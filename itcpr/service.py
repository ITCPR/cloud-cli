"""Service management for running sync as a background daemon."""

import os
import sys
import time
import signal
import atexit
import logging
import subprocess
import platform
from pathlib import Path
from typing import Optional
from .config import config
from .utils import get_logger, setup_logging

logger = get_logger(__name__)

# PID file location
PID_FILE = config.config_dir / "itcpr-service.pid"
LOG_FILE = config.config_dir / "itcpr-service.log"
IS_WINDOWS = platform.system() == "Windows"

def daemonize():
    """Daemonize the current process (Unix only)."""
    if IS_WINDOWS:
        # On Windows, we'll use subprocess to start a background process
        # This function shouldn't be called on Windows
        return
    
    try:
        # Fork first time
        pid = os.fork()
        if pid > 0:
            # Parent process - exit
            sys.exit(0)
    except OSError as e:
        logger.error(f"First fork failed: {e}")
        sys.exit(1)
    
    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)
    
    try:
        # Fork second time
        pid = os.fork()
        if pid > 0:
            # Parent process - exit
            sys.exit(0)
    except OSError as e:
        logger.error(f"Second fork failed: {e}")
        sys.exit(1)
    
    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    si = open(os.devnull, 'r')
    so = open(os.devnull, 'a+')
    se = open(os.devnull, 'a+')
    
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
    
    # Write PID file
    write_pid()
    
    # Register cleanup function
    atexit.register(remove_pid)

def start_windows_service(interval: int = 60):
    """Start service as background process on Windows."""
    import shutil
    
    # Get Python executable
    python_exe = sys.executable
    itcpr_script = shutil.which("itcpr") or f"{python_exe} -m itcpr.cli"
    
    # Create a batch script to run the service
    script_content = f'''@echo off
cd /d "%~dp0"
"{python_exe}" -m itcpr.cli service start --foreground --interval {interval} >> "{LOG_FILE}" 2>&1
'''
    
    script_file = config.config_dir / "itcpr-service.bat"
    config.ensure_config_dir()
    
    try:
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        # Start process in background using START command
        # Use CREATE_NO_WINDOW flag to hide console window
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        process = subprocess.Popen(
            ["cmd.exe", "/c", str(script_file)],
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo
        )
        
        # Write PID
        write_pid()
        
        return process.pid
    except Exception as e:
        logger.error(f"Failed to start Windows service: {e}")
        raise

def write_pid():
    """Write PID to file."""
    try:
        config.ensure_config_dir()
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.error(f"Failed to write PID file: {e}")

def read_pid() -> Optional[int]:
    """Read PID from file."""
    try:
        if PID_FILE.exists():
            with open(PID_FILE, 'r') as f:
                return int(f.read().strip())
    except Exception:
        pass
    return None

def remove_pid():
    """Remove PID file."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass

def is_running() -> bool:
    """Check if service is running."""
    pid = read_pid()
    if not pid:
        return False
    
    if IS_WINDOWS:
        # On Windows, use tasklist to check if process exists
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if str(pid) in result.stdout:
                return True
            else:
                remove_pid()
                return False
        except Exception:
            remove_pid()
            return False
    else:
        try:
            # Check if process exists
            os.kill(pid, 0)
            return True
        except OSError:
            # Process doesn't exist, remove stale PID file
            remove_pid()
            return False

def stop_service():
    """Stop the service."""
    pid = read_pid()
    if not pid:
        return False
    
    if IS_WINDOWS:
        try:
            # Use taskkill to terminate process
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            time.sleep(1)
            remove_pid()
            return True
        except Exception as e:
            logger.error(f"Failed to stop Windows service: {e}")
            remove_pid()
            return False
    else:
        try:
            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)
            
            # Wait for process to terminate (max 10 seconds)
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(1)
                except OSError:
                    # Process terminated
                    remove_pid()
                    return True
            
            # Force kill if still running
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
                remove_pid()
                return True
            except OSError:
                return True
        except OSError:
            remove_pid()
            return False

def setup_service_logging():
    """Setup logging to file for service mode."""
    config.ensure_config_dir()
    
    # Create file handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.INFO)

def run_service(interval: int = 60):
    """Run the sync service."""
    from .auth import Auth
    from .api import APIClient
    from .storage import Storage
    from .sync import SyncManager
    
    # Setup logging to file
    setup_service_logging()
    
    logger.info("Starting ITCPR sync service...")
    
    # Check authentication
    auth = Auth()
    if not auth.is_authenticated():
        logger.error("Not authenticated. Please run 'itcpr login' first.")
        sys.exit(1)
    
    api = APIClient(auth)
    storage = Storage()
    sync_manager = SyncManager(api, storage)
    
    # Setup signal handlers (Unix only)
    if not IS_WINDOWS:
        def signal_handler(sig, frame):
            logger.info("Shutdown signal received, stopping service...")
            sync_manager.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    else:
        # On Windows, handle Ctrl+C
        def signal_handler(sig, frame):
            logger.info("Shutdown signal received, stopping service...")
            sync_manager.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
    
    logger.info(f"Service started (sync interval: {interval} seconds)")
    
    # Main service loop
    while True:
        try:
            sync_manager.sync_all()
            
            # Wait for next sync, but check for shutdown periodically
            for _ in range(interval):
                if not sync_manager._running:
                    logger.info("Service stopped")
                    sys.exit(0)
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Service interrupted")
            break
        except Exception as e:
            logger.error(f"Service error: {e}", exc_info=True)
            time.sleep(5)  # Wait before retrying
    
    logger.info("Service stopped")
    remove_pid()

def get_service_status() -> dict:
    """Get service status information."""
    running = is_running()
    pid = read_pid() if running else None
    
    status = {
        "running": running,
        "pid": pid,
        "pid_file": str(PID_FILE),
        "log_file": str(LOG_FILE)
    }
    
    if running and LOG_FILE.exists():
        # Get last few lines of log
        try:
            with open(LOG_FILE, 'r') as f:
                lines = f.readlines()
                status["last_log_lines"] = lines[-5:] if len(lines) > 5 else lines
        except Exception:
            pass
    
    return status


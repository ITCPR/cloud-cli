"""CLI commands for ITCPR Cloud."""

import click
import sys
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from .config import config
from .utils import setup_logging, print_error, print_success, print_info, get_logger

logger = get_logger(__name__)

@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, verbose):
    """ITCPR Cloud - Sync GitHub repositories to your local machine."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)

@cli.command()
def login():
    """Authenticate this device with ITCPR Cloud."""
    from .auth import Auth
    auth = Auth()
    if auth.is_authenticated():
        # Verify token is still valid
        if auth.verify_token():
            if not click.confirm("You are already logged in. Do you want to login again?"):
                return
        else:
            # Token exists but is invalid (device was revoked)
            click.echo("Your device token is no longer valid (device may have been removed).")
            click.echo("Logging in again...")
            # Clear invalid token
            auth.logout()
    
    success = auth.login()
    if not success:
        click.echo("Login failed.", err=True)
        raise click.Abort()

@cli.command()
def logout():
    """Logout and clear stored credentials."""
    from .auth import Auth
    auth = Auth()
    if not auth.is_authenticated():
        click.echo("Not logged in.")
        return
    
    auth.logout()

@cli.command()
@click.pass_context
def status(ctx):
    """Show current status and assigned repositories."""
    from .auth import Auth
    from .api import APIClient
    from .storage import Storage
    auth = Auth()
    if not auth.is_authenticated():
        click.echo("Not logged in. Run 'itcpr login' first.")
        return
    
    api = APIClient(auth)
    storage = Storage()
    
    try:
        # Get device info
        me = api.get_me()
        device_id = auth.get_device_id()
        
        click.echo("\n=== Authentication ===")
        click.echo(f"Device ID: {device_id}")
        if me.get("user"):
            click.echo(f"User: {me['user'].get('name', 'N/A')}")
            click.echo(f"Email: {me['user'].get('email', 'N/A')}")
        
        # Get repos
        repos = api.get_repos()
        click.echo(f"\n=== Your Repositories ({len(repos)}) ===")
        if repos:
            for repo in repos:
                full_name = repo.get('full_name', '')
                repo_name = full_name.split('/', 1)[-1] if full_name else repo.get('name', 'N/A')
                click.echo(f"  - {repo_name}")
        else:
            click.echo("  No repositories")
        
        # Get local repos
        local_repos = storage.list_repos()
        click.echo(f"\n=== Local Repositories ({len(local_repos)}) ===")
        if local_repos:
            for repo in local_repos:
                sync_mode = repo.get("sync_mode", "manual")
                last_sync = repo.get("last_sync", "Never")
                click.echo(f"  - {repo['name']}")
                click.echo(f"    Path: {repo['local_path']}")
                click.echo(f"    Sync mode: {sync_mode}")
                click.echo(f"    Last sync: {last_sync}")
        else:
            click.echo("  No local repositories")
        
        click.echo()
        
    except Exception as e:
        logger.exception("Status error")
        print_error(f"Failed to get status: {e}")
        raise click.Abort()

@cli.command()
@click.pass_context
def repos(ctx):
    """List assigned repositories and their sync status."""
    from .auth import Auth
    from .api import APIClient
    from .storage import Storage
    auth = Auth()
    if not auth.is_authenticated():
        click.echo("Not logged in. Run 'itcpr login' first.")
        return
    
    api = APIClient(auth)
    storage = Storage()
    
    try:
        # Get assigned repos from API
        assigned_repos = api.get_repos()
        
        # Get local repos
        local_repos = {r["name"]: r for r in storage.list_repos()}
        
        if not assigned_repos:
            click.echo("No repositories assigned to this device.")
            return
        
        click.echo(f"\nYour Repositories ({len(assigned_repos)}):\n")
        
        for repo in assigned_repos:
            full_name = repo.get('full_name', '')
            repo_name = full_name.split('/', 1)[-1] if full_name else repo.get('name', 'N/A')
            local_repo = local_repos.get(repo_name)
            
            status_icon = "✓" if local_repo else "○"
            status_text = "Cloned" if local_repo else "Not cloned"
            
            click.echo(f"{status_icon} {repo_name} - {status_text}")
            if local_repo:
                click.echo(f"    Path: {local_repo['local_path']}")
                if local_repo.get("last_sync"):
                    click.echo(f"    Last sync: {local_repo['last_sync']}")
        
        click.echo()
        
    except Exception as e:
        logger.exception("Repos error")
        print_error(f"Failed to list repositories: {e}")
        raise click.Abort()

@cli.command()
@click.argument("repo")
@click.option("--path", "-p", type=click.Path(), help="Local path to clone repository")
@click.pass_context
def clone(ctx, repo, path):
    """Clone a repository from GitHub."""
    from .auth import Auth
    from .api import APIClient
    from .storage import Storage
    from .gitops import GitOps
    auth = Auth()
    if not auth.is_authenticated():
        click.echo("Not logged in. Run 'itcpr login' first.")
        return
    
    api = APIClient(auth)
    storage = Storage()
    
    try:
        # Get assigned repos
        assigned_repos = api.get_repos()
        repo_info = None
        
        # Find repo by name or full_name
        for r in assigned_repos:
            full_name = r.get('full_name', '')
            repo_name = full_name.split('/', 1)[-1] if full_name else r.get('name', 'N/A')
            if repo_name == repo or full_name == repo:
                repo_info = r
                break
        
        if not repo_info:
            click.echo(f"Repository '{repo}' is not assigned to this device.")
            return
        
        full_name = repo_info.get("full_name")
        repo_name = full_name.split('/', 1)[-1] if full_name else repo_info.get('name', 'N/A')
        remote_url = repo_info.get("clone_url") or repo_info.get("ssh_url")
        
        if not remote_url:
            click.echo("Repository URL not available.")
            return
        
        # Determine local path
        if path:
            local_path = Path(path)
        else:
            # Default: clone to current working directory
            local_path = Path.cwd() / repo_name
        
        # Check if already cloned
        existing = storage.get_repo(repo_name)
        if existing:
            click.echo(f"Repository '{repo_name}' is already cloned at {existing['local_path']}")
            if not click.confirm("Do you want to clone it again?"):
                return
        
        # Get GitHub token
        click.echo(f"Getting GitHub token for {repo_name}...")
        token = api.get_github_token(repo_name)
        
        # Clone
        click.echo(f"Cloning {repo_name} to {local_path}...")
        git = GitOps(local_path)
        git.clone(remote_url, token)
        
        # Register in storage
        storage.add_repo(repo_name, full_name, str(local_path), remote_url)
        
        print_success(f"Repository cloned successfully to {local_path}")
        
    except Exception as e:
        logger.exception("Clone error")
        print_error(f"Failed to clone repository: {e}")
        raise click.Abort()

@cli.command()
@click.option("--watch", "-w", is_flag=True, help="Run continuous sync loop")
@click.option("--interval", "-i", default=60, help="Sync interval in seconds (watch mode only)")
@click.pass_context
def sync(ctx, watch, interval):
    """Sync repositories with remote."""
    from .auth import Auth
    from .api import APIClient
    from .storage import Storage
    from .sync import SyncManager
    auth = Auth()
    if not auth.is_authenticated():
        click.echo("Not logged in. Run 'itcpr login' first.")
        return
    
    api = APIClient(auth)
    storage = Storage()
    sync_manager = SyncManager(api, storage)
    
    try:
        if watch:
            sync_manager.watch(interval)
        else:
            sync_manager.sync_all()
    except KeyboardInterrupt:
        click.echo("\nSync interrupted.")
    except Exception as e:
        logger.exception("Sync error")
        print_error(f"Sync failed: {e}")
        raise click.Abort()

@cli.command()
@click.option("--name", "-n", help="Repository name (defaults to current directory name)")
@click.option("--description", "-d", default="", help="Repository description")
@click.option("--public", is_flag=True, help="Create public repository (default: private)")
@click.option("--push", is_flag=True, help="Push initial commit to remote")
@click.pass_context
def init(ctx, name, description, public, push):
    """Initialize a new repository in the current folder."""
    from .auth import Auth
    from .api import APIClient
    from .storage import Storage
    from .gitops import GitOps
    auth = Auth()
    if not auth.is_authenticated():
        click.echo("Not logged in. Run 'itcpr login' first.")
        return
    
    api = APIClient(auth)
    storage = Storage()
    
    try:
        # Get current directory
        current_dir = Path.cwd()
        
        # Determine repository name
        if name:
            repo_name = name
        else:
            repo_name = current_dir.name
            if not repo_name or repo_name == ".":
                print_error("Cannot determine repository name. Please specify --name")
                raise click.Abort()
        
        # Check if already a git repo
        git = GitOps(current_dir)
        is_git_repo = git.is_repo()
        
        if is_git_repo:
            click.echo(f"Directory is already a git repository.")
            if not click.confirm("Continue with creating remote repository?"):
                return
        
        # Get user's GitHub username
        click.echo("Getting user information...")
        try:
            me = api.get_me()
            user_data = me.get("user", {})
            github_username = user_data.get("github_username")
            if not github_username:
                print_error("GitHub account not connected. Please connect your GitHub account first.")
                raise click.Abort()
        except Exception as e:
            logger.warning(f"Could not get user info: {e}")
            github_username = None
        
        # Create repository on GitHub (private by default, unless --public is specified)
        private = not public
        click.echo(f"Creating repository '{repo_name}' in organization ({'private' if private else 'public'})...")
        try:
            # Use project-template by default
            repo_data = api.create_repo(repo_name, description, private, template="project-template")
            print_success(f"Repository '{repo_name}' created successfully")
        except ValueError as e:
            # Handle "already exists" error
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                print_error(f"Repository '{repo_name}' already exists in the organization. Please choose a different name.")
                raise click.Abort()
            raise
        
        # Get repository owner and URLs
        full_name = repo_data.get("full_name", "")
        owner = full_name.split("/")[0] if "/" in full_name else repo_data.get("owner", {}).get("login", "")
        clone_url = repo_data.get("clone_url")
        ssh_url = repo_data.get("ssh_url")
        remote_url = clone_url or ssh_url
        
        if not remote_url:
            print_error("Repository created but URL not available")
            raise click.Abort()
        
        # Add device owner as admin collaborator
        if github_username and owner:
            click.echo(f"Adding you as admin collaborator...")
            try:
                api.add_collaborator(owner, repo_name, github_username, permission="admin")
                print_success(f"Added {github_username} as admin collaborator")
            except Exception as e:
                logger.warning(f"Failed to add collaborator: {e}")
                click.echo(f"Warning: Could not add you as collaborator. You may need to add yourself manually.")
        
        # Fetch template repository
        click.echo("Fetching template from ITCPR/project-template...")
        template_org = owner  # Use same org
        template_repo = "project-template"
        template_url = f"https://github.com/{template_org}/{template_repo}.git"
        
        temp_dir = None
        try:
            # Create temporary directory for template
            temp_dir = Path(tempfile.mkdtemp(prefix="itcpr-template-"))
            
            # Get GitHub token for cloning template
            token = api.get_github_token(template_repo)
            
            # Clone template to temp directory
            template_git = GitOps(temp_dir / template_repo)
            template_git.clone(template_url, token)
            template_path = temp_dir / template_repo
            
            # Copy template files to current directory (excluding .git)
            click.echo("Copying template files...")
            template_files_copied = False
            
            for item in template_path.iterdir():
                if item.name == ".git":
                    continue
                
                dest = current_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        # Skip if directory already exists
                        logger.debug(f"Skipping existing directory: {item.name}")
                        continue
                    shutil.copytree(item, dest)
                    template_files_copied = True
                else:
                    if dest.exists():
                        # Skip if file already exists
                        logger.debug(f"Skipping existing file: {item.name}")
                        continue
                    shutil.copy2(item, dest)
                    template_files_copied = True
            
            if template_files_copied:
                print_success("Template files copied")
            else:
                click.echo("Template files already exist, skipping copy")
            
        except Exception as e:
            logger.warning(f"Failed to fetch template: {e}")
            click.echo(f"Warning: Could not fetch template. Repository created but template files not copied.")
        finally:
            # Clean up temp directory
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.debug(f"Failed to clean up temp directory: {e}")
        
        # Initialize git if not already initialized
        if not is_git_repo:
            click.echo("Initializing git repository...")
            git.init()
            print_success("Git repository initialized")
        
        # Get GitHub token for remote operations
        click.echo("Setting up remote...")
        token = api.get_github_token(repo_name)
        
        # Add remote
        git.add_remote("origin", remote_url, token)
        print_success("Remote 'origin' configured")
        
        # Create initial commit if there are changes or no commits
        try:
            git.create_initial_commit("Initial commit from project-template")
            click.echo("Initial commit created")
        except Exception as e:
            logger.debug(f"Could not create initial commit: {e}")
            # This is okay, might already have commits or no files
        
        # Push if requested
        if push:
            click.echo("Pushing to remote...")
            try:
                branch = git.get_current_branch() or "main"
                git.push(set_upstream=True)
                print_success(f"Pushed to remote (branch: {branch})")
            except Exception as e:
                logger.warning(f"Push failed: {e}")
                print_error(f"Failed to push: {e}")
                click.echo("You can push manually later with: git push -u origin <branch>")
        
        # Register in storage
        full_name = repo_data.get("full_name", repo_name)
        storage.add_repo(repo_name, full_name, str(current_dir), remote_url)
        
        print_success(f"Repository '{repo_name}' initialized successfully!")
        if not push:
            click.echo(f"\nTo push your code, run: git push -u origin {git.get_current_branch() or 'main'}")
        
    except click.Abort:
        raise
    except Exception as e:
        logger.exception("Init error")
        print_error(f"Failed to initialize repository: {e}")
        raise click.Abort()

@cli.group()
def service():
    """Manage ITCPR sync service (background daemon)."""
    pass

@service.command()
@click.option("--interval", "-i", default=60, help="Sync interval in seconds (default: 60)")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't daemonize)")
@click.pass_context
def start(ctx, interval, foreground):
    """Start the sync service as a background daemon."""
    from .service import is_running, daemonize, run_service, start_windows_service, IS_WINDOWS
    
    if is_running():
        click.echo("Service is already running.")
        return
    
    if foreground:
        # Run in foreground
        click.echo(f"Starting service in foreground (interval: {interval}s)...")
        click.echo("Press Ctrl+C to stop")
        try:
            run_service(interval)
        except KeyboardInterrupt:
            click.echo("\nService stopped.")
    else:
        # Start in background
        if IS_WINDOWS:
            click.echo("Starting service in background (Windows)...")
            try:
                pid = start_windows_service(interval)
                click.echo(f"Service started in background (PID: {pid})")
                click.echo(f"Logs: {config.config_dir / 'itcpr-service.log'}")
            except Exception as e:
                click.echo(f"Failed to start service: {e}")
        else:
            # Unix: Daemonize
            click.echo("Starting service in background...")
            daemonize()
            run_service(interval)

@service.command()
def stop():
    """Stop the sync service."""
    from .service import is_running, stop_service
    
    if not is_running():
        click.echo("Service is not running.")
        return
    
    click.echo("Stopping service...")
    if stop_service():
        click.echo("Service stopped.")
    else:
        click.echo("Failed to stop service.")

@service.command()
def status():
    """Show service status."""
    from .service import get_service_status
    
    status = get_service_status()
    
    if status["running"]:
        click.echo("✓ Service is running")
        click.echo(f"  PID: {status['pid']}")
        click.echo(f"  PID file: {status['pid_file']}")
        click.echo(f"  Log file: {status['log_file']}")
        
        if "last_log_lines" in status and status["last_log_lines"]:
            click.echo("\n  Last log entries:")
            for line in status["last_log_lines"]:
                click.echo(f"    {line.rstrip()}")
    else:
        click.echo("✗ Service is not running")
        if status["pid_file"]:
            click.echo(f"  PID file: {status['pid_file']}")

@service.command()
def logs():
    """Show service logs."""
    from .service import LOG_FILE
    
    if not LOG_FILE.exists():
        click.echo("No log file found. Service may not have been started.")
        return
    
    # Show last 50 lines
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            for line in lines[-50:]:
                click.echo(line.rstrip())
    except Exception as e:
        click.echo(f"Error reading log file: {e}")

@service.command()
@click.option("--interval", "-i", default=60, help="Sync interval in seconds (default: 60)")
@click.option("--user", help="User to run service as (default: current user)")
def install(interval, user):
    """Install service to start automatically on boot (systemd/launchd)."""
    import platform
    import shutil
    import getpass
    
    system = platform.system()
    
    if system == "Linux":
        _install_systemd_service(interval, user)
    elif system == "Darwin":
        _install_launchd_service(interval, user)
    else:
        click.echo(f"Service installation not supported on {system}")
        click.echo("You can still run the service manually with 'itcpr service start'")

def _install_systemd_service(interval: int, user: Optional[str]):
    """Install systemd service file."""
    import getpass
    import shutil
    
    if os.geteuid() != 0:
        click.echo("Error: Root privileges required to install systemd service.")
        click.echo("Run: sudo itcpr service install")
        return
    
    service_user = user or getpass.getuser()
    python_path = shutil.which("python3") or sys.executable
    itcpr_path = shutil.which("itcpr")
    
    if not itcpr_path:
        click.echo("Error: 'itcpr' command not found in PATH")
        return
    
    service_content = f"""[Unit]
Description=ITCPR Cloud Sync Service
After=network.target

[Service]
Type=simple
User={service_user}
ExecStart={itcpr_path} service start --foreground --interval {interval}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    
    service_file = Path("/etc/systemd/system/itcpr.service")
    
    try:
        with open(service_file, 'w') as f:
            f.write(service_content)
        
        click.echo(f"Service file installed: {service_file}")
        click.echo("\nTo enable and start the service:")
        click.echo("  sudo systemctl daemon-reload")
        click.echo("  sudo systemctl enable itcpr")
        click.echo("  sudo systemctl start itcpr")
        click.echo("\nTo check status:")
        click.echo("  sudo systemctl status itcpr")
    except Exception as e:
        click.echo(f"Error installing service: {e}")

def _install_launchd_service(interval: int, user: Optional[str]):
    """Install launchd service (macOS)."""
    import getpass
    import shutil
    import plistlib
    from .service import LOG_FILE
    
    service_user = user or getpass.getuser()
    itcpr_path = shutil.which("itcpr")
    
    if not itcpr_path:
        click.echo("Error: 'itcpr' command not found in PATH")
        return
    
    plist_content = {
        "Label": "org.itcpr.sync",
        "ProgramArguments": [itcpr_path, "service", "start", "--foreground", "--interval", str(interval)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_FILE),
        "StandardErrorPath": str(LOG_FILE),
        "UserName": service_user
    }
    
    plist_file = Path.home() / "Library/LaunchAgents/org.itcpr.sync.plist"
    
    try:
        plist_file.parent.mkdir(parents=True, exist_ok=True)
        with open(plist_file, 'wb') as f:
            plistlib.dump(plist_content, f, fmt=plistlib.FMT_XML)
        
        click.echo(f"Service file installed: {plist_file}")
        click.echo("\nTo load and start the service:")
        click.echo(f"  launchctl load {plist_file}")
        click.echo(f"  launchctl start org.itcpr.sync")
        click.echo("\nTo check status:")
        click.echo("  launchctl list | grep itcpr")
        click.echo("\nTo unload:")
        click.echo(f"  launchctl unload {plist_file}")
    except Exception as e:
        click.echo(f"Error installing service: {e}")

@service.command()
def uninstall():
    """Uninstall service (remove system service files)."""
    import platform
    
    system = platform.system()
    
    if system == "Linux":
        _uninstall_systemd_service()
    elif system == "Darwin":
        _uninstall_launchd_service()
    elif system == "Windows":
        _uninstall_windows_task()
    else:
        click.echo(f"Service uninstallation not supported on {system}")

def _uninstall_systemd_service():
    """Uninstall systemd service."""
    if os.geteuid() != 0:
        click.echo("Error: Root privileges required to uninstall systemd service.")
        click.echo("Run: sudo itcpr service uninstall")
        return
    
    service_file = Path("/etc/systemd/system/itcpr.service")
    
    if service_file.exists():
        try:
            # Stop and disable service first
            os.system("systemctl stop itcpr 2>/dev/null")
            os.system("systemctl disable itcpr 2>/dev/null")
            
            service_file.unlink()
            click.echo("Service uninstalled.")
            click.echo("Run 'sudo systemctl daemon-reload' to reload systemd.")
        except Exception as e:
            click.echo(f"Error uninstalling service: {e}")
    else:
        click.echo("Service file not found.")

def _uninstall_launchd_service():
    """Uninstall launchd service."""
    plist_file = Path.home() / "Library/LaunchAgents/org.itcpr.sync.plist"
    
    if plist_file.exists():
        try:
            # Unload first
            os.system(f"launchctl unload {plist_file} 2>/dev/null")
            
            plist_file.unlink()
            click.echo("Service uninstalled.")
        except Exception as e:
            click.echo(f"Error uninstalling service: {e}")
    else:
        click.echo("Service file not found.")

def _install_windows_task(interval: int, user: Optional[str]):
    """Install Windows Task Scheduler task."""
    import getpass
    import shutil
    from .service import LOG_FILE
    
    python_exe = sys.executable
    itcpr_path = shutil.which("itcpr")
    
    if not itcpr_path:
        click.echo("Error: 'itcpr' command not found in PATH")
        return
    
    task_name = "ITCPR Sync Service"
    
    # Create a script that runs the service
    script_file = config.config_dir / "itcpr-service-start.bat"
    config.ensure_config_dir()
    
    log_file = str(LOG_FILE)
    script_content = f'''@echo off
cd /d "{config.config_dir}"
"{itcpr_path}" service start --foreground --interval {interval} >> "{log_file}" 2>&1
'''
    
    try:
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        # Create scheduled task using schtasks
        # Task runs at logon and repeats every hour (as a fallback)
        # The service itself handles the interval
        cmd = [
            "schtasks", "/Create",
            "/TN", task_name,
            "/TR", f'"{script_file}"',
            "/SC", "ONLOGON",
            "/F",  # Force (overwrite if exists)
            "/RL", "HIGHEST"  # Run with highest privileges
        ]
        
        if user:
            cmd.extend(["/RU", user])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode == 0:
            click.echo(f"Task scheduled: {task_name}")
            click.echo(f"Script: {script_file}")
            click.echo("\nThe service will start automatically on user logon.")
            click.echo("\nTo start immediately:")
            click.echo(f'  schtasks /Run /TN "{task_name}"')
            click.echo("\nTo check status:")
            click.echo(f'  schtasks /Query /TN "{task_name}"')
        else:
            click.echo(f"Error creating task: {result.stderr}")
            click.echo("\nYou may need to run as administrator.")
    except Exception as e:
        click.echo(f"Error installing service: {e}")

def _uninstall_windows_task():
    """Uninstall Windows Task Scheduler task."""
    task_name = "ITCPR Sync Service"
    
    try:
        # Delete the scheduled task
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode == 0:
            click.echo("Task uninstalled.")
            
            # Clean up script file
            script_file = config.config_dir / "itcpr-service-start.bat"
            if script_file.exists():
                script_file.unlink()
        else:
            if "not found" in result.stderr.lower():
                click.echo("Task not found.")
            else:
                click.echo(f"Error uninstalling task: {result.stderr}")
    except Exception as e:
        click.echo(f"Error uninstalling service: {e}")

def main():
    """Entry point for CLI."""
    cli()

if __name__ == "__main__":
    main()


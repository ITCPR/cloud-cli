"""Repository synchronization logic."""

import time
import signal
from pathlib import Path
from typing import Optional, Dict, Any, List
from .gitops import GitOps
from .api import APIClient
from .storage import Storage
from .utils import get_logger, print_error, print_success, print_info

logger = get_logger(__name__)

# Try to import yaml, but make it optional
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None

def load_sync_rules(repo_path: Path) -> Dict[str, Any]:
    """Load sync rules from itcpr.yml in repository root."""
    config_file = repo_path / "itcpr.yml"
    
    if not config_file.exists():
        return {}
    
    if not YAML_AVAILABLE:
        logger.warning("YAML not available. Install PyYAML to use itcpr.yml configuration.")
        return {}
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if not isinstance(config, dict):
                return {}
            
            # Extract sync rules
            sync_config = config.get('sync', {})
            return {
                'enabled': sync_config.get('enabled', True),
                'auto_commit': sync_config.get('auto_commit', True),
                'auto_push': sync_config.get('auto_push', True),
                'branch': sync_config.get('branch'),
                'ignore_patterns': sync_config.get('ignore', []),
            }
    except Exception as e:
        logger.warning(f"Failed to load itcpr.yml from {repo_path}: {e}")
        return {}

class SyncManager:
    """Manages repository synchronization."""
    
    def __init__(self, api_client: APIClient, storage: Storage):
        self.api = api_client
        self.storage = storage
        self._running = False
        self._shutdown_requested = False
    
    def sync_repo(self, repo_name: str, repo_path: Path) -> Dict[str, Any]:
        """Sync a single repository."""
        logger.info(f"Syncing repository: {repo_name}")
        
        try:
            # Load sync rules from itcpr.yml
            rules = load_sync_rules(repo_path)
            
            # Check if sync is disabled for this repo
            if not rules.get('enabled', True):
                logger.info(f"Sync disabled for {repo_name} (itcpr.yml)")
                return {
                    "success": True,
                    "skipped": True,
                    "message": "Sync disabled in itcpr.yml"
                }
            
            git = GitOps(repo_path)
            
            if not git.is_repo():
                return {
                    "success": False,
                    "error": f"Not a git repository: {repo_path}"
                }
            
            # Check if we need to switch branch
            if rules.get('branch'):
                current_branch = git.get_current_branch()
                if current_branch != rules['branch']:
                    logger.info(f"Switching to branch {rules['branch']} for {repo_name}")
                    # Note: Branch switching would need to be implemented in GitOps if needed
            
            # Check status
            status = git.get_status()
            if not status.get("clean"):
                if status.get("has_changes"):
                    # Check if auto_commit is enabled (default: True)
                    if rules.get('auto_commit', True):
                        print_info(f"  Uncommitted changes detected in {repo_name}")
                        # Commit local changes
                        try:
                            git.commit_if_changes()
                            print_success(f"  Committed local changes")
                        except Exception as e:
                            return {
                                "success": False,
                                "error": f"Failed to commit changes: {e}"
                            }
                    else:
                        return {
                            "success": False,
                            "error": "Uncommitted changes detected and auto_commit is disabled in itcpr.yml"
                        }
            
            # Fetch latest (silently, to update remote refs)
            git.fetch()
            
            # Check status after fetch
            status = git.get_status()
            is_behind = status.get("behind", False)
            is_ahead = status.get("ahead", False)
            
            # Pull if behind
            if is_behind:
                try:
                    print_info(f"  Pulling changes...")
                    git.pull_rebase()
                    print_success(f"  Pulled latest changes")
                except RuntimeError as e:
                    if "conflict" in str(e).lower():
                        return {
                            "success": False,
                            "error": f"Merge conflict detected. Please resolve manually."
                        }
                    raise
            
            # Push if ahead (check auto_push rule)
            if is_ahead:
                if rules.get('auto_push', True):
                    print_info(f"  Pushing local commits...")
                    try:
                        git.push()
                        print_success(f"  Pushed local commits")
                    except Exception as e:
                        return {
                            "success": False,
                            "error": f"Failed to push: {e}"
                        }
                else:
                    logger.info(f"Push skipped for {repo_name} (auto_push disabled in itcpr.yml)")
                    print_info(f"  Local commits not pushed (auto_push disabled)")
            
            # If no changes, just log silently (no output to user)
            if not is_behind and not is_ahead:
                logger.debug(f"Repository {repo_name} is up to date")
            
            # Update sync time
            self.storage.update_sync_time(repo_name)
            self.storage.add_sync_history(repo_name, "success", "Sync completed")
            
            print_success(f"Repository {repo_name} synced successfully")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Sync failed for {repo_name}: {e}")
            self.storage.add_sync_history(repo_name, "error", str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    def sync_all(self) -> Dict[str, Any]:
        """Sync all tracked repositories, respecting itcpr.yml rules."""
        repos = self.storage.list_repos()
        
        if not repos:
            print_info("No repositories to sync")
            return {"success": True, "synced": 0, "failed": 0, "skipped": 0}
        
        print_info(f"Syncing {len(repos)} repositories...")
        
        synced = 0
        failed = 0
        skipped = 0
        
        for repo in repos:
            repo_path = Path(repo["local_path"])
            if not repo_path.exists():
                print_error(f"Repository path does not exist: {repo_path}")
                failed += 1
                continue
            
            result = self.sync_repo(repo["name"], repo_path)
            if result.get("success"):
                if result.get("skipped"):
                    skipped += 1
                else:
                    synced += 1
            else:
                failed += 1
                if result.get("error"):
                    print_error(f"  {result['error']}")
        
        print_info(f"\nSync complete: {synced} succeeded, {failed} failed, {skipped} skipped")
        return {
            "success": failed == 0,
            "synced": synced,
            "failed": failed,
            "skipped": skipped
        }
    
    def watch(self, interval: int = 60):
        """Run continuous sync loop."""
        self._running = True
        self._shutdown_requested = False
        
        # Setup signal handlers
        def signal_handler(sig, frame):
            print_info("\nShutdown requested...")
            self._shutdown_requested = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print_info(f"Starting watch mode (sync every {interval} seconds)")
        print_info("Press Ctrl+C to stop")
        
        while self._running and not self._shutdown_requested:
            try:
                self.sync_all()
                
                # Wait for next sync, but check for shutdown periodically
                for _ in range(interval):
                    if self._shutdown_requested:
                        break
                    time.sleep(1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Watch loop error: {e}")
                if self._shutdown_requested:
                    break
                time.sleep(5)  # Wait before retrying
        
        print_info("Watch mode stopped")
        self._running = False
    
    def stop(self):
        """Stop watch mode."""
        self._shutdown_requested = True
        self._running = False


"""Git operations using system git command."""

import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from .utils import get_logger, print_error

logger = get_logger(__name__)

class GitOps:
    """Git operations wrapper."""
    
    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path).resolve()
        self.git = shutil.which("git")
        if not self.git:
            raise RuntimeError("git command not found. Please install git.")
    
    def _run_git(self, *args, check: bool = True, capture_output: bool = True, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run git command."""
        cmd = [self.git] + list(args)
        working_dir = cwd if cwd else self.repo_path
        # Convert Path to string for cwd
        cwd_str = str(working_dir) if working_dir else None
        logger.debug(f"Running: {' '.join(cmd)} in {cwd_str}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd_str,
                check=check,
                capture_output=capture_output,
                text=True,
                timeout=300  # 5 minute timeout
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error("Git command timed out")
            raise RuntimeError("Git operation timed out")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e.stderr}")
            raise RuntimeError(f"Git operation failed: {e.stderr}")
    
    def is_repo(self) -> bool:
        """Check if path is a git repository."""
        return (self.repo_path / ".git").exists()
    
    def clone(self, remote_url: str, token: Optional[str] = None) -> bool:
        """Clone repository."""
        if self.repo_path.exists():
            raise RuntimeError(f"Path already exists: {self.repo_path}")
        
        # Prepare URL with token if provided
        if token:
            # Insert token into URL
            if remote_url.startswith("https://"):
                # GitHub App installation tokens need x-access-token: prefix
                # https://github.com/owner/repo.git -> https://x-access-token:TOKEN@github.com/owner/repo.git
                url_parts = remote_url.split("://", 1)
                remote_url = f"{url_parts[0]}://x-access-token:{token}@{url_parts[1]}"
            elif remote_url.startswith("git@"):
                # For SSH, we'd need to use GIT_SSH_COMMAND, but we'll use HTTPS with token
                # Convert SSH URL to HTTPS with token
                # git@github.com:owner/repo.git -> https://x-access-token:TOKEN@github.com/owner/repo.git
                ssh_parts = remote_url.replace("git@", "").replace(":", "/", 1)
                remote_url = f"https://x-access-token:{token}@{ssh_parts}"
        
        try:
            # Ensure parent directory exists
            parent_dir = self.repo_path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            
            # Git clone needs to be run from the parent directory
            # Clone to the repo name in the parent directory
            repo_name = self.repo_path.name
            
            # Run git clone from parent directory
            self._run_git("clone", remote_url, repo_name, check=True, cwd=parent_dir)
            
            # Verify the clone was successful
            cloned_path = parent_dir / repo_name
            if not cloned_path.exists():
                raise RuntimeError(f"Clone completed but repository not found at {cloned_path}")
            
            logger.info(f"Cloned repository to {cloned_path}")
            return True
        except Exception as e:
            logger.error(f"Clone failed: {e}")
            raise
    
    def fetch(self) -> bool:
        """Fetch latest changes from remote."""
        if not self.is_repo():
            raise RuntimeError("Not a git repository")
        
        try:
            self._run_git("fetch", "origin", check=True)
            return True
        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """Get repository status."""
        if not self.is_repo():
            return {"clean": False, "error": "Not a git repository"}
        
        try:
            # Check if working directory is clean
            status_result = self._run_git("status", "--porcelain", check=True)
            has_changes = bool(status_result.stdout.strip())
            
            # Get current branch
            current_branch_result = self._run_git("rev-parse", "--abbrev-ref", "HEAD", check=True)
            current_branch = current_branch_result.stdout.strip()
            
            # Get remote tracking branch (e.g., origin/main)
            remote_branch = None
            try:
                remote_result = self._run_git("rev-parse", "--abbrev-ref", f"{current_branch}@{{upstream}}", check=True)
                remote_branch = remote_result.stdout.strip()
            except:
                # No upstream branch set, try origin/{current_branch}
                remote_branch = f"origin/{current_branch}"
            
            # Check if there are remote commits to pull (behind)
            behind = False
            if remote_branch:
                try:
                    # Check if remote branch exists
                    self._run_git("rev-parse", "--verify", remote_branch, check=True)
                    # Count commits in remote that aren't in local
                    behind_result = self._run_git("rev-list", "--count", f"HEAD..{remote_branch}", check=True)
                    behind_count = int(behind_result.stdout.strip())
                    behind = behind_count > 0
                except:
                    behind = False
            
            # Check if there are local commits to push (ahead)
            ahead = False
            if remote_branch:
                try:
                    # Check if remote branch exists
                    self._run_git("rev-parse", "--verify", remote_branch, check=True)
                    # Count commits in local that aren't in remote
                    ahead_result = self._run_git("rev-list", "--count", f"{remote_branch}..HEAD", check=True)
                    ahead_count = int(ahead_result.stdout.strip())
                    ahead = ahead_count > 0
                except:
                    ahead = False
            
            return {
                "clean": not has_changes,
                "has_changes": has_changes,
                "behind": behind,
                "ahead": ahead,
                "status_output": status_result.stdout
            }
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {"clean": False, "error": str(e)}
    
    def pull_rebase(self) -> bool:
        """Pull with rebase."""
        if not self.is_repo():
            raise RuntimeError("Not a git repository")
        
        try:
            self._run_git("pull", "--rebase", "origin", "HEAD", check=True)
            return True
        except subprocess.CalledProcessError as e:
            # Check if it's a merge conflict
            if "CONFLICT" in e.stderr or "conflict" in e.stderr.lower():
                raise RuntimeError("Merge conflict detected. Please resolve manually.")
            raise
    
    def commit_if_changes(self, message: str = "Auto-commit from itcpr") -> bool:
        """Commit changes if any exist."""
        status = self.get_status()
        if not status.get("has_changes"):
            return False
        
        try:
            # Add all changes
            self._run_git("add", "-A", check=True)
            # Commit
            self._run_git("commit", "-m", message, check=True)
            return True
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            raise
    
    def push(self, set_upstream: bool = False) -> bool:
        """Push to remote."""
        if not self.is_repo():
            raise RuntimeError("Not a git repository")
        
        try:
            branch = self.get_current_branch() or "main"
            if set_upstream:
                self._run_git("push", "-u", "origin", branch, check=True)
            else:
                self._run_git("push", "origin", "HEAD", check=True)
            return True
        except Exception as e:
            logger.error(f"Push failed: {e}")
            raise
    
    def get_remote_url(self) -> Optional[str]:
        """Get remote URL."""
        if not self.is_repo():
            return None
        
        try:
            result = self._run_git("remote", "get-url", "origin", check=True)
            return result.stdout.strip()
        except:
            return None
    
    def get_current_branch(self) -> Optional[str]:
        """Get current branch name."""
        if not self.is_repo():
            return None
        
        try:
            result = self._run_git("rev-parse", "--abbrev-ref", "HEAD", check=True)
            return result.stdout.strip()
        except:
            return None
    
    def init(self) -> bool:
        """Initialize a new git repository."""
        if self.is_repo():
            raise RuntimeError("Already a git repository")
        
        try:
            # Ensure directory exists
            self.repo_path.mkdir(parents=True, exist_ok=True)
            # Initialize git repo
            self._run_git("init", check=True, cwd=self.repo_path)
            return True
        except Exception as e:
            logger.error(f"Git init failed: {e}")
            raise
    
    def add_remote(self, name: str, url: str, token: Optional[str] = None) -> bool:
        """Add remote repository."""
        if not self.is_repo():
            raise RuntimeError("Not a git repository")
        
        # Prepare URL with token if provided
        if token:
            if url.startswith("https://"):
                url_parts = url.split("://", 1)
                url = f"{url_parts[0]}://x-access-token:{token}@{url_parts[1]}"
            elif url.startswith("git@"):
                ssh_parts = url.replace("git@", "").replace(":", "/", 1)
                url = f"https://x-access-token:{token}@{ssh_parts}"
        
        try:
            # Check if remote already exists
            try:
                existing_url = self._run_git("remote", "get-url", name, check=True)
                if existing_url.stdout.strip() != url:
                    # Update existing remote
                    self._run_git("remote", "set-url", name, url, check=True)
            except:
                # Remote doesn't exist, add it
                self._run_git("remote", "add", name, url, check=True)
            return True
        except Exception as e:
            logger.error(f"Add remote failed: {e}")
            raise
    
    def create_initial_commit(self, message: str = "Initial commit") -> bool:
        """Create initial commit if there are files to commit."""
        if not self.is_repo():
            raise RuntimeError("Not a git repository")
        
        try:
            # First check if there are any commits
            has_commits = False
            try:
                self._run_git("rev-parse", "--verify", "HEAD", check=True)
                has_commits = True
            except:
                # No commits yet
                has_commits = False
            
            # If already has commits, check status normally
            if has_commits:
                status = self.get_status()
                if not status.get("has_changes"):
                    # Already has commits and no changes
                    return False
                # Has commits and changes, add and commit
                self._run_git("add", "-A", check=True)
                self._run_git("commit", "-m", message, check=True)
                return True
            
            # No commits yet - check if there are any files to commit
            # Use git status --porcelain to check for changes without needing HEAD
            try:
                status_result = self._run_git("status", "--porcelain", check=True)
                has_changes = bool(status_result.stdout.strip())
            except:
                has_changes = False
            
            # If no changes, create a README
            if not has_changes:
                readme_path = self.repo_path / "README.md"
                if not readme_path.exists():
                    readme_path.write_text(f"# {self.repo_path.name}\n\n")
                    has_changes = True
            
            if has_changes:
                # Add all files
                self._run_git("add", "-A", check=True)
                # Commit
                self._run_git("commit", "-m", message, check=True)
                return True
            
            return False
        except Exception as e:
            logger.error(f"Create initial commit failed: {e}")
            raise


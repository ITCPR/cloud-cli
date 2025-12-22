"""CLI commands for ITCPR Cloud."""

import click
from pathlib import Path
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
        
        # Get assigned repos
        repos = api.get_repos()
        click.echo(f"\n=== Assigned Repositories ({len(repos)}) ===")
        if repos:
            for repo in repos:
                full_name = repo.get('full_name', '')
                repo_name = full_name.split('/', 1)[-1] if full_name else repo.get('name', 'N/A')
                click.echo(f"  - {repo_name}")
        else:
            click.echo("  No repositories assigned")
        
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
        
        click.echo(f"\nAssigned Repositories ({len(assigned_repos)}):\n")
        
        for repo in assigned_repos:
            full_name = repo.get('full_name', '')
            repo_name = full_name.split('/', 1)[-1] if full_name else repo.get('name', 'N/A')
            full_name = repo.get("full_name", repo_name)
            local_repo = local_repos.get(repo_name)
            
            status_icon = "✓" if local_repo else "○"
            status_text = "Cloned" if local_repo else "Not cloned"
            
            click.echo(f"{status_icon} {full_name} - {status_text}")
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
        click.echo(f"Getting GitHub token for {full_name}...")
        token = api.get_github_token(repo_name)
        
        # Clone
        click.echo(f"Cloning {full_name} to {local_path}...")
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
            repo_data = api.create_repo(repo_name, description, private)
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
            git.create_initial_commit("Initial commit")
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

def main():
    """Entry point for CLI."""
    cli()

if __name__ == "__main__":
    main()


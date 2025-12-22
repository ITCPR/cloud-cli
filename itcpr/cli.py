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
                click.echo(f"  - {repo.get('full_name', repo.get('name', 'N/A'))}")
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
            repo_name = repo.get("name")
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
            if r.get("name") == repo or r.get("full_name") == repo:
                repo_info = r
                break
        
        if not repo_info:
            click.echo(f"Repository '{repo}' is not assigned to this device.")
            return
        
        repo_name = repo_info.get("name")
        full_name = repo_info.get("full_name")
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

def main():
    """Entry point for CLI."""
    cli()

if __name__ == "__main__":
    main()


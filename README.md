# ITCPR Cloud CLI

A command-line tool for syncing GitHub repositories from ITCPR Cloud to your local machine. Manage your repositories with secure device-based authentication and automated synchronization.

## Features

- 🔐 Device-based authentication with ITCPR Cloud
- 🆕 Create new repositories in the organization
- 📦 Automatic repository synchronization
- 🔄 Manual or continuous sync modes
- 💾 Local SQLite database for metadata tracking
- 🔒 Secure token storage using OS keyring
- 🛡️ Safe git operations with conflict detection

## Installation

### From PyPI (Recommended)

```bash
pip install itcpr
```

Or use `pip3` or `python3 -m pip` if needed.

### From Source

To install from source for development or contribution:

```bash
git clone https://github.com/ITCPR/cloud-cli.git
cd cloud-cli
pip install -e .
```

Or use `pip3` or `python3 -m pip` if needed.

### Uninstall

To remove the CLI tool:

```bash
pip uninstall itcpr
```

**Note:** This will remove the CLI tool but will **not** delete:
- Configuration files (`~/.itcpr/config.toml`)
- Local repository database (`~/.itcpr/repos.db`)
- Stored device tokens (in OS keyring)

To completely remove all data:

```bash
# Uninstall the package
pip uninstall itcpr

# Remove configuration and data
rm -rf ~/.itcpr

# Remove stored tokens from OS keyring
# On macOS: Use Keychain Access app to remove "itcpr" entries
# On Linux: Use your keyring manager (e.g., seahorse, kwallet)
# On Windows: Use Credential Manager
```

### Requirements

- Python 3.10+
- Git (system installation)
- Access to api.itcpr.org (API) and cloud.itcpr.org (frontend)

## Prerequisites

**Important:** Before using the CLI, you must:

1. Visit [cloud.itcpr.org](https://cloud.itcpr.org)
2. Connect your GitHub account
3. Ensure your repositories are assigned to your device

Once your GitHub account is connected and repositories are assigned, you can proceed with the CLI login.

## Quick Start

### 1. Login

Authenticate your device with ITCPR Cloud:

```bash
itcpr login
```

**Note:** Make sure you've connected your GitHub account at [cloud.itcpr.org](https://cloud.itcpr.org) before logging in.

This will:
- Open your browser to the device login page
- Display a device code
- Wait for approval
- Store credentials securely

### 2. Check Status

View your assigned repositories:

```bash
itcpr status
```

### 3. List Repositories

See all repositories assigned to your device:

```bash
itcpr repos
```

### 4. Clone a Repository

Clone a repository to your local machine:

```bash
itcpr clone paperport-itcpr
```

Or specify a custom path:

```bash
itcpr clone paperport-itcpr --path ~/projects/paperport
```

### 5. Initialize a New Repository

Create a new repository in the current folder:

```bash
itcpr init
```

This will:
- Create a new repository in the organization (using current directory name)
- Add you as an admin collaborator
- Initialize git repository
- Set up remote origin
- Create an initial commit

With options:

```bash
# Custom repository name (creates private repo by default)
itcpr init --name my-new-repo

# With description
itcpr init --name my-repo --description "My awesome project"

# Create public repository (default is private)
itcpr init --public

# Initialize and push immediately
itcpr init --push
```

**Note:** If the repository name already exists in the organization, you'll be prompted to choose a different name.

### 6. Sync Repositories

Sync all cloned repositories:

```bash
itcpr sync
```

Run continuous sync (watches for changes):

```bash
itcpr sync --watch
```

With custom interval:

```bash
itcpr sync --watch --interval 120  # Sync every 2 minutes
```

**Note:** Watch mode runs in the foreground and will block your terminal. Press `Ctrl+C` to stop. To run it in the background, you can use:

```bash
# Run in background (Linux/macOS)
itcpr sync --watch &

# Or use nohup to keep it running after closing terminal
nohup itcpr sync --watch > itcpr.log 2>&1 &
```

### 7. Logout

Clear stored credentials:

```bash
itcpr logout
```

## Commands

### `itcpr login`

Starts the device authentication flow. Opens your browser to the device login page at `cloud.itcpr.org/device` and polls the API for approval.

**Prerequisite:** Ensure your GitHub account is connected at [cloud.itcpr.org](https://cloud.itcpr.org) before logging in.

### `itcpr logout`

Revokes device token and clears local metadata.

### `itcpr status`

Shows:
- Logged-in user information
- Device ID
- Assigned repositories
- Local repositories with sync status

### `itcpr repos`

Lists all repositories assigned to this device with their clone status.

### `itcpr clone <repo>`

Clones a repository from GitHub using short-lived installation tokens.

Options:
- `--path, -p`: Custom local path for the repository

### `itcpr init`

Creates a new repository in the organization and initializes it in the current folder. The repository name defaults to the current directory name, or you can specify a custom name.

**Options:**
- `--name, -n`: Repository name (defaults to current directory name)
- `--description, -d`: Repository description
- `--public`: Create a public repository (default: private)
- `--push`: Push initial commit to remote immediately

**What it does:**
1. Creates a new repository in the organization via GitHub API
2. Adds you (the device owner) as an admin collaborator
3. Initializes git repository if not already initialized
4. Sets up remote origin with authentication
5. Creates an initial commit (creates README.md if no files exist)
6. Optionally pushes to remote if `--push` is used

**Example:**

```bash
# Create repo with current directory name (private by default)
cd my-project
itcpr init

# Create repo with custom name
itcpr init --name awesome-project --description "My awesome project"

# Create public repo and push immediately
itcpr init --public --push
```

**Error handling:**
- If the repository name already exists, you'll see: "Repository 'name' already exists in the organization. Please choose a different name."
- If your GitHub account is not connected, you'll be prompted to connect it first.

### `itcpr sync`

Synchronizes all cloned repositories. By default, performs a one-time sync.

**Options:**
- `--watch, -w`: Run continuous sync loop (watches for changes)
- `--interval, -i`: Sync interval in seconds (watch mode only, default: 60)

**Per-Repository Configuration (itcpr.yml):**

You can configure per-repository sync behavior by creating an `itcpr.yml` file in the repository root:

```yaml
sync:
  enabled: true          # Enable/disable sync for this repo (default: true)
  auto_commit: true      # Auto-commit uncommitted local changes (default: true)
  auto_push: true        # Auto-push local commits to remote (default: true)
  branch: main           # Optional: specific branch to sync
  ignore:               # Optional: patterns to ignore
    - "*.log"
    - "temp/"
```

**Note:** `auto_commit` and `auto_push` are independent settings:
- `auto_commit`: Automatically commits uncommitted changes in your working directory
- `auto_push`: Automatically pushes local commits to the remote repository
- If both are enabled (default), the tool will commit uncommitted changes and then push them automatically
- You can set `auto_commit: true, auto_push: false` to commit locally without pushing
- If `itcpr.yml` doesn't exist, the tool uses default values (all enabled). The configuration file is optional.

## How It Works

### Authentication Flow

1. Device requests an authentication code from the backend
2. User approves the device in browser at `cloud.itcpr.org/device`
3. Device token is stored securely in OS keyring
4. Token is used for all subsequent API requests

### Repository Synchronization

The sync process follows these steps:

1. Fetches latest changes from the remote repository
2. Detects uncommitted local changes
3. Automatically commits local changes (if enabled)
4. Pulls remote changes with rebase
5. Pushes local commits (if enabled and permitted)
6. Aborts on merge conflicts (requires manual resolution)

### Security

- **No Personal Access Tokens**: Only uses backend-issued short-lived GitHub installation tokens
- **Device Tokens**: Revocable device authentication
- **OS Keyring**: Credentials stored securely using system keyring
- **Safe Git Operations**: Never force-pushes, detects conflicts

## Configuration

### Global Configuration

The CLI stores configuration and data in `~/.itcpr/`:

- **Configuration**: `~/.itcpr/config.toml` - Global settings
- **Repository Database**: `~/.itcpr/repos.db` - SQLite database for repository metadata

### Per-Repository Configuration (itcpr.yml)

Each repository can have its own `itcpr.yml` file in the repository root to control sync behavior:

```yaml
sync:
  enabled: true          # Enable/disable sync for this repo
  auto_commit: true      # Automatically commit local changes
  auto_push: true        # Automatically push local commits
  branch: main           # Optional: sync specific branch
  ignore: []             # Optional: file patterns to ignore
```

**Example: Disable auto-push for a repository**

```yaml
sync:
  auto_push: false
```

**Example: Disable sync entirely for a repository**

```yaml
sync:
  enabled: false
```

## Development & Mock Mode

The CLI includes a built-in mock mode for testing and development when the API is unavailable.

### Automatic Mock Mode

When the API at `api.itcpr.org` is unavailable, the CLI automatically falls back to mock API responses:
- If the backend returns 404 or is unreachable, mock responses are used automatically
- You'll see a warning: "⚠️ Backend unavailable, using mock mode for testing"

### Manual Mock Mode

You can also enable mock mode explicitly:

```bash
# Using environment variable
export ITCPR_MOCK_MODE=true
itcpr login

# Or set in config file (~/.itcpr/config.toml)
# mock_mode = true
```

**Mock Features:**
- Auto-approves device login after 2 seconds
- Provides sample user and repository data
- Generates mock GitHub tokens
- All commands work in mock mode for testing purposes

## Troubleshooting

### "Not logged in" error

Run `itcpr login` to authenticate your device. Make sure you've connected your GitHub account at [cloud.itcpr.org](https://cloud.itcpr.org) first. If the backend is unavailable, mock mode will activate automatically for testing.

### "Repository not assigned" error

The repository must be assigned to your device in ITCPR Cloud. Make sure you've:
1. Connected your GitHub account at [cloud.itcpr.org](https://cloud.itcpr.org)
2. Assigned the repository to your device in the ITCPR Cloud dashboard

If the issue persists, contact an administrator.

### "Repository already exists" error (init command)

When running `itcpr init`, if you see this error, it means a repository with that name already exists in the organization. Choose a different name:

```bash
itcpr init --name different-name
```

### "GitHub account not connected" error (init command)

The `init` command requires your GitHub account to be connected. Make sure you've:
1. Visited [cloud.itcpr.org](https://cloud.itcpr.org)
2. Connected your GitHub account
3. Then run `itcpr init` again

### Merge Conflicts

If a merge conflict is detected during sync:
1. Resolve conflicts manually in the repository
2. Commit the resolution
3. Run `itcpr sync` again

### Git Command Not Found

Ensure Git is installed and available in your PATH:

```bash
git --version
```

If Git is not installed, install it using your system's package manager.

### Token Storage Issues

On Linux, you may need to install a keyring backend:

```bash
# For GNOME
sudo apt-get install python3-keyring

# For KDE
sudo apt-get install python3-keyring kdewallet
```

On macOS and Windows, the keyring should work out of the box.

## Development

### Project Structure

```
cloud-cli/
├── itcpr/
│   ├── __init__.py      # Package initialization
│   ├── cli.py           # CLI commands
│   ├── auth.py          # Authentication
│   ├── api.py           # API client
│   ├── gitops.py        # Git operations
│   ├── sync.py          # Sync logic
│   ├── config.py        # Configuration
│   ├── storage.py       # SQLite storage
│   └── utils.py         # Utilities
├── setup.py             # Setup script
├── pyproject.toml       # Project metadata
└── README.md            # This file
```

### Development Setup

```bash
# Install in development mode
pip install -e .

# Run CLI
itcpr --help
```

### Contributing

Contributions are welcome! Please ensure your code follows the project's style guidelines and includes appropriate tests.

## License

MIT License - see LICENSE file for details.

## Support

For issues, questions, or feature requests, please contact ITCPR support or open an issue on GitHub.


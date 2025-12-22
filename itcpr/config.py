"""Configuration management for ITCPR Cloud."""

import os
from pathlib import Path
from typing import Optional, Dict, Any

# Try to import tomllib (Python 3.11+), fallback to tomli for older versions
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# Default config directory
CONFIG_DIR = Path.home() / ".itcpr"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DB_FILE = CONFIG_DIR / "repos.db"

# Default API endpoint
DEFAULT_API_BASE = "https://api.itcpr.org"

class Config:
    """Manages application configuration."""
    
    def __init__(self):
        self.config_dir = CONFIG_DIR
        self.config_file = CONFIG_FILE
        self.db_file = DB_FILE
        self.api_base = os.getenv("ITCPR_API_BASE", DEFAULT_API_BASE)
        # Enable mock mode if explicitly set or if backend is unavailable
        self.mock_mode = os.getenv("ITCPR_MOCK_MODE", "").lower() in ("true", "1", "yes")
        self._config_data: Dict[str, Any] = {}
        self._load_config()
        # Check config file for mock mode
        if not self.mock_mode:
            self.mock_mode = self.get("mock_mode", False)
    
    def _load_config(self):
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                if tomllib:
                    with open(self.config_file, "rb") as f:
                        self._config_data = tomllib.load(f)
                else:
                    # Fallback to JSON if tomllib not available
                    import json
                    with open(self.config_file.with_suffix('.json'), 'r') as f:
                        self._config_data = json.load(f)
            except Exception as e:
                # If config is invalid, use defaults
                self._config_data = {}
    
    def ensure_config_dir(self):
        """Ensure config directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value."""
        keys = key.split(".")
        value = self._config_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value if value is not None else default
    
    def set(self, key: str, value: Any):
        """Set config value (in memory only, doesn't persist)."""
        keys = key.split(".")
        config = self._config_data
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    def save(self):
        """Save configuration to file."""
        self.ensure_config_dir()
        try:
            import tomli_w
            with open(self.config_file, "wb") as f:
                tomli_w.dump(self._config_data, f)
        except ImportError:
            # Fallback to manual TOML writing if tomli_w not available
            import json
            with open(self.config_file.with_suffix('.json'), 'w') as f:
                json.dump(self._config_data, f, indent=2)

# Global config instance
config = Config()


"""Utility functions."""

import sys
import logging
from typing import Optional

def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)

def print_error(message: str):
    """Print error message to stderr."""
    print(f"Error: {message}", file=sys.stderr)

def print_success(message: str):
    """Print success message."""
    print(f"✓ {message}")

def print_info(message: str, end: str = "\n", flush: bool = False):
    """Print info message."""
    print(message, end=end, flush=flush)

def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


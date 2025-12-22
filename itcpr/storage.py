"""Local storage using SQLite for repository metadata."""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from .config import config

class Storage:
    """Manages local SQLite database for repository metadata."""
    
    def __init__(self):
        self.db_path = config.db_file
        self._ensure_db()
    
    def _ensure_db(self):
        """Ensure database and tables exist."""
        config.ensure_config_dir()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Repositories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                local_path TEXT NOT NULL,
                remote_url TEXT,
                last_sync TEXT,
                sync_mode TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Sync history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (repo_name) REFERENCES repos(name)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_repo(self, name: str, full_name: str, local_path: str, remote_url: Optional[str] = None):
        """Add or update a repository."""
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO repos 
            (name, full_name, local_path, remote_url, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, 
                COALESCE((SELECT created_at FROM repos WHERE name = ?), ?))
        """, (name, full_name, local_path, remote_url, now, name, now))
        
        conn.commit()
        conn.close()
    
    def get_repo(self, name: str) -> Optional[Dict[str, Any]]:
        """Get repository by name."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM repos WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def list_repos(self) -> List[Dict[str, Any]]:
        """List all repositories."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM repos ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_sync_time(self, name: str):
        """Update last sync time for a repository."""
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE repos SET last_sync = ?, updated_at = ? WHERE name = ?
        """, (now, now, name))
        
        conn.commit()
        conn.close()
    
    def set_sync_mode(self, name: str, mode: str):
        """Set sync mode for a repository."""
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE repos SET sync_mode = ?, updated_at = ? WHERE name = ?
        """, (mode, now, name))
        
        conn.commit()
        conn.close()
    
    def add_sync_history(self, repo_name: str, status: str, message: Optional[str] = None):
        """Add entry to sync history."""
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO sync_history (repo_name, status, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (repo_name, status, message, now))
        
        conn.commit()
        conn.close()
    
    def remove_repo(self, name: str):
        """Remove repository from tracking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM repos WHERE name = ?", (name,))
        cursor.execute("DELETE FROM sync_history WHERE repo_name = ?", (name,))
        
        conn.commit()
        conn.close()
    
    def clear_all(self):
        """Clear all data (for logout)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM sync_history")
        cursor.execute("DELETE FROM repos")
        
        conn.commit()
        conn.close()


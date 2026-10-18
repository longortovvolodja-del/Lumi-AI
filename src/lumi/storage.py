"""SQLite-backed local notes storage."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    """Return the per-user Lumi data directory on Windows."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    path = root / "Lumi" / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


class NotesStore:
    """Simple local notes database. Notes never leave this computer by default."""

    def __init__(self, database: Path | None = None) -> None:
        self.database = database or (data_dir() / "lumi.db")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def list_notes(self, query: str = "") -> list[dict[str, Any]]:
        with self._connect() as connection:
            if query.strip():
                term = f"%{query.strip()}%"
                rows = connection.execute(
                    """SELECT id, title, body, updated_at FROM notes
                       WHERE title LIKE ? OR body LIKE ?
                       ORDER BY updated_at DESC, id DESC""",
                    (term, term),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT id, title, body, updated_at FROM notes
                       ORDER BY updated_at DESC, id DESC"""
                ).fetchall()
        return [dict(row) for row in rows]

    def save_note(self, title: str, body: str, note_id: int | None = None) -> int:
        clean_title = title.strip() or "Новая заметка"
        with self._connect() as connection:
            if note_id is None:
                cursor = connection.execute(
                    "INSERT INTO notes (title, body, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (clean_title, body),
                )
                return int(cursor.lastrowid)
            connection.execute(
                """UPDATE notes SET title = ?, body = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (clean_title, body, note_id),
            )
            return note_id

    def delete_note(self, note_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))

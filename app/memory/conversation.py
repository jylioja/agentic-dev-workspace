import sqlite3
import json
from pathlib import Path
from datetime import datetime

# 1. Selvitetään tämän tiedoston (conversation.py) sijainti ja peruutetaan 3 askelta taaksepäin projektin juureen
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 2. Yhdistetään juuripolkuun data/db/sessions.db
DB_PATH = BASE_DIR / "data" / "db" / "sessions.db"

# 3. Luodaan kansiot (luo nyt varmasti oikeaan paikkaan projektin juuressa)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db():
    """Luo tarvittavat tietokantataulut, jos niitä ei ole olemassa."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                agent_key TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_logs TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_message(session_id: str, agent_key: str, role: str, content: str, tool_logs: list = None):
    """Tallentaa yksittäisen viestin ja mahdolliset työkalulokit tietokantaan."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (session_id, agent_key, role, content, tool_logs)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session_id,
            agent_key,
            role,
            content,
            json.dumps(tool_logs) if tool_logs else None
        ))
        conn.commit()


def load_history(session_id: str) -> list[dict]:
    """Hakee tietyn session kaikki viestit järjestyksessä."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content, tool_logs 
            FROM messages 
            WHERE session_id = ? 
            ORDER BY id ASC
        """, (session_id,))
        rows = cursor.fetchall()
        
        history = []
        for role, content, tool_logs_json in rows:
            msg = {"role": role, "content": content}
            if tool_logs_json:
                msg["tool_logs"] = json.loads(tool_logs_json)
            history.append(msg)
        return history
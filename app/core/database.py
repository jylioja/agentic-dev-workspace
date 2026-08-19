# app/core/database.py
import sqlite3
import json
import uuid
import os
from datetime import datetime

# TUODAAN UUSI VEKTORITIETOKANTA (RAG)
from app.core.vector_db import add_to_memory

# Määritetään tietokannan polku (luo 'data' kansion jos se puuttuu)
DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "chat_history.db")

def get_connection():
    """Luo ja palauttaa tietokantayhteyden. Palauttaa rivit sanakirjoina (dict)."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Alustaa tietokannan taulut, jos niitä ei ole olemassa."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Sessiot-taulu (Keskustelut)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                agent_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Viestit-taulu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                tool_logs TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            )
        """)
        conn.commit()

# --- SESSIOIDEN HALLINTA ---

def create_session(agent_key: str, title: str = "Uusi keskustelu") -> str:
    """Luo uuden keskustelusession ja palauttaa sen ID:n."""
    session_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, agent_key) VALUES (?, ?, ?)",
            (session_id, title, agent_key)
        )
        conn.commit()
    return session_id

def get_all_sessions() -> list[dict]:
    """Hakee kaikki sessiot uusimmasta vanhimpaan."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

def delete_session(session_id: str):
    """Poistaa session ja kaikki siihen liittyvät viestit (Cascade)."""
    with get_connection() as conn:
        # Pragma foreign_keys=ON vaaditaan SQLitessä CASCADE-poistoihin
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()

def update_session_title(session_id: str, new_title: str):
    """Päivittää keskustelun otsikon."""
    with get_connection() as conn:
        conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, session_id))
        conn.commit()

# --- VIESTIEN HALLINTA ---

def add_message(session_id: str, role: str, content: str, tool_logs: list = None):
    """Lisää viestin tiettyyn sessioon. tool_logs tallennetaan JSON-muodossa. 
    Tallentaa viestin myös semanttiseen vektoritietokantaan!"""
    logs_json = json.dumps(tool_logs) if tool_logs else None
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (session_id, role, content, tool_logs) VALUES (?, ?, ?, ?)",
            (session_id, role, content, logs_json)
        )
        message_id = cursor.lastrowid
        conn.commit()
        
        # --- UUSI OMINAISUUS: TALLENNETAAN VEKTORIKANTAAN ---
        if content:
            # Koska tool_logs on piilotettu RAG-haussa, puhdistetaan niitä hieman
            clean_content = content
            # Estetään tyhjien viestien kaatumiset
            if clean_content.strip():
                try:
                    add_to_memory(message_id, session_id, role, clean_content)
                except Exception as e:
                    print(f"Varoitus: Vektoritallennus epäonnistui: {e}")

def get_messages(session_id: str) -> list[dict]:
    """Hakee tietyn session kaikki viestit aikajärjestyksessä."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
        rows = cursor.fetchall()
        
        messages = []
        for row in rows:
            msg = dict(row)
            # Muutetaan JSON-teksti takaisin Python-listaksi
            msg['tool_logs'] = json.loads(msg['tool_logs']) if msg['tool_logs'] else None
            messages.append(msg)
            
        return messages
        
def cleanup_empty_sessions(exclude_session_id: str = None):
    """Poistaa tietokannasta kaikki sessiot, joissa ei ole yhtään viestiä.
    Ei kuitenkaan poista aktiivista sessiota, jota käyttäjä parhaillaan katsoo."""
    with get_connection() as conn:
        if exclude_session_id:
            conn.execute("""
                DELETE FROM sessions 
                WHERE id NOT IN (SELECT DISTINCT session_id FROM messages)
                AND id != ?
            """, (exclude_session_id,))
        else:
            conn.execute("""
                DELETE FROM sessions 
                WHERE id NOT IN (SELECT DISTINCT session_id FROM messages)
            """)
        conn.commit()

# Ajetaan alustus aina kun moduuli ladataan ensimmäisen kerran
init_db()
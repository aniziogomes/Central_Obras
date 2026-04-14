import sqlite3
from pathlib import Path

DB_PATH = Path("data/central_obras.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    with open("schema.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def query_all(sql, params=()):
    conn = get_connection()
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def query_one(sql, params=()):
    conn = get_connection()
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    conn.close()
    return row


def execute(sql, params=()):
    conn = get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id
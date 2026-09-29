import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostics_reports.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            notes TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def save_report(title, summary_dict):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO reports (title, created_at, summary_json, notes) VALUES (?, ?, ?, ?)",
        (title, datetime.now().isoformat(timespec="seconds"), json.dumps(summary_dict), "")
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_reports():
    conn = get_connection()
    rows = conn.execute("SELECT id, title, created_at FROM reports ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows


def get_report(report_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    return row


def update_notes(report_id, notes):
    conn = get_connection()
    conn.execute("UPDATE reports SET notes = ? WHERE id = ?", (notes, report_id))
    conn.commit()
    conn.close()


def delete_report(report_id):
    conn = get_connection()
    conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()

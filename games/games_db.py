import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_games_db():
    """إنشاء جدول الألعاب في قاعدة البيانات الرئيسية لو مش موجود"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def fetch_active_games():
    """جلب الألعاب المتاحة حالياً"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT game_key, title, folder_name FROM games_list WHERE is_active = 1")
    games = cursor.fetchall()
    conn.close()
    return [dict(g) for g in games]

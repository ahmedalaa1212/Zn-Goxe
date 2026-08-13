import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'database.db')

def init_fogo_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fogo_game_data (
            user_id INTEGER PRIMARY KEY,
            score INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_fogo_db()

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'database.db')

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات الرئيسية"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_goxe_db():
    """تأسيس جداول لعبة Goxe الخاصة بها داخل قاعدة البيانات"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goxe_game_data (
            user_id INTEGER PRIMARY KEY,
            score INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_user_goxe_data(user_id):
    """جلب بيانات مستخدم في لعبة Goxe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM goxe_game_data WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    conn.close()
    if data:
        return dict(data)
    return None

def update_user_goxe_score(user_id, added_score):
    """تحديث نقاط المستخدم في لعبة Goxe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO goxe_game_data (user_id, score) 
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET 
            score = score + excluded.score,
            last_played = CURRENT_TIMESTAMP
    ''', (user_id, added_score))
    conn.commit()
    conn.close()
    return True

import sqlite3

# اسم ملف قاعدة البيانات (هيكون موجود في نفس فولدر البوت)
DB_NAME = "game_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. جدول المستخدمين (الأساس)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            last_claim_time TIMESTAMP,
            is_banned INTEGER DEFAULT 0
        )
    ''')

    # 2. جدول الترقيات (10 مستويات)
    # كل عمود بيمثل عدد الترقيات في المستوى (من 0 لـ 20)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS upgrades (
            telegram_id INTEGER PRIMARY KEY,
            lvl1_count INTEGER DEFAULT 0,
            lvl2_count INTEGER DEFAULT 0,
            lvl3_count INTEGER DEFAULT 0,
            lvl4_count INTEGER DEFAULT 0,
            lvl5_count INTEGER DEFAULT 0,
            lvl6_count INTEGER DEFAULT 0,
            lvl7_count INTEGER DEFAULT 0,
            lvl8_count INTEGER DEFAULT 0,
            lvl9_count INTEGER DEFAULT 0,
            lvl10_count INTEGER DEFAULT 0,
            FOREIGN KEY(telegram_id) REFERENCES users(telegram_id)
        )
    ''')

    # 3. جدول إعدادات الأدمن (التحكم الكامل)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            game_active INTEGER DEFAULT 1,
            global_multiplier REAL DEFAULT 1.0
        )
    ''')
    
    # إضافة صف الإعدادات الافتراضي لو مش موجود
    cursor.execute('INSERT OR IGNORE INTO settings (id, game_active, global_multiplier) VALUES (1, 1, 1.0)')

    conn.commit()
    conn.close()
    print("الأساسات (قاعدة البيانات) اتعملت بنجاح!")

if __name__ == "__main__":
    init_db()

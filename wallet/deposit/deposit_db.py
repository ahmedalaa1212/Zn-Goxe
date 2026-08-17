import sqlite3
import uuid

DB_PATH = 'database.db'
OFFICIAL_TON_WALLET = 'UQCK...VGtc'  # عنوان محفظة TON الرسمية المربوطة

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_deposit_tables():
    """إنشاء جداول الباقات والسجلات تلقائياً وإضافة الباقات الـ 5 إذا لم تكن موجودة"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # جدول باقات الشحن المستقل لسهولة التعديل مستقبلاً
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposit_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usdt_amount REAL NOT NULL,
                name_ar TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0
            )
        ''')

        # جدول سجلات وتتبع عمليات الإيداع
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposit_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                usdt_amount REAL NOT NULL,
                ton_amount REAL NOT NULL,
                memo TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()

        # إضافة الباقات الـ 5 المحددة إن كانت القائمة فارغة
        cursor.execute("SELECT COUNT(*) as count FROM deposit_packages")
        if cursor.fetchone()['count'] == 0:
            default_packages = [
                (0.5, "باقة $0.5 USDT", 1, 1),
                (1.5, "باقة $1.5 USDT", 1, 2),
                (5.0, "باقة $5 USDT", 1, 3),
                (10.0, "باقة $10 USDT", 1, 4),
                (15.0, "باقة $15 USDT", 1, 5)
            ]
            cursor.executemany(
                "INSERT INTO deposit_packages (usdt_amount, name_ar, is_active, sort_order) VALUES (?, ?, ?, ?)",
                default_packages
            )
            conn.commit()
    except Exception as e:
        print(f"Error initializing deposit tables: {e}")
    finally:
        if conn:
            conn.close()

def get_active_deposit_packages():
    """جلب الباقات المتاحة مرتبة"""
    init_deposit_tables()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deposit_packages WHERE is_active = 1 ORDER BY sort_order ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching packages: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_package_by_id(pkg_id: int):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deposit_packages WHERE id = ?", (pkg_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error fetching package: {e}")
        return None
    finally:
        if conn:
            conn.close()

def create_deposit_invoice(user_id: int, usdt_amount: float, ton_amount: float) -> dict:
    """إنشاء وتوثيق فاتورة الإيداع مع توليد رمز Memo فريد"""
    conn = None
    memo = f"DEP-{user_id}-{uuid.uuid4().hex[:6].upper()}"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO deposit_invoices (user_id, usdt_amount, ton_amount, memo) VALUES (?, ?, ?, ?)",
            (user_id, usdt_amount, ton_amount, memo)
        )
        conn.commit()
        return {
            'invoice_id': cursor.lastrowid,
            'user_id': user_id,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'memo': memo
        }
    except Exception as e:
        print(f"Error creating invoice: {e}")
        return {'memo': memo, 'invoice_id': 0, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount}
    finally:
        if conn:
            conn.close()

# تهيئة الجداول تلقائياً عند استدعاء الملف
init_deposit_tables()

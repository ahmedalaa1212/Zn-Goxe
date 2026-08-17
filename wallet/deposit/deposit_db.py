import sqlite3
import uuid

DB_PATH = 'database.db'
OFFICIAL_TON_WALLET = 'UQCK...VGtc'  # عنوان محفظة TON الرسمية

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_deposit_tables():
    """إنشاء ومزامنة مستند deposit_settings في Firebase Firestore وجداول SQLite"""
    # 1. إنشاء ومزامنة المستند في Firebase Firestore تحت مجموعة settings
    try:
        from database import get_db
        fs_db = get_db()
        if fs_db:
            doc_ref = fs_db.collection('settings').document('deposit_settings')
            doc = doc_ref.get()
            if not doc.exists:
                doc_ref.set({
                    'official_ton_wallet': OFFICIAL_TON_WALLET,
                    'packages': [
                        {'id': 1, 'usdt_amount': 0.5, 'name_ar': 'باقة $0.5 USDT', 'is_active': True, 'sort_order': 1},
                        {'id': 2, 'usdt_amount': 1.5, 'name_ar': 'باقة $1.5 USDT', 'is_active': True, 'sort_order': 2},
                        {'id': 3, 'usdt_amount': 5.0, 'name_ar': 'باقة $5 USDT', 'is_active': True, 'sort_order': 3},
                        {'id': 4, 'usdt_amount': 10.0, 'name_ar': 'باقة $10 USDT', 'is_active': True, 'sort_order': 4},
                        {'id': 5, 'usdt_amount': 15.0, 'name_ar': 'باقة $15 USDT', 'is_active': True, 'sort_order': 5}
                    ]
                })
                print("✅ تم إنشاء مستند deposit_settings بنجاح في Firebase Firestore داخل مجموعة settings!")
    except Exception as e:
        print(f"⚠️ تنبيه أثناء إعداد مستند Firebase deposit_settings: {e}")

    # 2. إنشاء الجداول المحلية SQLite
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposit_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usdt_amount REAL NOT NULL,
                name_ar TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0
            )
        ''')

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

        cursor.execute("SELECT COUNT(*) as count FROM deposit_packages")
        if cursor.fetchone()['count'] == 0:
            default_packages = [
                (1, 0.5, "باقة $0.5 USDT", 1, 1),
                (2, 1.5, "باقة $1.5 USDT", 1, 2),
                (3, 5.0, "باقة $5 USDT", 1, 3),
                (4, 10.0, "باقة $10 USDT", 1, 4),
                (5, 15.0, "باقة $15 USDT", 1, 5)
            ]
            cursor.executemany(
                "INSERT OR REPLACE INTO deposit_packages (id, usdt_amount, name_ar, is_active, sort_order) VALUES (?, ?, ?, ?, ?)",
                default_packages
            )
            conn.commit()
    except Exception as e:
        print(f"Error initializing SQLite deposit tables: {e}")
    finally:
        if conn:
            conn.close()

def get_active_deposit_packages():
    """جلب الباقات المتاحة من Firebase أولاً للتزامن اللحظي، ثم SQLite كاحتياطي"""
    init_deposit_tables()
    
    # محاولة الجلب المباشر من Firebase Firestore
    try:
        from database import get_db
        fs_db = get_db()
        if fs_db:
            doc = fs_db.collection('settings').document('deposit_settings').get()
            if doc.exists:
                data = doc.to_dict()
                packages = [p for p in data.get('packages', []) if p.get('is_active', True)]
                if packages:
                    packages.sort(key=lambda x: x.get('sort_order', 0))
                    return packages
    except Exception as e:
        print(f"⚠️ قراءة الباقات من Firebase فشلت، الانتقال للنسخة المحلية: {e}")

    # الاحتياطي المحلي SQLite
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deposit_packages WHERE is_active = 1 ORDER BY sort_order ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching packages: {e}")
        return [
            {'id': 1, 'usdt_amount': 0.5, 'name_ar': 'باقة $0.5 USDT'},
            {'id': 2, 'usdt_amount': 1.5, 'name_ar': 'باقة $1.5 USDT'},
            {'id': 3, 'usdt_amount': 5.0, 'name_ar': 'باقة $5 USDT'},
            {'id': 4, 'usdt_amount': 10.0, 'name_ar': 'باقة $10 USDT'},
            {'id': 5, 'usdt_amount': 15.0, 'name_ar': 'باقة $15 USDT'}
        ]
    finally:
        if conn:
            conn.close()

def get_package_by_id(pkg_id: int):
    packages = get_active_deposit_packages()
    for pkg in packages:
        if int(pkg.get('id', 0)) == int(pkg_id):
            return pkg
    return None

def create_deposit_invoice(user_id: int, usdt_amount: float, ton_amount: float) -> dict:
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

init_deposit_tables()

import sqlite3
import uuid

DB_PATH = 'database.db'
OFFICIAL_TON_WALLET = 'UQCK...VGtc'

DEFAULT_PACKAGES = [
    {'id': 1, 'usdt_amount': 0.5, 'name_ar': 'باقة $0.5 USDT', 'is_active': True, 'sort_order': 1},
    {'id': 2, 'usdt_amount': 1.5, 'name_ar': 'باقة $1.5 USDT', 'is_active': True, 'sort_order': 2},
    {'id': 3, 'usdt_amount': 5.0, 'name_ar': 'باقة $5 USDT', 'is_active': True, 'sort_order': 3},
    {'id': 4, 'usdt_amount': 10.0, 'name_ar': 'باقة $10 USDT', 'is_active': True, 'sort_order': 4},
    {'id': 5, 'usdt_amount': 15.0, 'name_ar': 'باقة $15 USDT', 'is_active': True, 'sort_order': 5}
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_deposit_tables():
    """تجهيز جداول SQLite المحلية للاحتياط"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposit_packages (
                id INTEGER PRIMARY KEY,
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
    except Exception as e:
        print(f"Error initializing SQLite deposit tables: {e}")
    finally:
        if conn:
            conn.close()

def sync_sqlite_with_firebase(packages):
    """تحديث قاعدة البيانات المحلية بالبيانات الجديدة من الفايربيس"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM deposit_packages")
        for p in packages:
            cursor.execute(
                "INSERT INTO deposit_packages (id, usdt_amount, name_ar, is_active, sort_order) VALUES (?, ?, ?, ?, ?)",
                (int(p['id']), float(p['usdt_amount']), str(p['name_ar']), 1 if p.get('is_active') else 0, int(p.get('sort_order', 0)))
            )
        conn.commit()
    except Exception as e:
        print(f"⚠️ خطأ تحديث SQLite المحلي: {e}")
    finally:
        if conn:
            conn.close()

def get_active_deposit_packages():
    """جلب الباقات من Firebase وإنشاء المستند تلقائياً إذا كان مفقوداً"""
    init_deposit_tables()
    
    try:
        from database import get_db
        fs_db = get_db()
        if fs_db:
            doc_ref = fs_db.collection('settings').document('deposit_settings')
            doc = doc_ref.get()
            
            # إذا لم يكن المستند موجوداً في الفايربيس يتم إنشاؤه تلقائياً بالحقول المطلوبة
            if not doc.exists:
                initial_data = {
                    'official_ton_wallet': OFFICIAL_TON_WALLET,
                    'packages': DEFAULT_PACKAGES
                }
                doc_ref.set(initial_data)
                sync_sqlite_with_firebase(DEFAULT_PACKAGES)
                return DEFAULT_PACKAGES

            # في حال وجود المستند يتم قراءته وتحديث القائمة فوراً
            data = doc.to_dict() or {}
            raw_pkgs = data.get('packages', [])
            packages = []
            
            for p in raw_pkgs:
                is_active = p.get('is_active', True)
                if is_active is not False and str(is_active).lower() != 'false':
                    try:
                        pkg_id = int(p.get('id', 0))
                        usdt_amt = float(p.get('usdt_amount', 0))
                        name_ar = str(p.get('name_ar', f"باقة ${usdt_amt} USDT"))
                        sort_order = int(p.get('sort_order', 0))

                        packages.append({
                            'id': pkg_id,
                            'usdt_amount': usdt_amt,
                            'name_ar': name_ar,
                            'is_active': True,
                            'sort_order': sort_order
                        })
                    except (ValueError, TypeError) as err:
                        print(f"⚠️ خطأ في قراءة باقة: {err}")
                        continue

            if packages:
                packages.sort(key=lambda x: x.get('sort_order', 0))
                sync_sqlite_with_firebase(packages)
                return packages
    except Exception as e:
        print(f"⚠️ فشل الاتصال بالفايربيس: {e}")

    # احتياطي محلي في حال انقطاع الخدمة تماماً
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deposit_packages WHERE is_active = 1 ORDER BY sort_order ASC")
        rows = cursor.fetchall()
        if rows:
            return [dict(row) for row in rows]
    except Exception as e:
        pass

    return DEFAULT_PACKAGES

def get_package_by_id(pkg_id):
    if pkg_id is None:
        return None
    packages = get_active_deposit_packages()
    for pkg in packages:
        if str(pkg.get('id')) == str(pkg_id):
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
        return {'memo': memo, 'invoice_id': 0, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount}
    finally:
        if conn:
            conn.close()

init_deposit_tables()

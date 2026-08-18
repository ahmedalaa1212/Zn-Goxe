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

def get_firestore_db():
    """جلب اتصال الفايربيس بجميع الطرق الممكنة لضمان التوصيل المباشر"""
    try:
        import database
        if hasattr(database, 'get_db'):
            db_inst = database.get_db()
            if db_inst:
                return db_inst
        if hasattr(database, 'db') and database.db is not None:
            return database.db
    except Exception as e:
        print(f"⚠️ [Firebase Import database.py]: {e}")

    try:
        import firebase_admin
        from firebase_admin import firestore
        if firebase_admin._apps:
            return firestore.client()
    except Exception as e:
        print(f"⚠️ [Firebase Admin Direct]: {e}")

    return None

def ensure_firebase_deposit_settings():
    """إجبار إنشاء مستند deposit_settings داخل مجموعة settings في الفايربيس فوراً"""
    try:
        fs_db = get_firestore_db()
        if not fs_db:
            print("❌ [Firebase] تعذر الوصول للفايربيس")
            return None
        
        doc_ref = fs_db.collection('settings').document('deposit_settings')
        doc = doc_ref.get()
        
        if not doc.exists:
            initial_data = {
                'official_ton_wallet': OFFICIAL_TON_WALLET,
                'packages': DEFAULT_PACKAGES
            }
            doc_ref.set(initial_data)
            print("🔥 [Firebase] تم إنشاء مستند settings/deposit_settings بنجاح في الفايربيس!")
            return initial_data
        else:
            data = doc.to_dict() or {}
            if 'packages' not in data or not data['packages']:
                doc_ref.set({'packages': DEFAULT_PACKAGES}, merge=True)
                data['packages'] = DEFAULT_PACKAGES
            return data
    except Exception as e:
        print(f"❌ [Firebase Error] أثناء الكشف/الإنشاء: {e}")
        return None

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

def get_official_ton_wallet():
    """جلب عنوان المحفظة الرسمية من الفايربيس"""
    try:
        data = ensure_firebase_deposit_settings()
        if data and data.get('official_ton_wallet'):
            return str(data['official_ton_wallet'])
    except Exception as e:
        print(f"⚠️ خطأ جلب المحفظة من الفايربيس: {e}")
    return OFFICIAL_TON_WALLET

def get_active_deposit_packages():
    """جلب الباقات المتاحة وقراءتها مباشرة من Firebase"""
    init_deposit_tables()
    
    try:
        data = ensure_firebase_deposit_settings()
        if data and 'packages' in data:
            raw_pkgs = data.get('packages', [])
            packages = []
            
            for p in raw_pkgs:
                is_active = p.get('is_active', True)
                if is_active is True or str(is_active).lower() == 'true' or str(is_active) == '1':
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
        print(f"⚠️ فشل جلب الباقات من الفايربيس: {e}")

    # احتياطي محلي في حال تعذر الاتصال بالفايربيس
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
    init_deposit_tables()
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
        print(f"⚠️ خطأ أثناء إنشاء الفاتورة: {e}")
        return {'memo': memo, 'invoice_id': 0, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount}
    finally:
        if conn:
            conn.close()

# تشغيل الفحص والتأكد من وجود المستند فور تحميل الملف في Python
init_deposit_tables()
try:
    ensure_firebase_deposit_settings()
except Exception:
    pass

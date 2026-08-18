import sqlite3
import uuid
import os
import sys
import json
import time
import hashlib

# ضمان الوصول للمجلد الرئيسي (Root) لاستدعاء database.py ومجلد قاعدة البيانات
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

DB_PATH = os.path.join(ROOT_DIR, 'database.db')
OFFICIAL_TON_WALLET = 'UQCK...VGtc'

# كاش مؤقت لإعدادات الفايربيس لتوفير القراءات وتسرع الاستجابة
_SETTINGS_CACHE = None
_SETTINGS_CACHE_TIME = 0
CACHE_TTL_SECONDS = 60  # إعادة التحديث كل 60 ثانية

SEED_PACKAGES = [
    {'id': 1, 'usdt_amount': 0.5, 'is_active': True, 'sort_order': 1},
    {'id': 2, 'usdt_amount': 1.5, 'is_active': True, 'sort_order': 2},
    {'id': 3, 'usdt_amount': 5.0, 'is_active': True, 'sort_order': 3},
    {'id': 4, 'usdt_amount': 10.0, 'is_active': True, 'sort_order': 4},
    {'id': 5, 'usdt_amount': 15.0, 'is_active': True, 'sort_order': 5}
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def get_firestore_db():
    """جلب كائن الفايربيس المباشر من database.py أو التهيئة الذاتية الحرة"""
    try:
        import database
        if hasattr(database, 'get_db'):
            db_inst = database.get_db()
            if db_inst:
                return db_inst
    except Exception as e:
        print(f"⚠️ [deposit_db] خطأ استيراد database.py: {e}")

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred_env = os.getenv('FIREBASE_CREDENTIALS') or os.getenv('FIREBASE_SERVICE_ACCOUNT')
            if cred_env:
                if os.path.exists(cred_env):
                    cred = credentials.Certificate(cred_env)
                else:
                    try:
                        cred_dict = json.loads(cred_env)
                        cred = credentials.Certificate(cred_dict)
                    except Exception:
                        cred = credentials.Certificate(cred_env)
                firebase_admin.initialize_app(cred)
            else:
                service_key_path = os.path.join(ROOT_DIR, "serviceAccountKey.json")
                if os.path.exists(service_key_path):
                    cred = credentials.Certificate(service_key_path)
                    firebase_admin.initialize_app(cred)

        if firebase_admin._apps:
            return firestore.client()
    except Exception as e:
        print(f"⚠️ [deposit_db] خطأ الوصول المباشر لـ Firestore: {e}")

    return None

def get_official_ton_wallet():
    """جلب عنوان المحفظة الحقيقي من متغيرات البيئة في Railway أولاً ثم الفايربيس"""
    env_wallet = os.getenv('PROJECT_WALLET') or os.environ.get('PROJECT_WALLET')
    if env_wallet and str(env_wallet).strip():
        return str(env_wallet).strip()

    try:
        data = ensure_firebase_deposit_settings()
        if data.get('official_ton_wallet'):
            return str(data['official_ton_wallet'])
    except Exception as e:
        print(f"⚠️ خطأ جلب المحفظة: {e}")
        
    return OFFICIAL_TON_WALLET

def ensure_firebase_deposit_settings():
    """التحقق من وجود مستند settings/deposit_settings في الفايربيس استخدام نظام الكاش"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    now = time.time()

    if _SETTINGS_CACHE and (now - _SETTINGS_CACHE_TIME < CACHE_TTL_SECONDS):
        return _SETTINGS_CACHE

    fs_db = get_firestore_db()
    if not fs_db:
        print("⚠️ [deposit_db] تعذر الاتصال بقاعدة الفايربيس، سيتم الاعتماد على الباقات الافتراضية مؤقتاً.")
        return {'official_ton_wallet': get_official_ton_wallet(), 'packages': SEED_PACKAGES}

    try:
        doc_ref = fs_db.collection('settings').document('deposit_settings')
        doc = doc_ref.get()

        if not doc.exists:
            wallet_to_save = get_official_ton_wallet()

            initial_data = {
                'official_ton_wallet': wallet_to_save,
                'packages': SEED_PACKAGES
            }
            doc_ref.set(initial_data)
            _SETTINGS_CACHE = initial_data
            _SETTINGS_CACHE_TIME = now
            print("🔥 [Firebase Success] تم إنشاء مستند settings/deposit_settings بنجاح في الفايربيس تلقائياً!")
            return initial_data
        else:
            _SETTINGS_CACHE = doc.to_dict() or {}
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
    except Exception as e:
        print(f"⚠️ خطأ في إنشاء أو جلب مستند الفايربيس: {e}")
        return {'official_ton_wallet': get_official_ton_wallet(), 'packages': SEED_PACKAGES}

def init_deposit_tables():
    """تجهيز الجداول المحلية للفواتير والتحقق من المعاملات المكررة"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_txs (
                tx_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                usdt_amount REAL NOT NULL,
                memo TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                usd_balance REAL DEFAULT 0.0
            )
        ''')

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN usd_balance REAL DEFAULT 0.0")
        except Exception:
            pass

        conn.commit()
    except Exception as e:
        print(f"Error initializing SQLite deposit tables: {e}")
    finally:
        if conn:
            conn.close()

def verify_and_process_ton_boc(user_id: int, usdt_amount: float, memo: str, boc: str) -> float:
    """
    عملية آمنة لا تقبل التكرار (Firestore Transaction) متوافقة تماماً مع قواعد الفايربيس (قراءة أولاً ثم كتابة).
    """
    if not user_id or usdt_amount <= 0:
        raise ValueError("بيانات المستخدم أو قيمة الباقة غير صحيحة")

    tx_identifier = boc or memo or str(uuid.uuid4())
    tx_hash = hashlib.sha256(tx_identifier.encode('utf-8')).hexdigest()

    fs_db = get_firestore_db()
    if fs_db:
        from firebase_admin import firestore

        @firestore.transactional
        def run_in_transaction(transaction, tx_ref, user_ref):
            # 1. كل عمليات القراءة أولاً (ALL READS FIRST)
            tx_snap = transaction.get(tx_ref)
            if tx_snap.exists:
                raise Exception("هذه المعاملة تم استخدامها وشحنها سابقاً!")

            user_snap = transaction.get(user_ref)

            # حساب الرصيد الجديد قبل تنفيذ عمليات الكتابة
            if user_snap.exists:
                updated_data = user_snap.to_dict() or {}
                current_bal = float(updated_data.get('usd_balance', 0.0) or updated_data.get('usdt_balance', 0.0))
                new_bal = current_bal + usdt_amount
            else:
                new_bal = usdt_amount

            # 2. كل عمليات الكتابة والتحديث ثانياً (ALL WRITES AFTER)
            transaction.set(tx_ref, {
                'tx_hash': tx_hash,
                'user_id': user_id,
                'usdt_amount': usdt_amount,
                'memo': memo,
                'processed_at': firestore.SERVER_TIMESTAMP
            })

            if user_snap.exists:
                transaction.update(user_ref, {
                    'usd_balance': firestore.Increment(usdt_amount),
                    'usdt_balance': firestore.Increment(usdt_amount)
                })
            else:
                transaction.set(user_ref, {
                    'usd_balance': usdt_amount,
                    'usdt_balance': usdt_amount
                }, merge=True)

            return new_bal

        tx_ref = fs_db.collection('processed_txs').document(tx_hash)
        user_ref = fs_db.collection('users').document(str(user_id))

        transaction = fs_db.transaction()
        new_balance = run_in_transaction(transaction, tx_ref, user_ref)
        
        # مزامنة الرصيد محلياً في SQLite أيضاً
        credit_user_balance_sqlite(user_id, usdt_amount)
        return new_balance
    else:
        # البديل في حال عدم الاتصال بالفايربيس
        return credit_user_balance_sqlite(user_id, usdt_amount)

def credit_user_balance_sqlite(user_id: int, usdt_amount: float) -> float:
    conn = None
    new_usd = usdt_amount
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT usd_balance FROM users WHERE tg_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            new_usd = float(row['usd_balance'] or 0.0) + usdt_amount
            cursor.execute("UPDATE users SET usd_balance = ? WHERE tg_id = ?", (user_id, user_id))
        else:
            cursor.execute("INSERT INTO users (tg_id, usd_balance) VALUES (?, ?)", (user_id, usdt_amount))
        conn.commit()
    except Exception as e:
        print(f"⚠️ خطأ تحديث رصيد SQLite: {e}")
    finally:
        if conn:
            conn.close()
    return new_usd

def get_active_deposit_packages():
    """جلب الباقات من الفايربيس"""
    init_deposit_tables()
    data = ensure_firebase_deposit_settings()
    
    raw_pkgs = data.get('packages', [])
    if not raw_pkgs or not isinstance(raw_pkgs, list):
        raw_pkgs = SEED_PACKAGES

    packages = []
    for p in raw_pkgs:
        is_active = p.get('is_active', True)
        if is_active is True or str(is_active).lower() == 'true' or str(is_active) == '1':
            try:
                amt = float(p.get('usdt_amount', 0))
                formatted_amt = f"{amt:g}"
                packages.append({
                    'id': int(p.get('id', 0)),
                    'usdt_amount': amt,
                    'name_ar': f"باقة ${formatted_amt} USDT",
                    'is_active': True,
                    'sort_order': int(p.get('sort_order', 0))
                })
            except (ValueError, TypeError) as err:
                print(f"⚠️ خطأ قراءة باقة من الفايربيس: {err}")
                continue

    packages.sort(key=lambda x: x.get('sort_order', 0))
    return packages

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
        print(f"⚠️ خطأ إنشاء الفاتورة: {e}")
        return {'memo': memo, 'invoice_id': 0, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount}
    finally:
        if conn:
            conn.close()

def credit_user_balance(user_id: int, usdt_amount: float) -> float:
    """تحديث رصيد الدولار فقط للمستخدم دون مس رصيد ZN"""
    if not user_id:
        return 0.0
    return verify_and_process_ton_boc(user_id, usdt_amount, f"MANUAL-{time.time()}", f"BOC-MANUAL-{uuid.uuid4().hex}")

init_deposit_tables()

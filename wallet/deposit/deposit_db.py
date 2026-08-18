import sqlite3
import uuid
import os
import sys
import json
import time
import hashlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

DB_PATH = os.path.join(ROOT_DIR, 'database.db')
OFFICIAL_TON_WALLET = 'UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc'

_SETTINGS_CACHE = None
_SETTINGS_CACHE_TIME = 0
CACHE_TTL_SECONDS = 60

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
    env_wallet = os.getenv('PROJECT_WALLET') or os.getenv('OFFICIAL_TON_WALLET') or os.getenv('TON_WALLET')
    if env_wallet and str(env_wallet).strip():
        return str(env_wallet).strip()

    global _SETTINGS_CACHE
    if _SETTINGS_CACHE and _SETTINGS_CACHE.get('official_ton_wallet'):
        return str(_SETTINGS_CACHE['official_ton_wallet'])

    return OFFICIAL_TON_WALLET

def ensure_firebase_deposit_settings():
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    now = time.time()

    if _SETTINGS_CACHE and (now - _SETTINGS_CACHE_TIME < CACHE_TTL_SECONDS):
        return _SETTINGS_CACHE

    default_wallet = get_official_ton_wallet()
    fallback_settings = {'official_ton_wallet': default_wallet, 'packages': SEED_PACKAGES}

    fs_db = get_firestore_db()
    if not fs_db:
        print("⚠️ [deposit_db] تعذر الاتصال بقاعدة الفايربيس، سيتم الاعتماد على الباقات الافتراضية مؤقتاً.")
        _SETTINGS_CACHE = fallback_settings
        _SETTINGS_CACHE_TIME = now
        return fallback_settings

    try:
        doc_ref = fs_db.collection('settings').document('deposit_settings')
        doc = doc_ref.get()

        if not doc.exists:
            initial_data = {
                'official_ton_wallet': default_wallet,
                'packages': SEED_PACKAGES
            }
            doc_ref.set(initial_data)
            _SETTINGS_CACHE = initial_data
            _SETTINGS_CACHE_TIME = now
            print("🔥 [Firebase Success] تم إنشاء مستند settings/deposit_settings بنجاح في الفايربيس تلقائياً!")
            return initial_data
        else:
            data = doc.to_dict() or {}
            if not data.get('official_ton_wallet'):
                data['official_ton_wallet'] = default_wallet
            if not data.get('packages'):
                data['packages'] = SEED_PACKAGES

            _SETTINGS_CACHE = data
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
    except Exception as e:
        print(f"⚠️ خطأ في إنشاء أو جلب مستند الفايربيس: {e}")
        _SETTINGS_CACHE = fallback_settings
        _SETTINGS_CACHE_TIME = now
        return fallback_settings

def init_deposit_tables():
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
    if not user_id or usdt_amount <= 0:
        raise ValueError("بيانات المستخدم أو قيمة الباقة غير صحيحة")

    tx_identifier = boc or memo or str(uuid.uuid4())
    tx_hash = hashlib.sha256(tx_identifier.encode('utf-8')).hexdigest()

    fs_db = get_firestore_db()
    if fs_db:
        from firebase_admin import firestore

        @firestore.transactional
        def run_in_transaction(transaction, tx_ref, user_ref, user_history_ref):
            tx_snaps = list(transaction.get(tx_ref))
            tx_snap = tx_snaps[0] if tx_snaps else None
            if tx_snap and tx_snap.exists:
                raise ValueError("هذه المعاملة تم استخدامها وشحنها سابقاً!")

            user_snaps = list(transaction.get(user_ref))
            user_snap = user_snaps[0] if user_snaps else None

            if user_snap and user_snap.exists:
                updated_data = user_snap.to_dict() or {}
                current_bal = float(updated_data.get('usd_balance', 0.0) or 0.0)
                new_bal = current_bal + usdt_amount
            else:
                new_bal = usdt_amount

            tx_data = {
                'tx_hash': tx_hash,
                'user_id': user_id,
                'usdt_amount': usdt_amount,
                'memo': memo or '',
                'boc': boc or '',
                'type': 'deposit',
                'status': 'completed',
                'processed_at': firestore.SERVER_TIMESTAMP
            }

            transaction.set(tx_ref, tx_data)
            transaction.set(user_history_ref, tx_data)

            if user_snap and user_snap.exists:
                transaction.update(user_ref, {
                    'usd_balance': firestore.Increment(usdt_amount)
                })
            else:
                transaction.set(user_ref, {
                    'usd_balance': usdt_amount
                }, merge=True)

            return new_bal

        tx_ref = fs_db.collection('processed_txs').document(tx_hash)
        user_ref = fs_db.collection('users').document(str(user_id))
        user_history_ref = user_ref.collection('deposit_history').document(tx_hash)

        transaction = fs_db.transaction()
        new_balance = run_in_transaction(transaction, tx_ref, user_ref, user_history_ref)
        
        credit_user_balance_sqlite(user_id, usdt_amount, tx_hash, memo)
        return new_balance
    else:
        return credit_user_balance_sqlite(user_id, usdt_amount, tx_hash, memo)

def credit_user_balance_sqlite(user_id: int, usdt_amount: float, tx_hash: str = None, memo: str = None) -> float:
    conn = None
    new_usd = usdt_amount
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if tx_hash:
            cursor.execute("INSERT OR IGNORE INTO processed_txs (tx_hash, user_id, usdt_amount, memo) VALUES (?, ?, ?, ?)",
                           (tx_hash, user_id, usdt_amount, memo))

        cursor.execute("SELECT usd_balance FROM users WHERE tg_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            curr_val = float(row['usd_balance'] or 0.0)
            new_usd = curr_val + usdt_amount
            cursor.execute("UPDATE users SET usd_balance = ? WHERE tg_id = ?", (new_usd, user_id))
        else:
            cursor.execute("INSERT INTO users (tg_id, usd_balance) VALUES (?, ?)", (user_id, new_usd))
        conn.commit()
    except Exception as e:
        print(f"⚠️ خطأ تحديث رصيد SQLite: {e}")
    finally:
        if conn:
            conn.close()
    return new_usd

def get_active_deposit_packages():
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
    if not user_id:
        return 0.0
    return verify_and_process_ton_boc(user_id, usdt_amount, f"MANUAL-{time.time()}", f"BOC-MANUAL-{uuid.uuid4().hex}")

init_deposit_tables()

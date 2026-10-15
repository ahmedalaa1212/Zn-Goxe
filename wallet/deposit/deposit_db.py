import os
import sys
import uuid
import time
import hashlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)

try:
    from database import get_db_connection, _sanitize_id
    from wallet.wallet_db import update_user_balance, get_user_wallet_balances
except ImportError as e:
    print(f"⚠️ خطأ في الاستيراد من قاعدة البيانات الرئيسية: {e}")

OFFICIAL_TON_WALLET = 'UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc'

SEED_PACKAGES = [
    {'id': 1, 'usdt_amount': 0.5, 'is_active': True, 'sort_order': 1},
    {'id': 2, 'usdt_amount': 1.5, 'is_active': True, 'sort_order': 2},
    {'id': 3, 'usdt_amount': 5.0, 'is_active': True, 'sort_order': 3},
    {'id': 4, 'usdt_amount': 10.0, 'is_active': True, 'sort_order': 4},
    {'id': 5, 'usdt_amount': 15.0, 'is_active': True, 'sort_order': 5}
]

def init_deposit_tables():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS deposit_packages (
                        id SERIAL PRIMARY KEY,
                        usdt_amount NUMERIC NOT NULL,
                        name_ar VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS deposit_invoices (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        usdt_amount NUMERIC NOT NULL,
                        ton_amount NUMERIC NOT NULL,
                        memo VARCHAR(255) UNIQUE NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        tx_hash VARCHAR(255) PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        usdt_amount NUMERIC NOT NULL,
                        memo TEXT,
                        boc TEXT,
                        type VARCHAR(50) DEFAULT 'deposit',
                        status VARCHAR(50) DEFAULT 'completed',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cur.execute("SELECT COUNT(*) FROM deposit_packages")
                count = cur.fetchone()[0]
                if count == 0:
                    for pkg in SEED_PACKAGES:
                        cur.execute("""
                            INSERT INTO deposit_packages (usdt_amount, name_ar, is_active, sort_order)
                            VALUES (%s, %s, %s, %s)
                        """, (pkg['usdt_amount'], f"باقة ${pkg['usdt_amount']} USDT", pkg['is_active'], pkg['sort_order']))
            conn.commit()
    except Exception as e: print(f"⚠️ خطأ الجداول: {e}")

def get_active_deposit_packages():
    """ضمان الاستعلام اللحظي من Supabase والتأكد من مطابقة الاسم للسعر المعدل"""
    init_deposit_tables()
    packages = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # جلب مباشر بدون كاش (Real-time Fetch)
                cur.execute("""
                    SELECT id, usdt_amount, name_ar, is_active, sort_order 
                    FROM deposit_packages 
                    WHERE is_active = TRUE 
                    ORDER BY sort_order ASC
                """)
                rows = cur.fetchall()
                for row in rows:
                    usdt_amount = float(row[1])
                    # التأكد أن الاسم العربي يتضمن السعر الحقيقي الموجود في الـ DB الآن!
                    current_name = row[2]
                    if not current_name or str(usdt_amount) not in current_name:
                        current_name = f"باقة ${usdt_amount:g} USDT"
                        
                    packages.append({
                        'id': row[0],
                        'usdt_amount': usdt_amount,
                        'name_ar': current_name,
                        'is_active': row[3],
                        'sort_order': row[4]
                    })
        if packages:
            return packages
    except Exception as e:
        print(f"⚠️ خطأ جلب الباقات من قاعدة البيانات: {e}")

    return SEED_PACKAGES

def get_package_by_id(pkg_id):
    if pkg_id is None: return None
    packages = get_active_deposit_packages()
    for pkg in packages:
        if str(pkg.get('id')) == str(pkg_id): return pkg
    return None

def create_deposit_invoice(user_id, usdt_amount: float, ton_amount: float) -> dict:
    init_deposit_tables()
    user_id_clean = _sanitize_id(user_id)
    memo = f"DEP-{user_id_clean}-{uuid.uuid4().hex[:6].upper()}"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deposit_invoices (user_id, usdt_amount, ton_amount, memo)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (user_id_clean, usdt_amount, ton_amount, memo))
                invoice_id = cur.fetchone()[0]
                conn.commit()
        return {'invoice_id': invoice_id, 'user_id': user_id_clean, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount, 'memo': memo}
    except Exception as e:
        return {'memo': memo, 'invoice_id': 0, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount}

def verify_and_process_ton_boc(user_id, usdt_amount: float, memo: str, boc: str) -> float:
    if not user_id or usdt_amount <= 0: raise ValueError("بيانات غير صحيحة")
    user_id_clean = _sanitize_id(user_id)
    tx_hash = hashlib.sha256((boc or memo or str(uuid.uuid4())).encode('utf-8')).hexdigest()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tx_hash FROM processed_txs WHERE tx_hash = %s", (tx_hash,))
                if cur.fetchone(): raise ValueError("هذه المعاملة تم استخدامها مسبقاً!")

                cur.execute("""
                    INSERT INTO processed_txs (tx_hash, user_id, usdt_amount, memo, boc, type, status)
                    VALUES (%s, %s, %s, %s, %s, 'deposit', 'completed')
                """, (tx_hash, user_id_clean, usdt_amount, memo, boc))
                conn.commit()

        # الدالة المحمية بـ GREATEST(0.0) 
        success = update_user_balance(user_id_clean, usdt_amount, currency='usd_balance', operation='add')
        if not success: raise Exception("فشل تحديث الرصيد.")
        
        balances = get_user_wallet_balances(user_id_clean)
        return balances.get('usdt_balance', 0.0)

    except ValueError as ve: raise ve
    except Exception as e: raise Exception("حدث خطأ أثناء معالجة الرصيد.")

def credit_user_balance(user_id, usdt_amount: float) -> float:
    if not user_id: return 0.0
    return verify_and_process_ton_boc(user_id, usdt_amount, f"MANUAL-{time.time()}", f"BOC-{uuid.uuid4().hex}")

init_deposit_tables()

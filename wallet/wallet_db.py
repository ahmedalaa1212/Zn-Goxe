# -*- coding: utf-8 -*-
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from database import get_db_connection, _sanitize_id
except ImportError as e:
    print(f"⚠️ خطأ فادح: لم يتم العثور على database.py: {e}")
    def _sanitize_id(val):
        if val is None: return None
        s = str(val).strip()
        return s[:-2] if s.endswith('.0') else s

# ==========================================
# وظائف المحفظة العامة
# ==========================================
def get_user_wallet_balances(user_id) -> dict:
    clean_id = _sanitize_id(user_id)
    default_balances = {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0, 'db_ok': False}
    if not clean_id: return default_balances

    for attempt in range(2):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COALESCE(balance, 0.0), COALESCE(usd_balance, 0.0), COALESCE(znx_balance, 0.0)
                        FROM users WHERE tg_id = %s OR user_id = %s LIMIT 1
                    """, (clean_id, clean_id))
                    row = cur.fetchone()
                    if row:
                        return {'zn_balance': float(row[0]), 'usdt_balance': float(row[1]), 'znx_balance': float(row[2]), 'db_ok': True}
                    return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0, 'db_ok': True}
        except Exception as e:
            print(f"⚠️ Database Fetch Error: {e}")
    return default_balances

def update_user_balance(user_id, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    clean_id = _sanitize_id(user_id)
    if not clean_id: return False

    curr = str(currency).lower().strip()
    field_to_update = 'balance' if curr in ['zn', 'balance'] else 'znx_balance' if curr in ['znx', 'znx_balance'] else 'usd_balance'
    amount_val = abs(float(amount))
    if operation == 'subtract': amount_val = -amount_val

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE users SET {field_to_update} = GREATEST(0.0, COALESCE({field_to_update}, 0.0) + %s)
                    WHERE tg_id = %s OR user_id = %s RETURNING {field_to_update}
                """, (amount_val, clean_id, clean_id))
                return cur.fetchone() is not None
    except Exception as e:
        print(f"⚠️ Update Balance Error: {e}")
    return False

# ==========================================
# وظائف الإيداع (Supabase) - تم إضافتها
# ==========================================
def init_supabase_deposit_tables():
    """إنشاء جداول الباقات والسجلات تلقائياً في Supabase إذا لم تكن موجودة"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # جدول الباقات للتحكم بالأسعار
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS deposit_packages (
                        id SERIAL PRIMARY KEY,
                        usdt_amount NUMERIC NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0
                    )
                ''')
                # جدول الفواتير
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS deposit_invoices (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        usdt_amount NUMERIC NOT NULL,
                        ton_amount NUMERIC NOT NULL,
                        memo TEXT UNIQUE NOT NULL,
                        status VARCHAR DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # جدول السجلات لمنع تكرار الشحن
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        tx_hash VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        usdt_amount NUMERIC NOT NULL,
                        memo TEXT,
                        boc TEXT,
                        type VARCHAR DEFAULT 'deposit',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # إدخال الباقات الافتراضية إذا كان الجدول فارغاً
                cur.execute("SELECT COUNT(*) FROM deposit_packages")
                if cur.fetchone()[0] == 0:
                    default_packages = [(0.5, 1), (1.5, 2), (5.0, 3), (10.0, 4), (15.0, 5)]
                    for amt, order in default_packages:
                        cur.execute("INSERT INTO deposit_packages (usdt_amount, sort_order) VALUES (%s, %s)", (amt, order))
            conn.commit()
    except Exception as e:
        print(f"⚠️ خطأ في تهيئة جداول الإيداع في Supabase: {e}")

def get_supabase_deposit_packages():
    packages = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, usdt_amount, is_active, sort_order FROM deposit_packages WHERE is_active = TRUE ORDER BY sort_order ASC")
                for row in cur.fetchall():
                    packages.append({
                        'id': row[0],
                        'usdt_amount': float(row[1]),
                        'name_ar': f"باقة ${float(row[1]):g} USDT",
                        'is_active': row[2],
                        'sort_order': row[3]
                    })
    except Exception as e:
        print(f"⚠️ خطأ في جلب الباقات من Supabase: {e}")
    return packages

def create_supabase_deposit_invoice(user_id, usdt_amount, ton_amount, memo):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deposit_invoices (user_id, usdt_amount, ton_amount, memo) 
                    VALUES (%s, %s, %s, %s) RETURNING id
                """, (str(user_id), usdt_amount, ton_amount, memo))
                invoice_id = cur.fetchone()[0]
                conn.commit()
                return invoice_id
    except Exception as e:
        print(f"⚠️ خطأ في إنشاء الفاتورة في Supabase: {e}")
        return 0

def process_supabase_deposit(user_id, usdt_amount, memo, boc, tx_hash):
    """تسجيل المعاملة وإضافة الرصيد في حركة واحدة (Transaction) بأمان"""
    clean_id = _sanitize_id(user_id)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. التحقق من عدم استخدام المعاملة سابقاً
                cur.execute("SELECT tx_hash FROM processed_txs WHERE tx_hash = %s", (tx_hash,))
                if cur.fetchone():
                    raise ValueError("هذه المعاملة تم استخدامها وشحنها سابقاً!")
                
                # 2. تسجيل المعاملة
                cur.execute("""
                    INSERT INTO processed_txs (tx_hash, user_id, usdt_amount, memo, boc)
                    VALUES (%s, %s, %s, %s, %s)
                """, (tx_hash, clean_id, usdt_amount, memo, boc))
                
                # 3. تحديث الفاتورة إن وجدت
                cur.execute("UPDATE deposit_invoices SET status = 'completed' WHERE memo = %s", (memo,))

                # 4. إضافة الرصيد للمستخدم
                cur.execute("""
                    UPDATE users SET usd_balance = COALESCE(usd_balance, 0.0) + %s
                    WHERE tg_id = %s OR user_id = %s RETURNING usd_balance
                """, (usdt_amount, clean_id, clean_id))
                
                new_balance_row = cur.fetchone()
                if not new_balance_row:
                    # إذا لم يكن المستخدم موجوداً في الجدول
                    cur.execute("INSERT INTO users (tg_id, user_id, usd_balance) VALUES (%s, %s, %s) RETURNING usd_balance", (clean_id, clean_id, usdt_amount))
                    new_balance_row = cur.fetchone()
                
                conn.commit()
                return float(new_balance_row[0])
    except Exception as e:
        raise e

# تشغيل التهيئة التلقائية للجداول عند استدعاء الملف
init_supabase_deposit_tables()

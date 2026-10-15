# -*- coding: utf-8 -*-
import os
import sys
import uuid
import time
import hashlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from database import get_db_connection, _sanitize_id, atomic_update_balance, get_user_balances
except ImportError as e:
    print(f"⚠️ خطأ في الاستيراد من database.py: {e}")

SEED_PACKAGES = [
    {'id': 1, 'usdt_amount': 0.5, 'name_ar': 'باقة $0.5 USDT', 'is_active': True, 'sort_order': 1},
    {'id': 2, 'usdt_amount': 1.5, 'name_ar': 'باقة $1.5 USDT', 'is_active': True, 'sort_order': 2},
    {'id': 3, 'usdt_amount': 5.0, 'name_ar': 'باقة $5 USDT', 'is_active': True, 'sort_order': 3},
    {'id': 4, 'usdt_amount': 10.0, 'name_ar': 'باقة $10 USDT', 'is_active': True, 'sort_order': 4},
    {'id': 5, 'usdt_amount': 15.0, 'name_ar': 'باقة $15 USDT', 'is_active': True, 'sort_order': 5}
]

_tables_initialized = False

def get_official_ton_wallet():
    """جلب عنوان محفظة TON للاستلام من متغيرات Railway فقط (بدون أي عناوين ثابتة)"""
    env_wallet = (
        os.getenv('TON_WALLET_ADDRESS')
        or os.getenv('OFFICIAL_TON_WALLET')
        or os.getenv('TON_WALLET')
        or os.getenv('PROJECT_WALLET')
        or ''
    )
    return str(env_wallet).strip()

def init_deposit_tables():
    """تهيئة الجداول والتأكد من وجود كافة الأعمدة في Supabase دون تعارض"""
    global _tables_initialized
    if _tables_initialized:
        return
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. جدول الباقات
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS deposit_packages (
                        id SERIAL PRIMARY KEY,
                        usdt_amount NUMERIC NOT NULL,
                        name_ar VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0
                    )
                ''')
                cur.execute("ALTER TABLE deposit_packages ADD COLUMN IF NOT EXISTS name_ar VARCHAR(255);")
                cur.execute("ALTER TABLE deposit_packages ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")
                cur.execute("ALTER TABLE deposit_packages ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;")

                # 2. جدول الفواتير
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

                # 3. جدول المعاملات المكتملة (متوافق مع database.py)
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        tx_hash VARCHAR(256) PRIMARY KEY,
                        user_id VARCHAR(255),
                        usdt_amount NUMERIC DEFAULT 0.0,
                        memo TEXT,
                        boc TEXT,
                        type VARCHAR(64) DEFAULT 'deposit',
                        status VARCHAR(50) DEFAULT 'completed',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cur.execute("ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS user_id VARCHAR(255);")
                cur.execute("ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS usdt_amount NUMERIC DEFAULT 0.0;")
                cur.execute("ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS memo TEXT;")
                cur.execute("ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS boc TEXT;")
                cur.execute("ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'completed';")

                # إدخال الباقات الافتراضية فقط إذا كان الجدول فارغاً تماماً
                cur.execute("SELECT COUNT(*) FROM deposit_packages")
                count = cur.fetchone()[0]
                if count == 0:
                    for pkg in SEED_PACKAGES:
                        cur.execute("""
                            INSERT INTO deposit_packages (usdt_amount, name_ar, is_active, sort_order)
                            VALUES (%s, %s, %s, %s)
                        """, (pkg['usdt_amount'], f"باقة ${pkg['usdt_amount']:g} USDT", pkg['is_active'], pkg['sort_order']))
            conn.commit()
            _tables_initialized = True
    except Exception as e:
        print(f"⚠️ خطأ في تهيئة جداول الإيداع في Supabase: {e}")

def get_active_deposit_packages():
    """جلب الباقات مباشرة من جدول deposit_packages في Supabase"""
    init_deposit_tables()
    packages = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, usdt_amount, COALESCE(is_active, TRUE), COALESCE(sort_order, id)
                    FROM deposit_packages
                    WHERE COALESCE(is_active, TRUE) = TRUE
                    ORDER BY COALESCE(sort_order, id) ASC, id ASC
                """)
                rows = cur.fetchall()
                for row in rows:
                    pkg_id = row[0]
                    usdt_val = float(row[1])
                    packages.append({
                        'id': pkg_id,
                        'usdt_amount': usdt_val,
                        'name_ar': f"باقة ${usdt_val:g} USDT",
                        'is_active': bool(row[2]),
                        'sort_order': int(row[3])
                    })
        if packages:
            return packages
    except Exception as e:
        print(f"❌ خطأ جلب الباقات من Supabase: {e}")

    return SEED_PACKAGES

def get_package_by_id(pkg_id):
    if pkg_id is None:
        return None
    packages = get_active_deposit_packages()
    for pkg in packages:
        if str(pkg.get('id')) == str(pkg_id):
            return pkg
    return None

def create_deposit_invoice(user_id, usdt_amount: float, ton_amount: float) -> dict:
    """إنشاء فاتورة مبدئية في Supabase"""
    init_deposit_tables()
    user_id_clean = _sanitize_id(user_id) or "0"
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
                
        return {
            'invoice_id': invoice_id,
            'user_id': user_id_clean,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'memo': memo
        }
    except Exception as e:
        print(f"⚠️ خطأ إنشاء الفاتورة: {e}")
        return {'memo': memo, 'invoice_id': 0, 'user_id': user_id_clean, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount}

def verify_and_process_ton_boc(user_id, usdt_amount: float, memo: str, boc: str) -> float:
    """معالجة المعاملة وتحديث رصيد الدولار ذرياً في Supabase"""
    init_deposit_tables()
    user_id_clean = _sanitize_id(user_id)
    if not user_id_clean or usdt_amount <= 0:
        raise ValueError("بيانات المستخدم أو قيمة الباقة غير صحيحة")

    tx_identifier = boc or memo or str(uuid.uuid4())
    tx_hash = hashlib.sha256(tx_identifier.encode('utf-8')).hexdigest()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. التأكد أن المعاملة غير مكررة
                cur.execute("SELECT tx_hash FROM processed_txs WHERE tx_hash = %s", (tx_hash,))
                if cur.fetchone():
                    raise ValueError("هذه المعاملة تم استخدامها وشحنها سابقاً!")

                # 2. تسجيل المعاملة
                cur.execute("""
                    INSERT INTO processed_txs (tx_hash, user_id, usdt_amount, memo, boc, type, status)
                    VALUES (%s, %s, %s, %s, %s, 'deposit', 'completed')
                """, (tx_hash, user_id_clean, usdt_amount, memo, boc))
                
                if memo:
                    cur.execute("UPDATE deposit_invoices SET status = 'completed' WHERE memo = %s", (memo,))
            conn.commit()

        # 3. تحديث الرصيد ذرياً باستخدام الدالة المركزية
        try:
            from wallet.wallet_db import update_user_balance, get_user_wallet_balances
            success = update_user_balance(user_id_clean, usdt_amount, currency='usd_balance', operation='add')
            if success:
                balances = get_user_wallet_balances(user_id_clean)
                return float(balances.get('usdt_balance', 0.0))
        except Exception:
            pass

        # Fallback مباشر لـ database.py لضمان عدم فشل إضافة الرصيد أبداً
        ok, new_bal = atomic_update_balance(user_id_clean, usdt_amount, is_usd=True)
        if not ok:
            raise Exception("فشل تحديث رصيد المستخدم في قاعدة البيانات الرئيسية.")
        return float(new_bal)

    except ValueError as ve:
        raise ve
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة الشحن في Supabase: {e}")
        raise Exception(f"حدث خطأ أثناء معالجة المعاملة: {str(e)}")

def credit_user_balance(user_id, usdt_amount: float) -> float:
    """دالة احتياطية للشحن اليدوي"""
    if not user_id:
        return 0.0
    return verify_and_process_ton_boc(user_id, usdt_amount, f"MANUAL-{time.time()}", f"BOC-MANUAL-{uuid.uuid4().hex}")

init_deposit_tables()

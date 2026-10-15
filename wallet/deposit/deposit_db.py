import os
import sys
import uuid
import time
import hashlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# استيراد دوال الاتصال الرئيسية بالـ DB وتحديث الأرصدة (Supabase)
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
    """تهيئة الجداول وعواميد الباقات والسجلات تلقائياً في Supabase/PostgreSQL"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. إنشاء جدول الباقات (لتحكمك الديناميكي فيها)
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS deposit_packages (
                        id SERIAL PRIMARY KEY,
                        usdt_amount NUMERIC NOT NULL,
                        name_ar VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0
                    )
                ''')
                
                # 2. إنشاء جدول الفواتير (طلبات الدفع المبدئية)
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

                # 3. إنشاء جدول المعاملات المكتملة والسجلات (لمنع الشحن المزدوج)
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
                
                # إدخال الباقات الافتراضية لأول مرة فقط
                cur.execute("SELECT COUNT(*) FROM deposit_packages")
                count = cur.fetchone()[0]
                if count == 0:
                    for pkg in SEED_PACKAGES:
                        cur.execute("""
                            INSERT INTO deposit_packages (usdt_amount, name_ar, is_active, sort_order)
                            VALUES (%s, %s, %s, %s)
                        """, (pkg['usdt_amount'], f"باقة ${pkg['usdt_amount']} USDT", pkg['is_active'], pkg['sort_order']))
            conn.commit()
    except Exception as e:
        print(f"⚠️ خطأ في إنشاء أو تحديث جداول الإيداع في Supabase: {e}")

def get_official_ton_wallet():
    env_wallet = os.getenv('PROJECT_WALLET') or os.getenv('OFFICIAL_TON_WALLET') or os.getenv('TON_WALLET')
    if env_wallet and str(env_wallet).strip():
        return str(env_wallet).strip()
    return OFFICIAL_TON_WALLET

def get_active_deposit_packages():
    """جلب الباقات من Supabase بدلاً من الفايربيس (مع ضمان جلب أحدث البيانات)"""
    init_deposit_tables() # التأكد من وجود الجداول
    packages = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # نجلب البيانات الطازجة من Supabase
                cur.execute("""
                    SELECT id, usdt_amount, name_ar, is_active, sort_order 
                    FROM deposit_packages 
                    WHERE is_active = TRUE 
                    ORDER BY sort_order ASC
                """)
                rows = cur.fetchall()
                for row in rows:
                    packages.append({
                        'id': row[0],
                        'usdt_amount': float(row[1]),
                        # تحديث الاسم العربي تلقائياً إذا لم يكن موجوداً أو كان قديماً ليتطابق مع القيمة الجديدة
                        'name_ar': row[2] if row[2] and str(float(row[1])) in row[2] else f"باقة ${float(row[1]):g} USDT",
                        'is_active': row[3],
                        'sort_order': row[4]
                    })
    except Exception as e:
        print(f"⚠️ خطأ جلب الباقات من قاعدة البيانات: {e}")
        return SEED_PACKAGES

    return packages if packages else SEED_PACKAGES

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
                
        return {
            'invoice_id': invoice_id,
            'user_id': user_id_clean,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'memo': memo
        }
    except Exception as e:
        print(f"⚠️ خطأ إنشاء الفاتورة: {e}")
        return {'memo': memo, 'invoice_id': 0, 'usdt_amount': usdt_amount, 'ton_amount': ton_amount}

def verify_and_process_ton_boc(user_id, usdt_amount: float, memo: str, boc: str) -> float:
    """معالجة المعاملة وتحديث الرصيد عبر ملف wallet_db.py الرئيسي"""
    if not user_id or usdt_amount <= 0:
        raise ValueError("بيانات المستخدم أو قيمة الباقة غير صحيحة")

    user_id_clean = _sanitize_id(user_id)
    tx_identifier = boc or memo or str(uuid.uuid4())
    tx_hash = hashlib.sha256(tx_identifier.encode('utf-8')).hexdigest()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. التأكد أن المعاملة غير مكررة
                cur.execute("SELECT tx_hash FROM processed_txs WHERE tx_hash = %s", (tx_hash,))
                if cur.fetchone():
                    raise ValueError("هذه المعاملة تم استخدامها وشحنها سابقاً!")

                # 2. تسجيل المعاملة في سجلات Supabase
                cur.execute("""
                    INSERT INTO processed_txs (tx_hash, user_id, usdt_amount, memo, boc, type, status)
                    VALUES (%s, %s, %s, %s, %s, 'deposit', 'completed')
                """, (tx_hash, user_id_clean, usdt_amount, memo, boc))
                conn.commit()

        # 3. الاعتماد على الدالة المركزية في wallet_db لإضافة الرصيد للمستخدم
        success = update_user_balance(user_id_clean, usdt_amount, currency='usd_balance', operation='add')
        if not success:
            raise Exception("فشل تحديث رصيد المستخدم في قاعدة البيانات الرئيسية.")
        
        # 4. جلب الرصيد المحدث
        balances = get_user_wallet_balances(user_id_clean)
        return balances.get('usdt_balance', 0.0)

    except ValueError as ve:
        raise ve
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة الشحن في Supabase: {e}")
        raise Exception("حدث خطأ أثناء معالجة المعاملة وتحديث الرصيد.")

def credit_user_balance(user_id, usdt_amount: float) -> float:
    """دالة احتياطية للشحن اليدوي"""
    if not user_id:
        return 0.0
    return verify_and_process_ton_boc(user_id, usdt_amount, f"MANUAL-{time.time()}", f"BOC-MANUAL-{uuid.uuid4().hex}")

# تشغيل التهيئة عند الإقلاع
init_deposit_tables()

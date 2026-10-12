import os
import sys

# توحيد مسار المشروع الرئيسي (Root)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# استيراد الاتصال بقاعدة البيانات PostgreSQL (Supabase)
from database import get_db_connection

# ==================== Sub-Modules Re-exports ====================
try:
    from .deposit.deposit_db import *
except Exception as e:
    print(f"⚠️ تنبيه أثناء تحميل deposit_db في wallet_db: {e}")

try:
    from .history.history_db import *
except Exception as e:
    print(f"⚠️ تنبيه أثناء تحميل history_db في wallet_db: {e}")

try:
    from .withdraw.withdraw_db import *
except Exception as e:
    print(f"⚠️ تنبيه أثناء تحميل withdraw_db في wallet_db: {e}")

# ==================== Helpers لقواعد البيانات ====================

def get_user_wallet_balances(user_id: int) -> dict:
    """
    جلب الأرصدة (ZN, USDT, ZNX) المباشرة من Supabase
    """
    str_user_id = str(user_id)
    default_balances = {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # استعلام مباشر وسريع لجلب الأرصدة الثلاثة
                cur.execute("""
                    SELECT balance, usd_balance, znx_balance 
                    FROM users 
                    WHERE tg_id = %s
                """, (str_user_id,))
                
                row = cur.fetchone()
                if row:
                    return {
                        'zn_balance': float(row[0] or 0.0),
                        'usdt_balance': float(row[1] or 0.0),
                        'znx_balance': float(row[2] or 0.0)
                    }
    except Exception as e:
        print(f"⚠️ خطأ جلب الرصيد من Supabase: {e}")

    return default_balances

def update_user_balance(user_id: int, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """
    تعديل الرصيد في Supabase بتزامن كامل وبشكل ذري (Atomic) لمنع الثغرات
    """
    str_user_id = str(user_id)
    curr = str(currency).lower()
    
    # تحديد العمود المستهدف
    if curr in ['zn', 'balance']:
        field_to_update = 'balance'
    elif curr in ['znx', 'znx_balance', 'total_znx_earned']:
        field_to_update = 'znx_balance'
    else:
        field_to_update = 'usd_balance'

    amount_val = abs(float(amount))
    if operation == 'subtract':
        amount_val = -amount_val

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # استخدام تحديث ذري (Atomic Update) مع دالة GREATEST لمنع الرصيد السالب
                # هذا الاستعلام يقفل الصف لحظياً وينفذ العملية بأمان تام بدون الحاجة لـ Transactions معقدة
                cur.execute(f"""
                    UPDATE users 
                    SET {field_to_update} = GREATEST(0.0, COALESCE({field_to_update}, 0.0) + %s)
                    WHERE tg_id = %s
                    RETURNING {field_to_update}
                """, (amount_val, str_user_id))
                
                updated_row = cur.fetchone()
                if updated_row is not None:
                    return True
                else:
                    print(f"⚠️ لم يتم العثور على المستخدم {str_user_id} لتحديث رصيده.")
                    return False
    except Exception as e:
        print(f"⚠️ خطأ تحديث الرصيد في Supabase: {e}")
        return False

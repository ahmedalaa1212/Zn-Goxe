import os
import sys

# توحيد مسار المشروع الرئيسي (Root)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ==================== استيراد الاتصال المباشر بقاعدة البيانات ====================
try:
    from database import get_db_connection
except ImportError as e:
    print(f"⚠️ خطأ فادح: لم يتم العثور على database.py في الجذر: {e}")

# ==================== Sub-Modules Re-exports ====================
try:
    from .deposit.deposit_db import *
except Exception as e:
    pass

try:
    from .history.history_db import *
except Exception as e:
    pass

try:
    from .withdraw.withdraw_db import *
except Exception as e:
    pass

# ==================== دوال المحفظة الأساسية ====================

def get_user_wallet_balances(user_id) -> dict:
    """
    جلب الأرصدة (ZN, USDT, ZNX) المباشرة من Supabase (PostgreSQL)
    """
    str_user_id = str(user_id).strip()
    default_balances = {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}
    
    if not str_user_id or str_user_id == 'undefined':
        return default_balances

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # استخدام COALESCE بقوة لضمان وجود قيمة رقمية دائماً
                cur.execute("""
                    SELECT COALESCE(balance, 0.0), COALESCE(usd_balance, 0.0), COALESCE(znx_balance, 0.0) 
                    FROM users 
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (str_user_id, str_user_id, str_user_id))
                
                row = cur.fetchone()
                if row:
                    # تحويل صريح إلى float لضمان عدم وجود أخطاء في الـ JSON
                    return {
                        'zn_balance': float(row[0] if row[0] is not None else 0.0),
                        'usdt_balance': float(row[1] if row[1] is not None else 0.0),
                        'znx_balance': float(row[2] if row[2] is not None else 0.0)
                    }
    except Exception as e:
        print(f"⚠️ خطأ جلب الرصيد من Supabase: {e}")

    return default_balances


def update_user_balance(user_id, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """
    تعديل الرصيد في Supabase بشكل ذري وآمن (Atomic Update)
    """
    str_user_id = str(user_id).strip()
    curr = str(currency).lower()
    
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
                cur.execute(f"""
                    UPDATE users 
                    SET {field_to_update} = GREATEST(0.0, COALESCE({field_to_update}, 0.0) + %s)
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    RETURNING {field_to_update}
                """, (amount_val, str_user_id, str_user_id, str_user_id))
                
                updated_row = cur.fetchone()
                if updated_row is not None:
                    return True
                return False
    except Exception as e:
        print(f"⚠️ خطأ تحديث الرصيد في Supabase: {e}")
        return False

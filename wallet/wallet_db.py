import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from database import get_db_connection
except ImportError as e:
    print(f"⚠️ خطأ فادح: لم يتم العثور على database.py: {e}")

try:
    from .deposit.deposit_db import *
except Exception: pass
try:
    from .history.history_db import *
except Exception: pass
try:
    from .withdraw.withdraw_db import *
except Exception: pass

def get_user_wallet_balances(user_id) -> dict:
    """جلب الأرصدة المباشرة من Supabase"""
    str_user_id = str(user_id).strip()
    default_balances = {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}
    
    if not str_user_id or str_user_id in ['None', 'undefined', '']:
        return default_balances

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # استعلام صارم باستخدام tg_id المطابق لقاعدة البيانات
                cur.execute("""
                    SELECT balance, usd_balance, znx_balance 
                    FROM users 
                    WHERE tg_id = %s
                    LIMIT 1
                """, (str_user_id,))
                
                row = cur.fetchone()
                if row:
                    return {
                        'zn_balance': float(row[0] if row[0] is not None else 0.0),
                        'usdt_balance': float(row[1] if row[1] is not None else 0.0),
                        'znx_balance': float(row[2] if row[2] is not None else 0.0)
                    }
    except Exception as e:
        print(f"⚠️ Database Fetch Error: {e}")

    return default_balances

def update_user_balance(user_id, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تحديث الأرصدة في Supabase بأمان"""
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
                    WHERE tg_id = %s
                    RETURNING {field_to_update}
                """, (amount_val, str_user_id))
                
                updated_row = cur.fetchone()
                if updated_row is not None:
                    return True
                return False
    except Exception as e:
        print(f"⚠️ Database Update Error: {e}")
        return False

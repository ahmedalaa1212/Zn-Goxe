import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    # استيراد الدوال المركزية من database.py
    from database import get_db_connection, get_user_balances
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
    """جلب الأرصدة بالاعتماد على الدالة المركزية في database.py لضمان التطابق"""
    try:
        # استخدام الدالة من database.py مباشرة
        return get_user_balances(user_id)
    except Exception as e:
        print(f"⚠️ خطأ في توجيه get_user_wallet_balances: {e}")
        return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}

def update_user_balance(user_id, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تحديث الأرصدة في Supabase بأمان"""
    str_user_id = str(user_id).strip()
    if not str_user_id or str_user_id in ['None', 'undefined', '']:
        return False
        
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
                # تحديث قوي يضمن التطابق مع tg_id أو user_id
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
        print(f"⚠️ Database Update Error: {e}")
        return False

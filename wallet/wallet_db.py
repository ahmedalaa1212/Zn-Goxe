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

def get_user_wallet_balances(user_id) -> dict:
    """جلب الأرصدة المباشرة من Supabase مع دعم البحث في كافة أعمدة المعرف وإعادة المحاولة"""
    clean_id = _sanitize_id(user_id)
    default_balances = {
        'zn_balance': 0.0,
        'usdt_balance': 0.0,
        'znx_balance': 0.0,
        'db_ok': False
    }
    
    if not clean_id:
        return default_balances

    for attempt in range(2):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COALESCE(balance, 0.0), COALESCE(usd_balance, 0.0), COALESCE(znx_balance, 0.0)
                        FROM users 
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        LIMIT 1
                    """, (clean_id, clean_id, clean_id))
                    
                    row = cur.fetchone()
                    if row:
                        return {
                            'zn_balance': float(row[0] if row[0] is not None else 0.0),
                            'usdt_balance': float(row[1] if row[1] is not None else 0.0),
                            'znx_balance': float(row[2] if row[2] is not None else 0.0),
                            'db_ok': True
                        }
                    else:
                        return {
                            'zn_balance': 0.0,
                            'usdt_balance': 0.0,
                            'znx_balance': 0.0,
                            'db_ok': True
                        }
        except Exception as e:
            print(f"⚠️ Database Fetch Error (Attempt {attempt + 1}): {e}")

    return default_balances

def update_user_balance(user_id, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تحديث الأرصدة في Supabase بأمان تام (مستخدم في الإيداع والسحب)"""
    clean_id = _sanitize_id(user_id)
    if not clean_id:
        return False

    curr = str(currency).lower().strip()
    if curr in ['zn', 'balance']:
        field_to_update = 'balance'
    elif curr in ['znx', 'znx_balance', 'total_znx_earned']:
        field_to_update = 'znx_balance'
    else:
        field_to_update = 'usd_balance'

    amount_val = abs(float(amount))
    if operation == 'subtract':
        amount_val = -amount_val

    for attempt in range(2):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        UPDATE users 
                        SET {field_to_update} = GREATEST(0.0, COALESCE({field_to_update}, 0.0) + %s),
                            last_active_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        RETURNING {field_to_update}
                    """, (amount_val, clean_id, clean_id, clean_id))
                    
                    updated_row = cur.fetchone()
                    conn.commit()
                    if updated_row is not None:
                        return True
                    return False
        except Exception as e:
            if conn: conn.rollback()
            print(f"⚠️ Database Update Error (Attempt {attempt + 1}): {e}")

    return False

# الاستيراد الآمن للقوائم الفرعية بعد تعريف الدوال الأساسية لمنع الـ Circular Import
try:
    from .deposit.deposit_db import *
except Exception as e:
    print(f"⚠️ Notice importing deposit_db: {e}")
try:
    from .history.history_db import *
except Exception:
    pass
try:
    from .withdraw.withdraw_db import *
except Exception:
    pass

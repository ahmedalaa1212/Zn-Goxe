# -*- coding: utf-8 -*-
import os
import sys
import math

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from database import get_db_connection, init_user
except ImportError as e:
    print(f"⚠️ خطأ فادح: لم يتم العثور على database.py: {e}")

try:
    from .deposit.deposit_db import *
except Exception:
    pass
try:
    from .history.history_db import *
except Exception:
    pass
try:
    from .withdraw.withdraw_db import *
except Exception:
    pass

def _clean_user_id(user_id) -> str:
    if user_id is None:
        return ""
    s = str(user_id).strip()
    if s.lower() in ('none', 'undefined', 'null', 'nan', ''):
        return ""
    # السماح فقط بالأرقام والمعرفات الآمنة لمنع أي حقن
    return "".join(ch for ch in s if ch.isalnum() or ch in ('_', '-'))

def get_user_wallet_balances(user_id) -> dict:
    """جلب الأرصدة المباشرة من Supabase بسرعة وموثوقية عالية"""
    str_user_id = _clean_user_id(user_id)
    default_balances = {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}
    
    if not str_user_id:
        return default_balances

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # البحث في الأعمدة الثلاثة لضمان العثور على المستخدم دائماً
                cur.execute("""
                    SELECT COALESCE(balance, 0.0), COALESCE(usd_balance, 0.0), COALESCE(znx_balance, 0.0)
                    FROM users 
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (str_user_id, str_user_id, str_user_id))
                
                row = cur.fetchone()
                if row:
                    return {
                        'zn_balance': float(row[0] if row[0] is not None else 0.0),
                        'usdt_balance': float(row[1] if row[1] is not None else 0.0),
                        'znx_balance': float(row[2] if row[2] is not None else 0.0)
                    }
                else:
                    # إذا كان المستخدم جديداً ولم يُسجل بعد، نقوم بتهيئته
                    try:
                        init_user(str_user_id)
                    except Exception:
                        pass
    except Exception as e:
        print(f"⚠️ Database Fetch Error in wallet_db: {e}")

    return default_balances

def update_user_balance(user_id, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تحديث الأرصدة في Supabase بأمان ذري يمنع التلاعب أو الرصيد السالب"""
    str_user_id = _clean_user_id(user_id)
    if not str_user_id:
        return False

    try:
        raw_amount = float(amount)
        if math.isnan(raw_amount) or math.isinf(raw_amount) or raw_amount < 0:
            print("⚠️ محاولة إدخال قيمة غير صالحة في الرصيد!")
            return False
    except (ValueError, TypeError):
        return False

    curr = str(currency).lower().strip()
    if curr in ('zn', 'balance', 'zn_balance'):
        field_to_update = 'balance'
    elif curr in ('znx', 'znx_balance', 'total_znx_earned'):
        field_to_update = 'znx_balance'
    elif curr in ('usd', 'usdt', 'usd_balance', 'usdt_balance'):
        field_to_update = 'usd_balance'
    else:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if operation == 'subtract':
                    # خصم مشروط بتوفر الرصيد الكافي لمنع السحب على المكشوف (Race Condition Protection)
                    cur.execute(f"""
                        UPDATE users 
                        SET {field_to_update} = COALESCE({field_to_update}, 0.0) - %s,
                            last_active_at = CURRENT_TIMESTAMP
                        WHERE (tg_id = %s OR user_id = %s OR telegram_id = %s)
                          AND COALESCE({field_to_update}, 0.0) >= %s
                        RETURNING {field_to_update}
                    """, (raw_amount, str_user_id, str_user_id, str_user_id, raw_amount))
                else:
                    cur.execute(f"""
                        UPDATE users 
                        SET {field_to_update} = GREATEST(0.0, COALESCE({field_to_update}, 0.0) + %s),
                            last_active_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        RETURNING {field_to_update}
                    """, (raw_amount, str_user_id, str_user_id, str_user_id))
                
                updated_row = cur.fetchone()
                return updated_row is not None
    except Exception as e:
        print(f"⚠️ Database Update Error in wallet_db: {e}")
        return False

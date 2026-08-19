import sqlite3
import os
import sys

# توحيد مسار المشروع الرئيسي (Root) لجلب قاعدة SQLite
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

DB_PATH = os.path.join(ROOT_DIR, 'database.db')

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

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_wallet_balances(user_id: int) -> dict:
    """استعلام آمن للأرصدة من قاعدة البيانات الرئيسية مع إعطاء الأولوية للقيم الفعلية غير الصفرية"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT balance, zn_balance, usd_balance, usdt_balance FROM users WHERE user_id = ? OR tg_id = ?", 
            (user_id, user_id)
        )
        row = cursor.fetchone()
        if row:
            keys = row.keys()
            
            # جلب القيم المتاحة
            zn_b = float(row['zn_balance']) if 'zn_balance' in keys and row['zn_balance'] is not None else None
            b = float(row['balance']) if 'balance' in keys and row['balance'] is not None else None
            
            # تحديد رصيد ZN بناءً على القيمة الأكبر أو المتوفرة
            if zn_b is not None and zn_b > 0:
                final_zn = zn_b
            elif b is not None and b > 0:
                final_zn = b
            else:
                final_zn = zn_b if zn_b is not None else (b or 0.0)

            # جلب وتحديد رصيد USDT
            usdt_b = float(row['usdt_balance']) if 'usdt_balance' in keys and row['usdt_balance'] is not None else None
            usd_b = float(row['usd_balance']) if 'usd_balance' in keys and row['usd_balance'] is not None else None
            
            if usdt_b is not None and usdt_b > 0:
                final_usdt = usdt_b
            elif usd_b is not None and usd_b > 0:
                final_usdt = usd_b
            else:
                final_usdt = usdt_b if usdt_b is not None else (usd_b or 0.0)

            return {
                'zn_balance': final_zn,
                'usdt_balance': final_usdt
            }
        return {'zn_balance': 0.0, 'usdt_balance': 0.0}
    except Exception as e:
        print(f"Error reading wallet balances: {e}")
        return {'zn_balance': 0.0, 'usdt_balance': 0.0}
    finally:
        if conn:
            conn.close()

def update_user_balance(user_id: int, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تعديل آمن ومباشر للرصيد مع الحفاظ على تزامن الجداول"""
    conn = None
    curr = str(currency).lower()
    
    if curr in ['zn', 'balance']:
        target_cols = ['zn_balance', 'balance']
    else:
        target_cols = ['usdt_balance', 'usd_balance']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        operator = '+' if operation == 'add' else '-'
        
        set_statements = [f"{col} = MAX(0, COALESCE({col}, 0) {operator} ?)" for col in target_cols]
        set_clause = ", ".join(set_statements)
        
        params = [abs(float(amount))] * len(target_cols) + [user_id, user_id]
        
        query = f"UPDATE users SET {set_clause} WHERE user_id = ? OR tg_id = ?"
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating balance in database: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

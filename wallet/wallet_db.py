import sqlite3

DB_PATH = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_wallet_balances(user_id: int) -> dict:
    """استعلام آمن للأرصدة مع دعم مرن لجميع المسميات"""
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
            zn_val = row['zn_balance'] if 'zn_balance' in keys and row['zn_balance'] is not None else row['balance']
            usdt_val = row['usdt_balance'] if 'usdt_balance' in keys and row['usdt_balance'] is not None else row['usd_balance']
            
            return {
                'zn_balance': float(zn_val or 0.0),
                'usdt_balance': float(usdt_val or 0.0)
            }
        return {'zn_balance': 0.0, 'usdt_balance': 0.0}
    except Exception as e:
        print(f"Error reading wallet balances: {e}")
        return {'zn_balance': 0.0, 'usdt_balance': 0.0}
    finally:
        if conn:
            conn.close()

def update_user_balance(user_id: int, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تعديل آمن ومباشر للرصيد مع الحفاظ على تزامن الجداول بدون تعارض"""
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

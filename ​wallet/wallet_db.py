import sqlite3

DB_PATH = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_wallet_balances(user_id: int) -> dict:
    """استعلام عن أرصدة ZN و USDT من قاعدة البيانات"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT zn_balance, usdt_balance FROM users WHERE user_id = ?", 
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                'zn_balance': float(row['zn_balance'] or 0.0),
                'usdt_balance': float(row['usdt_balance'] or 0.0)
            }
        return {'zn_balance': 0.0, 'usdt_balance': 0.0}
    except Exception as e:
        print(f"Error reading wallet balances: {e}")
        return {'zn_balance': 0.0, 'usdt_balance': 0.0}
    finally:
        conn.close()

def update_user_balance(user_id: int, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تعديل الرصيد (إضافة أو خصم) لكل من ZN أو USDT"""
    conn = get_db_connection()
    cursor = conn.cursor()
    column = 'zn_balance' if currency.lower() == 'zn' else 'usdt_balance'
    
    try:
        operator = '+' if operation == 'add' else '-'
        cursor.execute(
            f"UPDATE users SET {column} = MAX(0, {column} {operator} ?) WHERE user_id = ?",
            (amount, user_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating balance: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

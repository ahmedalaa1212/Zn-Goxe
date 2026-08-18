import sqlite3
import os
import sys
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
DB_PATH = os.path.join(ROOT_DIR, 'database.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def can_user_withdraw_today_utc(user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم قد قام بالسحب اليوم بتوقيت UTC"""
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # استعلام عن أي سحب منفذ أو معلق تم اليوم
        cursor.execute("""
            SELECT COUNT(*) as count FROM processed_txs 
            WHERE user_id = ? AND type = 'withdraw' 
            AND status IN ('completed', 'pending') 
            AND strftime('%Y-%m-%d', created_at) = ?
        """, (user_id, today_utc))
        
        row = cursor.fetchone()
        if row and row['count'] > 0:
            return False
        return True
    except Exception as e:
        print(f"Error checking daily withdraw cap: {e}")
        return True
    finally:
        if conn:
            conn.close()

def get_user_withdrawal_context(user_id: int) -> dict:
    """جلب عدد مرات السحب الناجحة وحالة السحب اليومي"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # جلب عدد السحوبات المكتملة لتعيين المستوى
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM processed_txs 
            WHERE user_id = ? AND type = 'withdraw' AND status = 'completed'
        """, (user_id,))
        cnt_row = cursor.fetchone()
        withdraw_count = cnt_row['cnt'] if cnt_row else 0

        has_withdrawn_today = not can_user_withdraw_today_utc(user_id)

        return {
            'withdraw_count': withdraw_count,
            'has_withdrawn_today': has_withdrawn_today
        }
    except Exception as e:
        print(f"Error in get_user_withdrawal_context: {e}")
        return {'withdraw_count': 0, 'has_withdrawn_today': False}
    finally:
        if conn:
            conn.close()

def execute_withdrawal_transaction(user_id: int, amount_zn: float, fee_zn: float, net_zn: float, usdt_value: float, wallet_address: str, is_auto: bool):
    """تنفيذ المعاملة، خصم الرصيد وتسجيل البيانات فوراً في سجل المعاملات"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. التحقق من رصيد المستخدم
        cursor.execute("SELECT balance, zn_balance FROM users WHERE user_id = ? OR tg_id = ?", (user_id, user_id))
        user_row = cursor.fetchone()
        if not user_row:
            return False, "المستخدم غير موجود", 0

        current_bal = float(user_row['zn_balance'] if 'zn_balance' in user_row.keys() and user_row['zn_balance'] is not None else user_row['balance'] or 0)
        
        if current_bal < amount_zn:
            return False, "الرصيد غير كافٍ", current_bal

        new_balance = current_bal - amount_zn

        # 2. خصم الرصيد
        cursor.execute("""
            UPDATE users 
            SET balance = MAX(0, COALESCE(balance, 0) - ?),
                zn_balance = MAX(0, COALESCE(zn_balance, 0) - ?)
            WHERE user_id = ? OR tg_id = ?
        """, (amount_zn, amount_zn, user_id, user_id))

        status = 'completed' if is_auto else 'pending'
        created_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        # 3. إدراج المعاملة في جدول السجلات processed_txs لتظهر في قائمة History فوراً
        cursor.execute("""
            INSERT INTO processed_txs (user_id, type, amount, usdt_amount, fee, net_amount, wallet_address, status, created_at)
            VALUES (?, 'withdraw', ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, amount_zn, usdt_value, fee_zn, net_zn, wallet_address, status, created_at))

        conn.commit()
        return True, "OK", new_balance

    except Exception as e:
        print(f"Error executing withdrawal: {e}")
        if conn:
            conn.rollback()
        return False, "حدث خطأ أثناء معالجة السحب", 0
    finally:
        if conn:
            conn.close()

import os
import sys

# توحيد مسار المشروع الرئيسي (Root)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

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
def get_firestore_db():
    """محاولة جلب الاتصال بقاعدة بيانات Firebase Firestore"""
    try:
        import firebase_admin
        from firebase_admin import firestore
        if firebase_admin._apps:
            return firestore.client()
    except Exception as e:
        print(f"⚠️ تنبيه الاتصال بـ Firestore: {e}")
    return None

def get_sqlite_conn():
    """الاتصال بقاعدة SQLite كمصدر احتياطي"""
    try:
        import sqlite3
        db_path = os.path.join(ROOT_DIR, 'database.db')
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            return conn
    except Exception as e:
        print(f"⚠️ تنبيه الاتصال بـ SQLite: {e}")
    return None

def get_user_wallet_balances(user_id: int) -> dict:
    """
    جلب الأرصدة (ZN, USDT, ZNX) المباشرة من Firebase Firestore كأولوية قصوى ثم SQLite
    """
    str_user_id = str(user_id)
    
    # 1. القراءة المباشرة واللحظية من Firebase Firestore
    db = get_firestore_db()
    if db:
        try:
            doc_ref = db.collection('users').document(str_user_id)
            doc = doc_ref.get()
            
            data = None
            if doc.exists:
                data = doc.to_dict()
            else:
                # البحث في الفيربيس بناءً على tg_id بالأنواع المختلفة
                query = db.collection('users').where('tg_id', '==', str_user_id).limit(1).get()
                if query:
                    data = query[0].to_dict()
                elif str_user_id.isdigit():
                    query_num = db.collection('users').where('tg_id', '==', int(str_user_id)).limit(1).get()
                    if query_num:
                        data = query_num[0].to_dict()

            if data:
                # 1. ZN Balance
                zn_val = data.get('balance')
                if zn_val is None:
                    zn_val = data.get('zn_balance', 0.0)
                
                # 2. USDT Balance (مع فحص الحقل الرئيسي وحقل upgrades الفرعي إن وجد)
                usdt_val = data.get('usd_balance')
                if usdt_val is None:
                    usdt_val = data.get('usdt_balance')
                if usdt_val is None and isinstance(data.get('upgrades'), dict):
                    usdt_val = data.get('upgrades', {}).get('usd_balance')
                if usdt_val is None:
                    usdt_val = 0.0

                # 3. ZNX Balance
                znx_val = data.get('znx_balance')
                if znx_val is None:
                    znx_val = data.get('total_znx_earned')
                if znx_val is None:
                    znx_val = data.get('znx', 0.0)

                return {
                    'zn_balance': float(zn_val or 0.0),
                    'usdt_balance': float(usdt_val or 0.0),
                    'znx_balance': float(znx_val or 0.0)
                }
        except Exception as e:
            print(f"⚠️ خطأ جلب الرصيد من Firestore: {e}")

    # 2. القراءة من SQLite كخيار احتياطي
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT balance, zn_balance, usd_balance, usdt_balance, znx_balance, total_znx_earned FROM users WHERE user_id = ? OR tg_id = ?", 
                (user_id, str_user_id)
            )
            row = cursor.fetchone()
            if row:
                keys = row.keys()
                zn_val = row['balance'] if 'balance' in keys and row['balance'] is not None else row.get('zn_balance', 0.0)
                usdt_val = row['usd_balance'] if 'usd_balance' in keys and row['usd_balance'] is not None else row.get('usdt_balance', 0.0)
                
                znx_val = 0.0
                if 'znx_balance' in keys and row['znx_balance'] is not None:
                    znx_val = row['znx_balance']
                elif 'total_znx_earned' in keys and row['total_znx_earned'] is not None:
                    znx_val = row['total_znx_earned']

                return {
                    'zn_balance': float(zn_val or 0.0),
                    'usdt_balance': float(usdt_val or 0.0),
                    'znx_balance': float(znx_val or 0.0)
                }
        except Exception as e:
            print(f"⚠️ خطأ جلب الرصيد من SQLite: {e}")
        finally:
            conn.close()

    return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}

def update_user_balance(user_id: int, amount: float, currency: str = 'zn', operation: str = 'add') -> bool:
    """تعديل الرصيد في Firebase Firestore و SQLite لتزامن كامل (ZN, USDT, ZNX)"""
    str_user_id = str(user_id)
    curr = str(currency).lower()
    
    is_zn = curr in ['zn', 'balance']
    is_znx = curr in ['znx', 'znx_balance', 'total_znx_earned']
    
    amount_val = abs(float(amount))
    if operation == 'subtract':
        amount_val = -amount_val

    success = False

    # 1. التحديث في Firebase Firestore
    db = get_firestore_db()
    if db:
        try:
            import firebase_admin
            from firebase_admin import firestore
            
            if is_zn:
                field_to_update = 'balance'
            elif is_znx:
                field_to_update = 'znx_balance'
            else:
                field_to_update = 'usd_balance'

            doc_ref = db.collection('users').document(str_user_id)
            doc_ref.update({
                field_to_update: firestore.Increment(amount_val)
            })
            success = True
        except Exception as e:
            print(f"⚠️ خطأ تحديث الرصيد في Firestore: {e}")

    # 2. التحديث في SQLite للاحتياط
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            if is_zn:
                target_cols = ['zn_balance', 'balance']
            elif is_znx:
                target_cols = ['znx_balance', 'total_znx_earned']
            else:
                target_cols = ['usdt_balance', 'usd_balance']

            operator = '+' if operation == 'add' else '-'
            set_statements = [f"{col} = MAX(0, COALESCE({col}, 0) {operator} ?)" for col in target_cols]
            set_clause = ", ".join(set_statements)
            params = [abs(float(amount))] * len(target_cols) + [user_id, str_user_id]
            
            cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ? OR tg_id = ?", params)
            conn.commit()
            success = True
        except Exception as e:
            print(f"⚠️ خطأ تحديث الرصيد في SQLite: {e}")
        finally:
            conn.close()

    return success

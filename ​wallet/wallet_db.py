import datetime
import database

def save_user_wallet_address(user_id, address):
    """حفظ عنوان محفظة المستخدم الحقيقي في قاعدة البيانات"""
    try:
        user_id = str(user_id).strip()
        user_data = database.get_user(user_id) or {}
        user_data['wallet_address'] = address
        
        if hasattr(database, 'update_user'):
            database.update_user(user_id, {'wallet_address': address})
        elif hasattr(database, 'save_user'):
            database.save_user(user_id, user_data)
        elif hasattr(database, 'set_user_field'):
            database.set_user_field(user_id, 'wallet_address', address)
        elif hasattr(database, 'db') and hasattr(database.db, 'collection'):
            database.db.collection('users').document(user_id).set({'wallet_address': address}, merge=True)
            
        return True
    except Exception as e:
        print(f"❌ Error in save_user_wallet_address: {e}")
        return False

def process_withdrawal_request(user_id, amount, address):
    """
    التحقق من الرصيد الحقيقي للمستخدم في قاعدة البيانات وتحديثه سيرفر-سايد
    """
    try:
        user_id = str(user_id).strip()
        user_data = database.get_user(user_id)
        
        if not user_data:
            return {"success": False, "error": "المستخدم غير موجود في قاعدة البيانات"}

        current_balance = float(user_data.get('balance', 0.0))
        amount = float(amount)

        if amount <= 0:
            return {"success": False, "error": "مبلغ السحب غير صحيح"}

        if current_balance < amount:
            return {
                "success": False, 
                "error": f"رصيدك الحقيقي غير كافٍ لتنفيذ السحب. الرصيد الحالي: {current_balance} ZN"
            }

        new_balance = round(current_balance - amount, 4)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        tx_entry = {
            "type": "withdraw",
            "amount": amount,
            "address": address,
            "date": now_str,
            "status": "pending"
        }

        history = list(user_data.get('history', []))
        history.insert(0, tx_entry)

        update_payload = {
            'balance': new_balance,
            'history': history
        }

        if hasattr(database, 'update_user'):
            database.update_user(user_id, update_payload)
        elif hasattr(database, 'save_user'):
            user_data['balance'] = new_balance
            user_data['history'] = history
            database.save_user(user_id, user_data)
        elif hasattr(database, 'db') and hasattr(database.db, 'collection'):
            database.db.collection('users').document(user_id).set(update_payload, merge=True)

        return {
            "success": True,
            "new_balance": new_balance,
            "message": "تم تقديم طلب السحب بنجاح وحسم المبلغ من رصيدك الحقيقي."
        }
    except Exception as e:
        print(f"❌ Error processing withdrawal: {e}")
        return {"success": False, "error": f"حدث خطأ أثناء معالجة السحب: {str(e)}"}

def get_user_transaction_history(user_id):
    """استرجاع سجل المعاملات الحقيقي للمستخدم من قاعدة البيانات"""
    try:
        user_id = str(user_id).strip()
        user_data = database.get_user(user_id) or {}
        
        history = user_data.get('history', [])
        if isinstance(history, list):
            return history
        return []
    except Exception as e:
        print(f"❌ Error getting transaction history: {e}")
        return []

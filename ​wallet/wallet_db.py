import database

def get_wallet_info(telegram_id):
    """جلب بيانات المحفظة الخاصة باللاعب من قاعدة البيانات"""
    try:
        user_data = database.get_user(telegram_id) or {}
        return {
            "wallet_address": user_data.get('wallet_address'),
            "balance": float(user_data.get('balance', 0.0)),
            "usd_balance": float(user_data.get('usd_balance', 0.0))
        }
    except Exception as e:
        print(f"❌ Error in get_wallet_info for {telegram_id}: {e}")
        return {"wallet_address": None, "balance": 0.0, "usd_balance": 0.0}

def save_wallet_address(telegram_id, wallet_address):
    """حفظ أو تحديث عنوان محفظة TON الخاصة باللاعب"""
    try:
        if hasattr(database, 'update_user'):
            database.update_user(telegram_id, {"wallet_address": wallet_address})
        elif hasattr(database, 'db') and database.db:
            database.db.collection('users').document(str(telegram_id)).update({
                "wallet_address": wallet_address
            })
        return True
    except Exception as e:
        print(f"❌ Error in save_wallet_address for {telegram_id}: {e}")
        return False

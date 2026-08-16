import database

def get_user_wallet_balances(telegram_id):
    """جلب الأرصدة المتاحة في محفظة المستخدم"""
    user_data = database.get_user(telegram_id)
    if not user_data:
        return {"balance": 0.0, "usd_balance": 0.0, "ad_balance": 0.0}
        
    return {
        "balance": float(user_data.get('balance', 0.0)),
        "usd_balance": float(user_data.get('usd_balance', 0.0)),
        "ad_balance": float(user_data.get('ad_balance', 0.0))
    }

def update_user_wallet_address(telegram_id, wallet_address):
    """تحديث عنوان محفظة المستخدم (مثل TON Wallet)"""
    try:
        return database.update_user(telegram_id, {"wallet_address": wallet_address})
    except Exception as e:
        print(f"❌ Error updating wallet address for {telegram_id}: {e}")
        return False

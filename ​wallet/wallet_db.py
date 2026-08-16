# wallet/wallet_db.py
import database

def set_user_wallet_address(tg_id, wallet_address):
    """ربط/تحديث عنوان محفظة المستخدم الرئيسي"""
    try:
        if not tg_id or not wallet_address:
            return False, "عنوان المحفظة غير صالح"

        database.update_user(tg_id, {"wallet_address": str(wallet_address).strip()})
        return True, "تم حفظ عنوان المحفظة بنجاح!"
    except Exception as e:
        print(f"❌ Error setting wallet address for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}"

def get_user_wallet_summary(tg_id):
    """جلب ملخص بيانات المحفظة للمستخدم"""
    try:
        user_data = database.get_user(tg_id) or {}
        return {
            "balance_zn": float(user_data.get("balance", 0.0)),
            "balance_usd": float(user_data.get("usd_balance", 0.0)),
            "wallet_address": user_data.get("wallet_address", None)
        }
    except Exception as e:
        print(f"❌ Error getting wallet summary for {tg_id}: {e}")
        return {"balance_zn": 0.0, "balance_usd": 0.0, "wallet_address": None}


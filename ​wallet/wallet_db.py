# wallet/wallet_db.py
import os
import sys

# ضمان استيراد database من المجلد الجذر
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

import database

def get_wallet_info(telegram_id):
    """جلب تفاصيل المحفظة والأرصدة المتاحة للمستخدم من قاعدة البيانات"""
    try:
        user = database.get_user(str(telegram_id))
        if not user:
            return None
            
        return {
            "balance": float(user.get("balance", 0.0)),
            "usd_balance": float(user.get("usd_balance", 0.0)),
            "ton_address": user.get("ton_address", ""),
            "stars_balance": int(user.get("stars_balance", 0))
        }
    except Exception as e:
        print(f"❌ Wallet DB Error: {e}")
        return None

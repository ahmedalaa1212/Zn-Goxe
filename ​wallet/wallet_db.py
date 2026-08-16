import os
import sys

# ربط قاعدة البيانات الرئيسية بالمحفظة
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database

def get_wallet_overview(telegram_id):
    """جلب نظرة عامة على المحفظة للمستخدم"""
    user_data = database.get_user(telegram_id)
    if user_data:
        return {
            "balance": user_data.get('balance', 0.0),
            "usd_balance": user_data.get('usd_balance', 0.0),
            "wallet_address": user_data.get('wallet_address', None)
        }
    return None

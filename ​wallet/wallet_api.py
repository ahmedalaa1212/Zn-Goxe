# wallet/wallet_api.py
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user

# استيراد مرن ومضمون لملف wallet_db
try:
    from wallet.wallet_db import get_wallet_info
except Exception:
    try:
        from wallet_db import get_wallet_info
    except Exception as e:
        print(f"⚠️ تعذر استيراد wallet_db: {e}")
        get_wallet_info = None

wallet_bp = Blueprint('wallet', __name__)

# ==========================================
# 🔄 تسجيل المسارات الفرعية (تغليف آمن بمنع الكسر)
# ==========================================
try:
    from wallet.deposit.deposit_api import deposit_bp
    wallet_bp.register_blueprint(deposit_bp, url_prefix='/deposit')
    print("✅ تم ربط موديول الإيداع (deposit) بالمحفظة الرئيسية")
except Exception as e:
    print(f"⚠️ تعذر تحميل موديول الإيداع: {e}")

try:
    from wallet.withdraw.withdraw_api import withdraw_bp
    wallet_bp.register_blueprint(withdraw_bp, url_prefix='/withdraw')
    print("✅ تم ربط موديول السحب (withdraw) بالمحفظة الرئيسية")
except Exception as e:
    print(f"⚠️ تعذر تحميل موديول السحب: {e}")

try:
    from wallet.history.history_api import history_bp
    wallet_bp.register_blueprint(history_bp, url_prefix='/history')
    print("✅ تم ربط موديول السجلات (history) بالمحفظة الرئيسية")
except Exception as e:
    print(f"⚠️ تعذر تحميل موديول السجلات: {e}")

# ==========================================
# 🌐 المسار الرئيسي للمحفظة
# ==========================================
@wallet_bp.route('/', methods=['GET', 'POST'])
@wallet_bp.route('/info', methods=['GET', 'POST'])
def get_main_wallet_info():
    """جلب ملخص بيانات المحفظة والأرصدة للمستخدم"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    
    if not success:
        req_json = request.get_json(silent=True) if request.is_json else {}
        tg_id_param = request.args.get('tg_id') or req_json.get('tg_id')
        if tg_id_param:
            telegram_id = str(tg_id_param).strip()
        else:
            return error_res

    if get_wallet_info is None:
        return jsonify({"success": False, "error": "خدمة المحفظة غير متوفرة حالياً"}), 500

    wallet_data = get_wallet_info(telegram_id)
    if wallet_data is None:
        return jsonify({"success": False, "error": "الحساب غير موجود"}), 404

    return jsonify({
        "success": True, 
        "message": "Wallet Main API Hub is Active!",
        "wallet": wallet_data
    }), 200

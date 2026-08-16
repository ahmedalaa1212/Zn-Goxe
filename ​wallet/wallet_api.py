import os
import sys

from flask import Blueprint, jsonify, request

# Ensure the project root is importable without adding wallet/ itself to sys.path.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(CURRENT_DIR)

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from core.security import get_authenticated_user

try:
    from wallet.wallet_db import get_wallet_info
except Exception as exc:
    print(f"⚠️ تعذر استيراد wallet_db: {exc}")
    get_wallet_info = None


wallet_bp = Blueprint("wallet", __name__)


# Register wallet submodules.
try:
    from wallet.deposit.deposit_api import deposit_bp

    wallet_bp.register_blueprint(deposit_bp, url_prefix="/deposit")
    print("✅ تم ربط موديول الإيداع (deposit) بالمحفظة الرئيسية")
except Exception as exc:
    print(f"⚠️ تعذر تحميل موديول الإيداع: {exc}")

try:
    from wallet.withdraw.withdraw_api import withdraw_bp

    wallet_bp.register_blueprint(withdraw_bp, url_prefix="/withdraw")
    print("✅ تم ربط موديول السحب (withdraw) بالمحفظة الرئيسية")
except Exception as exc:
    print(f"⚠️ تعذر تحميل موديول السحب: {exc}")

try:
    from wallet.history.history_api import history_bp

    wallet_bp.register_blueprint(history_bp, url_prefix="/history")
    print("✅ تم ربط موديول السجلات (history) بالمحفظة الرئيسية")
except Exception as exc:
    print(f"⚠️ تعذر تحميل موديول السجلات: {exc}")


@wallet_bp.route("/", methods=["GET", "POST"])
@wallet_bp.route("/info", methods=["GET", "POST"])
def get_main_wallet_info():
    """Return the authenticated user's wallet summary."""
    success, telegram_id, user_info, error_response = get_authenticated_user(request)

    if not success:
        return error_response

    if get_wallet_info is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "خدمة المحفظة غير متوفرة حالياً",
                }
            ),
            500,
        )

    wallet_data = get_wallet_info(telegram_id)

    if wallet_data is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "الحساب غير موجود",
                }
            ),
            404,
        )

    return (
        jsonify(
            {
                "success": True,
                "message": "Wallet Main API Hub is Active!",
                "wallet": wallet_data,
            }
        ),
        200,
    )

from flask import Blueprint, request, jsonify

# استدعاء أمان المصادقة بشكل مرن
try:
    from core.security import get_authenticated_user
except ImportError:
    try:
        from security import get_authenticated_user
    except ImportError:
        get_authenticated_user = None

# استدعاء ملف قواعد بيانات المحفظة بشكل محصن يمنع No module named 'wallet'
try:
    from wallet.wallet_db import save_user_wallet_address, process_withdrawal_request, get_user_transaction_history
except (ImportError, ValueError):
    try:
        from .wallet_db import save_user_wallet_address, process_withdrawal_request, get_user_transaction_history
    except (ImportError, ValueError):
        from wallet_db import save_user_wallet_address, process_withdrawal_request, get_user_transaction_history

wallet_bp = Blueprint('wallet', __name__)

def get_auth_user_id(is_post=True):
    """استخراج المعرف الخاص بالمستخدم بأمان من Telegram Auth مع دعم الاحتياط"""
    try:
        if get_authenticated_user:
            success, telegram_id, user_info, _ = get_authenticated_user(request, is_post=is_post)
            if success and telegram_id:
                return str(telegram_id)
    except Exception as e:
        print(f"⚠️ Warning in Auth extraction: {e}")
        
    header_id = request.headers.get('X-Telegram-User-Id')
    req_json = request.get_json(silent=True) if request.is_json else {}
    param_id = request.args.get('tg_id') or request.args.get('user_id') or (req_json.get('user_id') if isinstance(req_json, dict) else None)
    
    return str(header_id or param_id or '') if (header_id or param_id) else None

@wallet_bp.route('/save_address', methods=['POST'])
def save_address():
    """حفظ عنوان محفظة المستخدم (المسار النهائي: /api/wallet/save_address)"""
    try:
        user_id = get_auth_user_id(is_post=True)
        data = request.get_json(silent=True) or {}
        wallet_address = data.get('wallet_address') or data.get('address')

        if not user_id:
            return jsonify({"success": False, "error": "غير مسموح، لم يتم التعرف على المستخدم"}), 401

        if not wallet_address:
            return jsonify({"success": False, "error": "عنوان المحفظة مفقود"}), 400

        res = save_user_wallet_address(user_id, wallet_address)
        if res:
            return jsonify({"success": True, "message": "تم حفظ عنوان المحفظة بنجاح"}), 200
        else:
            return jsonify({"success": False, "error": "فشل حفظ العنوان في قاعدة البيانات"}), 500
    except Exception as e:
        print(f"❌ Error in save_address: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@wallet_bp.route('/withdraw', methods=['POST'])
def withdraw():
    """معالجة طلب السحب (المسار النهائي: /api/wallet/withdraw)"""
    try:
        user_id = get_auth_user_id(is_post=True)
        if not user_id:
            return jsonify({"success": False, "error": "غير مسموح، لم يتم التعرف على المستخدم"}), 401

        data = request.get_json(silent=True) or {}
        try:
            amount = float(data.get('amount', 0))
        except (ValueError, TypeError):
            amount = 0.0

        address = data.get('address') or data.get('wallet_address')

        if amount <= 0 or not address:
            return jsonify({"success": False, "error": "المبلغ أو عنوان المحفظة غير صحيح"}), 400

        result = process_withdrawal_request(user_id, amount, address)
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"❌ Error in withdraw: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@wallet_bp.route('/history', methods=['GET'])
def history():
    """جلب سجل معاملات المستخدم (المسار النهائي: /api/wallet/history)"""
    try:
        user_id = get_auth_user_id(is_post=False)
        if not user_id:
            return jsonify({"success": False, "error": "لم يتم التعرف على المستخدم", "history": []}), 401

        history_data = get_user_transaction_history(user_id)
        return jsonify({"success": True, "history": history_data}), 200
    except Exception as e:
        print(f"❌ Error in history: {e}")
        return jsonify({"success": False, "error": str(e), "history": []}), 500

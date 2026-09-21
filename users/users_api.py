from flask import Blueprint, jsonify, request
import users.users_db as users_db

users_bp = Blueprint('users_api', __name__)

@users_bp.route('/api/users', methods=['GET'])
def api_get_all_users():
    """جلب جميع بيانات المستخدمين كاملة من قواعد البيانات"""
    try:
        users = users_db.get_all_users_admin(limit=1000)
        return jsonify({"success": True, "users": users})
    except Exception as e:
        print(f"❌ Error in /api/users: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@users_bp.route('/api/users/<tg_id>/action', methods=['POST'])
def api_user_action(tg_id):
    """تنفيذ العمليات على حساب المستخدم (حظر، فك حظر، إضافة/خصم رصيد)"""
    try:
        data = request.get_json() or {}
        action = data.get('action')
        value = data.get('value', 0)

        if not tg_id:
            return jsonify({"success": False, "message": "معرف المستخدم مطلوب"}), 400

        if action == 'ban':
            success, msg = users_db.ban_user(tg_id, True)
        elif action == 'unban':
            success, msg = users_db.ban_user(tg_id, False)
        elif action == 'add_balance':
            user = users_db.get_user(tg_id)
            if not user:
                return jsonify({"success": False, "message": "المستخدم غير موجود"}), 404
            
            current_bal = float(user.get('balance', 0.0) or 0.0)
            new_bal = current_bal + float(value)
            success = users_db.update_user(tg_id, {"balance": new_bal})
            msg = "تمت إضافة الرصيد بنجاح"
        elif action == 'deduct_balance':
            user = users_db.get_user(tg_id)
            if not user:
                return jsonify({"success": False, "message": "المستخدم غير موجود"}), 404
            
            current_bal = float(user.get('balance', 0.0) or 0.0)
            new_bal = max(0.0, current_bal - float(value))
            success = users_db.update_user(tg_id, {"balance": new_bal})
            msg = "تم خصم الرصيد بنجاح"
        else:
            return jsonify({"success": False, "message": "إجراء غير معروف"}), 400

        return jsonify({"success": success, "message": msg})
    except Exception as e:
        print(f"❌ Error in /api/users/{tg_id}/action: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

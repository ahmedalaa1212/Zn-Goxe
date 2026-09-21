from flask import Blueprint, jsonify
import users.users_db as users_db

users_bp = Blueprint('users_api', __name__)

@users_bp.route('/api/users', methods=['GET'])
def api_get_all_users():
    """جلب جميع مستخدمين الفايربيس بكافة بياناتهم الكاملة"""
    try:
        users = users_db.get_all_users_admin(limit=2000)
        return jsonify({"success": True, "count": len(users), "users": users})
    except Exception as e:
        print(f"❌ Error in /api/users: {e}")
        return jsonify({"success": False, "message": f"حدث خطأ في السيرفر: {str(e)}"}), 500

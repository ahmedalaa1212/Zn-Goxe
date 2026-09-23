from flask import Blueprint, jsonify, request
import users.users_db as users_db

users_bp = Blueprint('users_api', __name__)

@users_bp.route('/api/users', methods=['GET'])
def api_get_all_users():
    """جلب جميع مستخدمين الفايربيس بكافة بياناتهم الكاملة مع دعم التكبير والفلترة"""
    try:
        # جلب حد زمني كبير لضمان جلب كافة المستخدمين في القاعدة
        limit = request.args.get('limit', default=5000, type=int)
        users = users_db.get_all_users_admin(limit=limit)
        return jsonify({
            "success": True, 
            "count": len(users), 
            "users": users
        })
    except Exception as e:
        print(f"❌ Error in /api/users: {e}")
        return jsonify({
            "success": False, 
            "message": f"حدث خطأ في السيرفر: {str(e)}"
        }), 500

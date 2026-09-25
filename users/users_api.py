from flask import Blueprint, jsonify, request, make_response
import users.users_db as users_db

users_bp = Blueprint('users_api', __name__)

@users_bp.route('/api/users', methods=['GET'])
def api_get_all_users():
    """جلب جميع مستخدمين الفايربيس بكافة بياناتهم المجمعة والمدققة حيوياً في الوقت الفعلي"""
    try:
        limit = request.args.get('limit', default=5000, type=int)
        users = users_db.get_all_users_admin(limit=limit)
        
        response = make_response(jsonify({
            "success": True, 
            "count": len(users), 
            "users": users
        }))
        
        # منع التخزين المؤقت لتحديث البيانات بشكل حيويلحظي
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        print(f"❌ Error in /api/users: {e}")
        return jsonify({
            "success": False, 
            "message": f"حدث خطأ في السيرفر: {str(e)}"
        }), 500

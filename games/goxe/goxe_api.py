from flask import Blueprint, jsonify, request
from games.goxe.goxe_db import init_goxe_db, get_user_goxe_data, update_user_goxe_score

# إنشاء Blueprint خاص بلعبة Goxe
goxe_bp = Blueprint('goxe', __name__, url_prefix='/api/games/goxe')

# تهيئة جدول اللعبة عند بدء التشغيل
init_goxe_db()

@goxe_bp.route('/user_data', methods=['GET'])
def user_data():
    """إرجاع بيانات اللاعب في لعبة Goxe"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "user_id مطلوب"}), 400
    
    data = get_user_goxe_data(user_id)
    return jsonify({"success": True, "data": data}), 200

@goxe_bp.route('/add_score', methods=['POST'])
def add_score():
    """إضافة نقاط للاعب في لعبة Goxe"""
    req_data = request.get_json() or {}
    user_id = req_data.get('user_id')
    points = req_data.get('points', 0)

    if not user_id:
        return jsonify({"success": False, "message": "user_id مطلوب"}), 400

    update_user_goxe_score(user_id, points)
    return jsonify({"success": True, "message": "تم تحديث النقاط بنجاح"}), 200

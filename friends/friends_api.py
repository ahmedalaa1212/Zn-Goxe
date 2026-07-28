from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from database import db
from google.cloud import firestore

friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "الحساب غير موجود"}), 404

        user_data = user_doc.to_dict()
        pending = float(user_data.get("pending_ref_earnings", 0.0))
        
        if pending <= 0:
            return jsonify({"success": False, "error": "لا توجد أرباح معلقة للسحب."}), 400

        # خصم 1.5% رسوم
        fee = pending * 0.015
        net_amount = pending - fee
        new_balance = float(user_data.get("balance", 0.0)) + net_amount

        user_ref.update({
            "balance": new_balance,
            "pending_ref_earnings": 0.0
        })

        return jsonify({"success": True, "net_amount": net_amount, "new_balance": new_balance}), 200
    except Exception as e:
        print(f"Error claim ref earnings: {e}")
        return jsonify({"success": False, "error": "خطأ في معالجة السحب"}), 500

@friends_bp.route('/claim_ref_task', methods=['POST'])
def claim_ref_task():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: return error_response

    data = request.get_json() or {}
    task_id = data.get('taskId')
    reward = float(data.get('reward', 0))
    req_friends = int(data.get('reqFriends', 0))

    if not task_id:
        return jsonify({"success": False, "error": "بيانات المهمة غير مكتملة"}), 400

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "الحساب غير موجود"}), 404

        user_data = user_doc.to_dict()
        current_friends = int(user_data.get("invited_friends_count", 0))
        claimed_tasks = user_data.get("claimed_ref_tasks", [])

        if task_id in claimed_tasks:
            return jsonify({"success": False, "error": "لقد قمت باستلام هذه المكافأة مسبقاً!"}), 400

        if current_friends < req_friends:
            return jsonify({"success": False, "error": "لم تكمل عدد الأصدقاء المطلوب!"}), 400

        new_balance = float(user_data.get("balance", 0.0)) + reward
        claimed_tasks.append(task_id)

        user_ref.update({
            "balance": new_balance,
            "claimed_ref_tasks": claimed_tasks
        })

        return jsonify({"success": True, "new_balance": new_balance}), 200
    except Exception as e:
        print(f"Error claim ref task: {e}")
        return jsonify({"success": False, "error": "خطأ في معالجة المكافأة"}), 500

@friends_bp.route('/list', methods=['POST'])
def get_friends_list():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: return error_response

    try:
        # جلب كل المستخدمين الذين تسجلوا عن طريق هذا اللاعب
        friends_query = db.collection('users').where('referred_by', '==', telegram_id).stream()
        friends_list = []
        for f in friends_query:
            f_data = f.to_dict()
            upgrades = f_data.get('upgrades', {})
            friends_list.append({
                "id": f.id,
                "name": f_data.get('first_name', 'صديق'),
                "generated": float(f_data.get('generated_for_inviter', 0.0)),
                "upgrades_count": len(upgrades)
            })
        
        # ترتيب من الأعلى ربحاً إلى الأقل
        friends_list = sorted(friends_list, key=lambda x: x['generated'], reverse=True)
        return jsonify({"success": True, "friends": friends_list}), 200
    except Exception as e:
        print(f"Error fetching friends list: {e}")
        return jsonify({"success": False, "error": "خطأ في جلب الأصدقاء"}), 500

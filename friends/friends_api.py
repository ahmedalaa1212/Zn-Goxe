from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from database import db

friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/data', methods=['GET', 'POST'])
def get_friends_data():
    """مسار مستقل لجلب بيانات صفحة الأصدقاء فقط"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404
            
        user_data = user_doc.to_dict()
        return jsonify({
            "success": True,
            "player": {
                "balance": user_data.get('balance', 0),
                "pending_ref_earnings": user_data.get('pending_ref_earnings', 0),
                "invited_friends_count": user_data.get('invited_friends_count', 0),
                "claimed_ref_tasks": user_data.get('claimed_ref_tasks', [])
            }
        }), 200
    except Exception as e:
        print(f"Error in friends/data: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم"}), 500

@friends_bp.route('/list', methods=['GET', 'POST'])
def get_friends_list():
    """جلب سجل الأصدقاء"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        friends_query = db.collection('users').where('referred_by', '==', str(user_id)).stream()
        
        friends_list = []
        for doc in friends_query:
            f_data = doc.to_dict()
            
            upgrades = f_data.get('upgrades', {})
            total_upgrades = 0
            if isinstance(upgrades, dict):
                for k, v in upgrades.items():
                    try: total_upgrades += int(v)
                    except: pass
            
            friends_list.append({
                "name": f_data.get('first_name', 'صديق'),
                "upgrades_count": total_upgrades,
                "generated": f_data.get('generated_for_inviter', 0)
            })
            
        return jsonify({"success": True, "friends": friends_list}), 200
    except Exception as e:
        print(f"Error in friends/list: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم"}), 500

@friends_bp.route('/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    """سحب الأرباح مع خصم 1.5%"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "حساب المستخدم غير موجود"}), 404
            
        user_data = user_doc.to_dict()
        pending_earnings = float(user_data.get('pending_ref_earnings', 0))
        current_balance = float(user_data.get('balance', 0))
        
        if pending_earnings <= 0:
            return jsonify({"success": False, "error": "لا توجد أرباح معلقة للسحب"}), 400
            
        fee_percentage = 0.015
        net_amount = pending_earnings - (pending_earnings * fee_percentage)
        new_balance = current_balance + net_amount
        
        user_ref.update({
            'balance': new_balance,
            'pending_ref_earnings': 0
        })
        
        return jsonify({
            "success": True, 
            "new_balance": new_balance,
            "net_amount": net_amount
        }), 200
    except Exception as e:
        print(f"Error in claim_ref_earnings: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية السحب"}), 500

@friends_bp.route('/claim_ref_task', methods=['POST'])
def claim_ref_task():
    """استلام مكافآت الإنجازات"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        data = request.get_json()
        task_id = int(data.get('taskId', 0))
        expected_reward = float(data.get('reward', 0))
        req_friends = int(data.get('reqFriends', 0))
        
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "حساب المستخدم غير موجود"}), 404
            
        user_data = user_doc.to_dict()
        invited_count = int(user_data.get('invited_friends_count', 0))
        claimed_tasks = user_data.get('claimed_ref_tasks', [])
        current_balance = float(user_data.get('balance', 0))
        
        if invited_count < req_friends:
            return jsonify({"success": False, "error": "لم تصل للعدد المطلوب من الأصدقاء بعد"}), 400
            
        if task_id in claimed_tasks:
            return jsonify({"success": False, "error": "تم استلام هذه المكافأة مسبقاً"}), 400
            
        new_balance = current_balance + expected_reward
        claimed_tasks.append(task_id)
        
        user_ref.update({
            'balance': new_balance,
            'claimed_ref_tasks': claimed_tasks
        })
        
        return jsonify({"success": True, "new_balance": new_balance}), 200
    except Exception as e:
        print(f"Error in claim_ref_task: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500

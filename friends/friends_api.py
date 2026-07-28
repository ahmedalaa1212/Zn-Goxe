from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from database import db

friends_bp = Blueprint('friends', __name__)

def get_user_upgrades_count(user_data):
    """حساب إجمالي ترقيات سرعة التعدين للمستخدم"""
    upgrades = user_data.get('upgrades', {})
    total = 0
    if isinstance(upgrades, dict):
        for k, v in upgrades.items():
            try:
                total += int(v)
            except (ValueError, TypeError):
                pass
    elif isinstance(upgrades, (int, float)):
        total = int(upgrades)
    return total

@friends_bp.route('/data', methods=['GET', 'POST'])
def get_friends_data():
    """جلب بيانات صفحة الأصدقاء وإحصائيات المهام"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            user_data = {
                'balance': 0,
                'pending_ref_earnings': 0,
                'claimed_ref_tasks': []
            }
        else:
            user_data = user_doc.to_dict() or {}
        
        # حصر عدد الأصدقاء الإجمالي والأصدقاء المؤهلين للمهام (3 ترقيات فأكثر)
        friends_query = db.collection('users').where('referred_by', '==', str(user_id)).stream()
        
        total_friends_count = 0
        eligible_task_friends_count = 0
        
        for doc in friends_query:
            total_friends_count += 1
            f_data = doc.to_dict() or {}
            if get_user_upgrades_count(f_data) >= 3:
                eligible_task_friends_count += 1
        
        return jsonify({
            "success": True,
            "player": {
                "balance": user_data.get('balance', 0),
                "pending_ref_earnings": user_data.get('pending_ref_earnings', 0),
                "invited_friends_count": total_friends_count,
                "eligible_task_friends_count": eligible_task_friends_count,
                "claimed_ref_tasks": user_data.get('claimed_ref_tasks', [])
            }
        }), 200
    except Exception as e:
        print(f"Error in friends/data: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم"}), 500

@friends_bp.route('/list', methods=['GET', 'POST'])
def get_friends_list():
    """جلب سجل الأصدقاء بالتفصيل"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        friends_query = db.collection('users').where('referred_by', '==', str(user_id)).stream()
        
        friends_list = []
        for doc in friends_query:
            f_data = doc.to_dict() or {}
            total_upgrades = get_user_upgrades_count(f_data)
            
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
    """سحب الأرباح مع خصم 1.5% رسوم تحويل"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "حساب المستخدم غير موجود"}), 404
            
        user_data = user_doc.to_dict() or {}
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
    """استلام مكافآت الإنجازات مع التحقق من شرط الـ 3 ترقيات لكل صديق"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        data = request.get_json(silent=True) or {}
        task_id = int(data.get('taskId', 0))
        expected_reward = float(data.get('reward', 0))
        req_friends = int(data.get('reqFriends', 0))
        
        # التحقق في السيرفر من عدد الأصدقاء الذين اشتروا 3 ترقيات أو أكثر
        friends_query = db.collection('users').where('referred_by', '==', str(user_id)).stream()
        eligible_friends = 0
        for doc in friends_query:
            if get_user_upgrades_count(doc.to_dict() or {}) >= 3:
                eligible_friends += 1

        if eligible_friends < req_friends:
            return jsonify({
                "success": False, 
                "error": f"يلزم {req_friends} أصدقاء قاموا بشراء 3 ترقيات تعدين على الأقل!"
            }), 400

        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "حساب المستخدم غير موجود"}), 404
            
        user_data = user_doc.to_dict() or {}
        claimed_tasks = user_data.get('claimed_ref_tasks', [])
        current_balance = float(user_data.get('balance', 0))
        
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

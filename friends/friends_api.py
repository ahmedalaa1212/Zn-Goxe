# friends/friends_api.py
from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from database import db
from firebase_admin import firestore

friends_bp = Blueprint('friends', __name__)

REF_TASKS_CONFIG = {
    1: {"reqFriends": 1, "reward": 5000},
    2: {"reqFriends": 5, "reward": 30000},
    3: {"reqFriends": 10, "reward": 75000},
    4: {"reqFriends": 25, "reward": 200000},
    5: {"reqFriends": 50, "reward": 500000},
    6: {"reqFriends": 100, "reward": 1500000},
    7: {"reqFriends": 500, "reward": 10000000}
}

def get_user_upgrades_count(user_data):
    """حساب إجمالي ترقيات سرعة التعدين للمستخدم"""
    upgrades = user_data.get('upgrades', {})
    total = 0
    if isinstance(upgrades, dict):
        if 'upgrades_count' in upgrades:
            return int(upgrades['upgrades_count'])
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
            
        user_id_str = str(user_id)
        user_ref = db.collection('users').document(user_id_str)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            user_data = {'balance': 0, 'pending_ref_earnings': 0, 'claimed_ref_tasks': []}
        else:
            user_data = user_doc.to_dict() or {}
        
        friends_query = db.collection('users').where('referred_by', '==', user_id_str).stream()
        
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
                "balance": float(user_data.get('balance', 0)),
                "pending_ref_earnings": float(user_data.get('pending_ref_earnings', 0)),
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
    """جلب سجل الأصدقاء بالتفصيل وحل مشكلة عدم ظهور جميع الدعوات"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        user_id_str = str(user_id)
        
        referred_users = {}
        users_query = db.collection('users').where('referred_by', '==', user_id_str).stream()
        for doc in users_query:
            referred_users[doc.id] = doc.to_dict() or {}
            
        sub_friends = {}
        sub_query = db.collection('users').document(user_id_str).collection('friends').stream()
        for doc in sub_query:
            sub_friends[doc.id] = doc.to_dict() or {}
            
        friends_list = []
        all_friend_ids = set(referred_users.keys()).union(set(sub_friends.keys()))
        
        for f_id in all_friend_ids:
            main_data = referred_users.get(f_id, {})
            sub_data = sub_friends.get(f_id, {})
            total_upgrades = get_user_upgrades_count(main_data)
            
            f_name = main_data.get('first_name') or main_data.get('name') or sub_data.get('first_name') or sub_data.get('name') or 'صديق'
            generated_amount = float(sub_data.get('earned_from_him', main_data.get('ref_generated_amount', 0)))
            
            friends_list.append({
                "name": f_name,
                "upgrades_count": total_upgrades,
                "generated": generated_amount
            })
            
        friends_list.sort(key=lambda x: x['generated'], reverse=True)
            
        return jsonify({"success": True, "friends": friends_list}), 200
    except Exception as e:
        print(f"Error in friends/list: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم"}), 500

@friends_bp.route('/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    """سحب أرباح الإحالات وتحويلها لرصيد حساب المستخدم بشكل آمن"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        user_ref = db.collection('users').document(str(user_id))

        @firestore.transactional
        def run_claim_earnings_transaction(transaction, u_ref):
            snapshot = u_ref.get(transaction=transaction)
            if not snapshot.exists:
                return False, "حساب المستخدم غير موجود", 404, 0, 0
                
            u_data = snapshot.to_dict() or {}
            pending_earnings = float(u_data.get('pending_ref_earnings', 0))
            current_balance = float(u_data.get('balance', 0))
            
            if pending_earnings <= 0:
                return False, "لا توجد أرباح معلقة للسحب", 400, 0, 0
                
            fee_percentage = 0.015
            net_amount = pending_earnings * (1.0 - fee_percentage)
            new_balance = current_balance + net_amount
            
            transaction.update(u_ref, {
                'balance': new_balance,
                'pending_ref_earnings': 0
            })
            
            return True, None, 200, new_balance, net_amount

        transaction = db.transaction()
        success, error_msg, status_code, new_balance, net_amount = run_claim_earnings_transaction(transaction, user_ref)

        if not success:
            return jsonify({"success": False, "error": error_msg}), status_code

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
    """استلام مكافأة مهمة الإحالة"""
    try:
        is_valid, user_id, error_resp = get_authenticated_user(request, is_post=True)
        if not is_valid:
            return error_resp
            
        data = request.get_json(silent=True) or {}
        try:
            task_id = int(data.get('taskId', 0))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "معرف المهمة غير صالح"}), 400
            
        task_config = REF_TASKS_CONFIG.get(task_id)
        if not task_config:
            return jsonify({"success": False, "error": "المهمة غير موجودة"}), 404

        req_friends = task_config['reqFriends']
        task_reward = task_config['reward']

        friends_query = db.collection('users').where('referred_by', '==', str(user_id)).stream()
        eligible_friends = 0
        for doc in friends_query:
            if get_user_upgrades_count(doc.to_dict() or {}) >= 3:
                eligible_friends += 1

        if eligible_friends < req_friends:
            return jsonify({
                "success": False, 
                "error": f"يلزم {req_friends} أصدقاء قاموا بشراء 3 ترقيات على الأقل!"
            }), 400

        user_ref = db.collection('users').document(str(user_id))

        @firestore.transactional
        def run_claim_task_transaction(transaction, u_ref):
            snapshot = u_ref.get(transaction=transaction)
            if not snapshot.exists:
                return False, "حساب المستخدم غير موجود", 404, 0
                
            u_data = snapshot.to_dict() or {}
            claimed_tasks = u_data.get('claimed_ref_tasks', [])
            if not isinstance(claimed_tasks, list):
                claimed_tasks = []

            if task_id in claimed_tasks:
                return False, "تم استلام هذه المكافأة مسبقاً", 400, 0
                
            current_balance = float(u_data.get('balance', 0))
            new_balance = current_balance + task_reward
            claimed_tasks.append(task_id)
            
            transaction.update(u_ref, {
                'balance': new_balance,
                'claimed_ref_tasks': claimed_tasks
            })
            
            return True, None, 200, new_balance

        transaction = db.transaction()
        success, error_msg, status_code, new_balance = run_claim_task_transaction(transaction, user_ref)

        if not success:
            return jsonify({"success": False, "error": error_msg}), status_code

        return jsonify({"success": True, "new_balance": new_balance}), 200

    except Exception as e:
        print(f"Error in claim_ref_task: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500

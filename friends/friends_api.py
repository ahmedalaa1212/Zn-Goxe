import time
from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from database import db, get_game_settings
from firebase_admin import firestore

friends_bp = Blueprint('friends', __name__)

# --- Server-Side RAM Caching Systems ---
_CONFIG_CACHE = {"data": None, "timestamp": 0}
_USER_DATA_CACHE = {}  # {user_id: {"data": response_dict, "timestamp": float}}
_USER_LIST_CACHE = {}  # {user_id: {"data": response_dict, "timestamp": float}}

CACHE_TTL_CONFIG = 600  # 10 دقائق لكاش الإعدادات العامة
CACHE_TTL_USER = 180    # 3 دقائق لكاش استعلامات الأصدقاء غير الحساسة

def invalidate_user_cache(user_id):
    """إبطال كاش المستخدم فوراً عند إجراء عملية مالية حية"""
    user_id_str = str(user_id)
    _USER_DATA_CACHE.pop(user_id_str, None)
    _USER_LIST_CACHE.pop(user_id_str, None)

def get_friends_config():
    """جلب إعدادات نظام الإحالات مع التخزين المؤقت بالسيرفر (10 دقائق)"""
    now = time.time()
    if _CONFIG_CACHE["data"] and (now - _CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _CONFIG_CACHE["data"]

    settings = get_game_settings() or {}
    config = settings.get('friends_config', {
        "commission_percent": 10,
        "claim_fee_percent": 1.5,
        "min_upgrades_for_task": 3,
        "ref_tasks": {
            "1": {"reqFriends": 1, "reward": 4000},
            "2": {"reqFriends": 5, "reward": 25000},
            "3": {"reqFriends": 10, "reward": 60000},
            "4": {"reqFriends": 25, "reward": 160000},
            "5": {"reqFriends": 50, "reward": 350000},
            "6": {"reqFriends": 100, "reward": 800000},
            "7": {"reqFriends": 500, "reward": 4500000}
        }
    })
    _CONFIG_CACHE["data"] = config
    _CONFIG_CACHE["timestamp"] = now
    return config

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
    try:
        is_post = (request.method == 'POST')
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res
            
        user_id_str = str(user_id)
        now = time.time()

        cached_entry = _USER_DATA_CACHE.get(user_id_str)
        if cached_entry and (now - cached_entry["timestamp"] < CACHE_TTL_USER):
            return jsonify(cached_entry["data"]), 200

        user_ref = db.collection('users').document(user_id_str)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            user_data = {'balance': 0, 'pending_ref_earnings': 0, 'claimed_ref_tasks': []}
        else:
            user_data = user_doc.to_dict() or {}
        
        friends_config = get_friends_config()
        min_upgrades = int(friends_config.get('min_upgrades_for_task', 3))

        friends_query = db.collection('users').where('referred_by', '==', user_id_str).stream()
        
        total_friends_count = 0
        eligible_task_friends_count = 0
        
        for doc in friends_query:
            total_friends_count += 1
            f_data = doc.to_dict() or {}
            if get_user_upgrades_count(f_data) >= min_upgrades:
                eligible_task_friends_count += 1
        
        res_data = {
            "success": True,
            "player": {
                "balance": round(float(user_data.get('balance', 0)), 2),
                "pending_ref_earnings": round(float(user_data.get('pending_ref_earnings', 0)), 2),
                "invited_friends_count": total_friends_count,
                "eligible_task_friends_count": eligible_task_friends_count,
                "claimed_ref_tasks": user_data.get('claimed_ref_tasks', [])
            },
            "friends_config": friends_config
        }

        _USER_DATA_CACHE[user_id_str] = {"data": res_data, "timestamp": now}

        return jsonify(res_data), 200
    except Exception as e:
        print(f"Error in friends/data: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم"}), 500

@friends_bp.route('/list', methods=['GET', 'POST'])
def get_friends_list():
    try:
        is_post = (request.method == 'POST')
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res
            
        user_id_str = str(user_id)
        now = time.time()

        cached_entry = _USER_LIST_CACHE.get(user_id_str)
        if cached_entry and (now - cached_entry["timestamp"] < CACHE_TTL_USER):
            return jsonify(cached_entry["data"]), 200
        
        referred_users = {}
        users_query = db.collection('users').where('referred_by', '==', user_id_str).stream()
        for doc in users_query:
            referred_users[doc.id] = doc.to_dict() or {}
            
        sub_friends = {}
        sub_query = db.collection('users').document(user_id_str).collection('friends').stream()
        for doc in sub_query:
            sub_friends[doc.id] = doc.to_dict() or {}

        old_ref_query = db.collection('users').document(user_id_str).collection('referrals').stream()
        for doc in old_ref_query:
            f_id = doc.id
            old_d = doc.to_dict() or {}
            if f_id not in sub_friends:
                sub_friends[f_id] = old_d
            else:
                current_val = float(sub_friends[f_id].get('earned_from_him', 0))
                old_val = float(old_d.get('earned_from_friend') or old_d.get('earned_amount') or 0)
                sub_friends[f_id]['earned_from_him'] = current_val + old_val
            
        friends_list = []
        all_friend_ids = set(referred_users.keys()).union(set(sub_friends.keys()))
        
        for f_id in all_friend_ids:
            main_data = referred_users.get(f_id, {})
            sub_data = sub_friends.get(f_id, {})
            total_upgrades = get_user_upgrades_count(main_data)
            
            f_name = (main_data.get('first_name') or 
                      main_data.get('name') or 
                      sub_data.get('first_name') or 
                      sub_data.get('name') or 
                      'صديق')
            
            earned_val = (sub_data.get('earned_from_him') if sub_data.get('earned_from_him') is not None else
                          sub_data.get('earned_from_friend') if sub_data.get('earned_from_friend') is not None else
                          main_data.get('ref_generated_amount', 0))
            
            try:
                generated_amount = round(float(earned_val), 2)
            except (ValueError, TypeError):
                generated_amount = 0.0
            
            friends_list.append({
                "id": f_id,
                "name": f_name,
                "upgrades_count": total_upgrades,
                "generated": generated_amount
            })
            
        friends_list.sort(key=lambda x: x['generated'], reverse=True)
        res_data = {"success": True, "friends": friends_list}

        _USER_LIST_CACHE[user_id_str] = {"data": res_data, "timestamp": now}
            
        return jsonify(res_data), 200
    except Exception as e:
        print(f"Error in friends/list: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم"}), 500

@friends_bp.route('/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res
            
        user_ref = db.collection('users').document(str(user_id))
        friends_config = get_friends_config()
        fee_percentage = float(friends_config.get('claim_fee_percent', 1.5)) / 100.0

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
                
            net_amount = pending_earnings * (1.0 - fee_percentage)
            new_balance = current_balance + net_amount
            
            transaction.update(u_ref, {
                'balance': new_balance,
                'pending_ref_earnings': 0
            })
            
            return True, None, 200, new_balance, net_amount

        transaction = db.transaction()
        success_tr, error_msg, status_code, new_balance, net_amount = run_claim_earnings_transaction(transaction, user_ref)

        if not success_tr:
            return jsonify({"success": False, "error": error_msg}), status_code

        invalidate_user_cache(user_id)

        return jsonify({
            "success": True, 
            "new_balance": round(new_balance, 2),
            "net_amount": round(net_amount, 2),
            "pending_ref_earnings": 0.0
        }), 200

    except Exception as e:
        print(f"Error in claim_ref_earnings: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية السحب"}), 500

@friends_bp.route('/claim_ref_task', methods=['POST'])
def claim_ref_task():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res
            
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = {}

        try:
            task_id = str(data.get('taskId', '0'))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "معرف المهمة غير صالح"}), 400
            
        friends_config = get_friends_config()
        ref_tasks = friends_config.get('ref_tasks', {})
        
        task_config = ref_tasks.get(task_id) or ref_tasks.get(int(task_id) if task_id.isdigit() else task_id)
        if not task_config:
            return jsonify({"success": False, "error": "المهمة غير موجودة"}), 404

        req_friends = int(task_config['reqFriends'])
        task_reward = float(task_config['reward'])
        min_upgrades = int(friends_config.get('min_upgrades_for_task', 3))

        friends_query = db.collection('users').where('referred_by', '==', str(user_id)).stream()
        eligible_friends = 0
        for doc in friends_query:
            if get_user_upgrades_count(doc.to_dict() or {}) >= min_upgrades:
                eligible_friends += 1

        if eligible_friends < req_friends:
            return jsonify({
                "success": False, 
                "error": f"يلزم {req_friends} أصدقاء قاموا بشراء {min_upgrades} ترقيات على الأقل!"
            }), 400

        user_ref = db.collection('users').document(str(user_id))

        @firestore.transactional
        def run_claim_task_transaction(transaction, u_ref):
            snapshot = u_ref.get(transaction=transaction)
            if not snapshot.exists:
                return False, "حساب المستخدم غير موجود", 404, 0, []
                
            u_data = snapshot.to_dict() or {}
            claimed_tasks = u_data.get('claimed_ref_tasks', [])
            if not isinstance(claimed_tasks, list):
                claimed_tasks = []

            task_id_parsed = int(task_id) if task_id.isdigit() else task_id
            if task_id in claimed_tasks or task_id_parsed in claimed_tasks:
                return False, "تم استلام هذه المكافأة مسبقاً", 400, 0, []
                
            current_balance = float(u_data.get('balance', 0))
            new_balance = current_balance + task_reward
            claimed_tasks.append(task_id_parsed)
            
            transaction.update(u_ref, {
                'balance': new_balance,
                'claimed_ref_tasks': claimed_tasks
            })
            
            return True, None, 200, new_balance, claimed_tasks

        transaction = db.transaction()
        success_tr, error_msg, status_code, new_balance, updated_claimed_tasks = run_claim_task_transaction(transaction, user_ref)

        if not success_tr:
            return jsonify({"success": False, "error": error_msg}), status_code

        invalidate_user_cache(user_id)

        return jsonify({
            "success": True, 
            "new_balance": round(new_balance, 2),
            "claimed_ref_tasks": updated_claimed_tasks
        }), 200

    except Exception as e:
        print(f"Error in claim_ref_task: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500

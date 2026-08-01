# games/games_api.py
import time
import random
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db, get_game_settings
from core.security import get_authenticated_user

games_bp = Blueprint('games', __name__)

def get_arena_settings():
    settings = get_game_settings()
    return settings.get('arena_config', {
        "entry_fee": 1000,
        "round_duration": 900,
        "min_participants": 20,
        "lock_seconds": 15
    })

def get_current_round_info():
    config = get_arena_settings()
    round_duration = config.get("round_duration", 900)
    current_time = int(time.time())
    round_id_num = current_time // round_duration
    end_time = (round_id_num + 1) * round_duration
    return str(round_id_num), end_time, current_time, round_id_num, config

@games_bp.route('/status', methods=['POST'])
def arena_status():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res
        
        round_id, end_time, current_time, round_id_num, config = get_current_round_info()
        
        for i in range(1, 4):
            past_id = str(round_id_num - i)
            past_round_ref = db.collection('arena_rounds').document(past_id)
            past_doc = past_round_ref.get()
            if past_doc.exists and past_doc.to_dict().get('status') == 'active':
                resolve_round(past_id, config)

        round_ref = db.collection('arena_rounds').document(round_id)
        round_doc = round_ref.get()
        
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
        has_joined = any(p['uid'] == uid for p in participants)
        
        user_doc = db.collection('users').document(uid).get()
        balance = user_doc.to_dict().get('balance', 0) if user_doc.exists else 0

        total_collected = len(participants) * config.get("entry_fee", 1000)
        visible_prize_pool = int(total_collected * 0.45)

        return jsonify({
            "success": True,
            "round_id": round_id,
            "end_time": end_time,
            "prize_pool": visible_prize_pool,
            "has_joined": has_joined,
            "balance": balance,
            "entry_fee": config.get("entry_fee", 1000)
        })
    except Exception as e:
        print(f"Error in arena_status: {e}")
        return jsonify({"success": False, "message": "خطأ في الاتصال بالخادم."}), 500

@games_bp.route('/join', methods=['POST'])
def join_arena():
    success, uid, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    round_id, end_time, current_time, _, config = get_current_round_info()
    entry_fee = config.get("entry_fee", 1000)
    lock_seconds = config.get("lock_seconds", 15)
    
    if current_time >= (end_time - lock_seconds):
        return jsonify({"success": False, "message": "تم إغلاق باب الاشتراك لهذه الجولة! انتظر الجولة القادمة."})
        
    round_ref = db.collection('arena_rounds').document(round_id)
    user_ref = db.collection('users').document(uid)
    
    @firestore.transactional
    def join_transaction(transaction, round_ref, user_ref):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return False, "المستخدم غير موجود.", 0
            
        user_data = user_doc.to_dict()
        current_balance = user_data.get('balance', 0)
        
        if current_balance < entry_fee:
            return False, f"رصيدك غير كافٍ للاشتراك (تحتاج {entry_fee:,} ZN).", current_balance
            
        round_doc = round_ref.get(transaction=transaction)
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
            
        if any(p['uid'] == uid for p in participants):
            return False, "أنت مشترك بالفعل في هذه الجولة.", current_balance
            
        player_name = user_data.get('first_name') or user_data.get('name') or f"لاعب #{uid[:5]}"
        new_balance = current_balance - entry_fee
        
        transaction.update(user_ref, {'balance': new_balance})
        
        participants.append({"uid": uid, "name": player_name})
        transaction.set(round_ref, {'participants': participants, 'status': 'active'}, merge=True)
        return True, "تم دخول الساحة بنجاح!", new_balance
        
    try:
        success_join, msg, new_bal = join_transaction(db.transaction(), round_ref, user_ref)
        res_payload = {"success": success_join, "message": msg}
        if success_join:
            res_payload["new_balance"] = new_bal
        return jsonify(res_payload)
    except Exception as e:
        print(f"Error in join_arena: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء معالجة الطلب."}), 500

def resolve_round(round_id, config=None):
    if not config:
        config = get_arena_settings()
        
    round_ref = db.collection('arena_rounds').document(round_id)
    round_doc = round_ref.get()
    
    if not round_doc.exists or round_doc.to_dict().get('status') != 'active':
        return 
        
    data = round_doc.to_dict()
    participants = data.get('participants', [])
    batch = db.batch()
    entry_fee = config.get("entry_fee", 1000)
    min_participants = config.get("min_participants", 20)
    
    if len(participants) < min_participants:
        for p in participants:
            user_ref = db.collection('users').document(p['uid'])
            batch.update(user_ref, {
                'balance': firestore.Increment(entry_fee),
                'pending_refund': firestore.Increment(entry_fee)
            })
            
        batch.update(round_ref, {'status': 'refunded'})
        batch.commit()
        return

    total_collected = len(participants) * entry_fee
    visible_prize_pool = int(total_collected * 0.45)
    
    random.shuffle(participants)
    winners_list = participants[:5] if len(participants) >= 5 else participants
    percentages = [0.30, 0.25, 0.20, 0.15, 0.10]
    final_winners = []
    
    for i, winner in enumerate(winners_list):
        prize_amount = int(visible_prize_pool * percentages[i])
        user_ref = db.collection('users').document(winner['uid'])
        batch.update(user_ref, {'balance': firestore.Increment(prize_amount)})
        
        final_winners.append({
            "uid": winner['uid'],
            "name": winner['name'],
            "prize": prize_amount
        })
        
    batch.update(round_ref, {'status': 'completed', 'winners': final_winners})
    batch.commit()

@games_bp.route('/results', methods=['POST'])
def get_results():
    success, uid, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res
    
    data = request.get_json() or {}
    req_round_id = data.get('round_id')
    config = get_arena_settings()
    
    if req_round_id:
        resolve_round(str(req_round_id), config)
    
    round_ref = db.collection('arena_rounds').document(str(req_round_id))
    round_doc = round_ref.get()
    
    if not round_doc.exists:
        return jsonify({"success": False})
        
    r_data = round_doc.to_dict()
    user_doc = db.collection('users').document(uid).get()
    current_bal = user_doc.to_dict().get('balance', 0) if user_doc.exists else 0
    
    return jsonify({
        "success": True,
        "status": r_data.get('status'),
        "winners": r_data.get('winners', []),
        "new_balance": current_bal
    })

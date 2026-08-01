# games/games_api.py
import time
import random
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db, get_game_settings
from core.security import get_authenticated_user

games_bp = Blueprint('games', __name__)

def get_arena_config():
    """جلب إعدادات الساحة الديناميكية من Firestore مع توفير قيم افتراضية آمنة"""
    settings = get_game_settings() or {}
    cfg = settings.get('arena_config', {})
    return {
        "entry_fee": int(cfg.get('entry_fee', 1000)),
        "min_participants": int(cfg.get('min_participants', 20)),
        "prize_pool_percentage": float(cfg.get('prize_pool_percentage', 0.45)),
        "round_duration": int(cfg.get('round_duration', 900)),
        "lock_seconds": int(cfg.get('lock_seconds', 15))
    }

def get_current_round_info(round_duration):
    """حساب ID الجولة الحالية بناءً على توقيت السيرفر العالمي والمدة المحددة في الإعدادات"""
    current_time = int(time.time())
    round_duration = max(round_duration, 60)
    round_id_num = current_time // round_duration
    end_time = (round_id_num + 1) * round_duration
    return str(round_id_num), end_time, current_time, round_id_num

@games_bp.route('/status', methods=['POST'])
def arena_status():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res
        
        cfg = get_arena_config()
        round_id, end_time, current_time, round_id_num = get_current_round_info(cfg['round_duration'])
        
        # فحص الجولات السابقة وحسمها
        for i in range(1, 4):
            past_id = str(round_id_num - i)
            past_round_ref = db.collection('arena_rounds').document(past_id)
            past_doc = past_round_ref.get()
            if past_doc.exists and past_doc.to_dict().get('status') == 'active':
                resolve_round(past_id)

        # جلب بيانات الجولة الحالية
        round_ref = db.collection('arena_rounds').document(round_id)
        round_doc = round_ref.get()
        
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
        has_joined = any(p['uid'] == uid for p in participants)
        
        user_doc = db.collection('users').document(uid).get()
        balance = user_doc.to_dict().get('balance', 0.0) if user_doc.exists else 0.0

        total_collected = len(participants) * cfg['entry_fee']
        visible_prize_pool = int(total_collected * cfg['prize_pool_percentage'])

        return jsonify({
            "success": True,
            "round_id": round_id,
            "end_time": end_time,
            "prize_pool": visible_prize_pool,
            "has_joined": has_joined,
            "balance": balance,
            "entry_fee": cfg['entry_fee'],
            "lock_seconds": cfg['lock_seconds']
        })
    except Exception as e:
        print(f"Error in arena_status: {e}")
        return jsonify({"success": False, "message": "خطأ في الاتصال بالخادم."}), 500

@games_bp.route('/join', methods=['POST'])
def join_arena():
    success, uid, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    cfg = get_arena_config()
    round_id, end_time, current_time, _ = get_current_round_info(cfg['round_duration'])
    
    if current_time >= (end_time - cfg['lock_seconds']):
        return jsonify({"success": False, "message": "تم إغلاق باب الاشتراك لهذه الجولة! انتظر الجولة القادمة."})
        
    round_ref = db.collection('arena_rounds').document(round_id)
    user_ref = db.collection('users').document(uid)
    
    @firestore.transactional
    def join_transaction(transaction, round_ref, user_ref):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return False, "المستخدم غير موجود.", 0
            
        user_data = user_doc.to_dict()
        current_balance = user_data.get('balance', 0.0)
        
        if current_balance < cfg['entry_fee']:
            return False, f"رصيدك غير كافٍ للاشتراك (تحتاج {cfg['entry_fee']:,} ZN).", current_balance
            
        round_doc = round_ref.get(transaction=transaction)
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
            
        if any(p['uid'] == uid for p in participants):
            return False, "أنت مشترك بالفعل في هذه الجولة.", current_balance
            
        player_name = user_data.get('first_name') or user_data.get('name') or f"لاعب #{uid[:5]}"
        new_balance = current_balance - cfg['entry_fee']
        
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

def resolve_round(round_id):
    round_ref = db.collection('arena_rounds').document(round_id)
    round_doc = round_ref.get()
    
    if not round_doc.exists or round_doc.to_dict().get('status') != 'active':
        return 
        
    cfg = get_arena_config()
    data = round_doc.to_dict()
    participants = data.get('participants', [])
    batch = db.batch()
    
    # إلغاء الجولة لعدم اكتمال النصاب المحدد في الفايربيس
    if len(participants) < cfg['min_participants']:
        for p in participants:
            user_ref = db.collection('users').document(p['uid'])
            batch.update(user_ref, {
                'balance': firestore.Increment(cfg['entry_fee']),
                'pending_refund': firestore.Increment(cfg['entry_fee'])
            })
            
        batch.update(round_ref, {'status': 'refunded'})
        batch.commit()
        return

    # احتساب الفائزين برصيد وتوزيع الجوائز
    total_collected = len(participants) * cfg['entry_fee']
    visible_prize_pool = int(total_collected * cfg['prize_pool_percentage'])
    
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
    
    if req_round_id:
        resolve_round(str(req_round_id))
    
    round_ref = db.collection('arena_rounds').document(str(req_round_id))
    round_doc = round_ref.get()
    
    if not round_doc.exists:
        return jsonify({"success": False})
        
    r_data = round_doc.to_dict()
    
    user_doc = db.collection('users').document(uid).get()
    current_bal = user_doc.to_dict().get('balance', 0.0) if user_doc.exists else 0.0
    
    return jsonify({
        "success": True,
        "status": r_data.get('status'),
        "winners": r_data.get('winners', []),
        "new_balance": current_bal
    })

@games_bp.route('/check_notifications', methods=['POST'])
def check_notifications():
    success, uid, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res
    
    try:
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": True, "refund": 0})
        
        data = user_doc.to_dict()
        pending_refund = data.get('pending_refund', 0)
        
        if pending_refund > 0:
            user_ref.update({'pending_refund': 0})
            return jsonify({"success": True, "refund": pending_refund})
        
        return jsonify({"success": True, "refund": 0})
    except Exception as e:
        print(f"Error checking notifications: {e}")
        return jsonify({"success": False}), 500

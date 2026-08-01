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
        "entry_fee": float(cfg.get('entry_fee', 1000)),
        "min_participants": int(cfg.get('min_participants', 20)),
        "prize_pool_percentage": float(cfg.get('prize_pool_percentage', 0.45)),
        "round_duration": int(cfg.get('round_duration', 900)),
        "lock_seconds": int(cfg.get('lock_seconds', 15))
    }

def get_current_round_info(round_duration):
    """حساب ID الجولة الحالية بناءً على توقيت السيرفر العالمي"""
    current_time = int(time.time())
    round_duration = max(round_duration, 60)
    round_id_num = current_time // round_duration
    end_time = (round_id_num + 1) * round_duration
    return str(round_id_num), end_time, current_time, round_id_num

def resolve_round(round_id):
    """حسم الجولة بطريقة آمنة ومحمية من التعارضات Transactional"""
    round_ref = db.collection('arena_rounds').document(str(round_id))
    
    @firestore.transactional
    def resolve_transaction(transaction):
        round_doc = round_ref.get(transaction=transaction)
        
        if not round_doc.exists:
            return False
            
        data = round_doc.to_dict()
        if data.get('status') != 'active':
            return False  # تم حسم الجولة سابقاً
            
        cfg = get_arena_config()
        participants = data.get('participants', [])
        
        # 1. إلغاء الجولة وإعادة المبالغ لعدم اكتمال النصاب
        if len(participants) < cfg['min_participants']:
            refund_fee = round(cfg['entry_fee'], 2)
            for p in participants:
                user_ref = db.collection('users').document(p['uid'])
                transaction.update(user_ref, {
                    'balance': firestore.Increment(refund_fee),
                    'pending_refund': firestore.Increment(refund_fee)
                })
                
            transaction.update(round_ref, {'status': 'refunded'})
            return True

        # 2. احتساب وتوزيع الجوائز عند اكتمال النصاب
        total_collected = len(participants) * cfg['entry_fee']
        visible_prize_pool = round(total_collected * cfg['prize_pool_percentage'], 2)
        
        shuffled_participants = list(participants)
        random.shuffle(shuffled_participants)
        
        winners_count = min(len(shuffled_participants), 5)
        winners_list = shuffled_participants[:winners_count]
        
        base_percentages = [0.30, 0.25, 0.20, 0.15, 0.10][:winners_count]
        total_pct = sum(base_percentages)
        normalized_percentages = [pct / total_pct for pct in base_percentages]
        
        final_winners = []
        for i, winner in enumerate(winners_list):
            prize_amount = round(visible_prize_pool * normalized_percentages[i], 2)
            user_ref = db.collection('users').document(winner['uid'])
            
            transaction.update(user_ref, {
                'balance': firestore.Increment(prize_amount)
            })
            
            final_winners.append({
                "uid": winner['uid'],
                "name": winner['name'],
                "prize": prize_amount
            })
            
        transaction.update(round_ref, {
            'status': 'completed',
            'winners': final_winners
        })
        return True

    try:
        return resolve_transaction(db.transaction())
    except Exception as e:
        print(f"Error resolving round {round_id}: {e}")
        return False

@games_bp.route('/status', methods=['POST'])
def arena_status():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res
        
        cfg = get_arena_config()
        round_id, end_time, current_time, round_id_num = get_current_round_info(cfg['round_duration'])
        
        # فحص الجولات السابقة وحسمها بأمان
        for i in range(1, 4):
            past_id = str(round_id_num - i)
            resolve_round(past_id)

        # جلب بيانات الجولة الحالية
        round_ref = db.collection('arena_rounds').document(round_id)
        round_doc = round_ref.get()
        
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
        has_joined = any(p['uid'] == uid for p in participants)
        
        user_doc = db.collection('users').document(uid).get()
        balance = round(float(user_doc.to_dict().get('balance', 0.0)), 2) if user_doc.exists else 0.0

        total_collected = len(participants) * cfg['entry_fee']
        visible_prize_pool = round(total_collected * cfg['prize_pool_percentage'], 2)

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
            return False, "المستخدم غير موجود.", 0, 0
            
        user_data = user_doc.to_dict()
        current_balance = round(float(user_data.get('balance', 0.0)), 2)
        
        if current_balance < cfg['entry_fee']:
            return False, "رصيدك غير كافٍ للاشتراك.", current_balance, 0
            
        round_doc = round_ref.get(transaction=transaction)
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
            
        if any(p['uid'] == uid for p in participants):
            return False, "أنت مشترك بالفعل في هذه الجولة.", current_balance, 0
            
        player_name = user_data.get('first_name') or user_data.get('name') or f"لاعب #{uid[:5]}"
        new_balance = round(current_balance - cfg['entry_fee'], 2)
        
        transaction.update(user_ref, {'balance': new_balance})
        
        participants.append({"uid": uid, "name": player_name})
        transaction.set(round_ref, {'participants': participants, 'status': 'active'}, merge=True)
        
        new_prize_pool = round(len(participants) * cfg['entry_fee'] * cfg['prize_pool_percentage'], 2)
        
        return True, "تم دخول الساحة بنجاح!", new_balance, new_prize_pool
        
    try:
        success_join, msg, new_bal, new_prize = join_transaction(db.transaction(), round_ref, user_ref)
        res_payload = {"success": success_join, "message": msg}
        if success_join:
            res_payload["new_balance"] = new_bal
            res_payload["prize_pool"] = new_prize
            res_payload["has_joined"] = True
        return jsonify(res_payload)
    except Exception as e:
        print(f"Error in join_arena: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء معالجة الطلب."}), 500

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
        return jsonify({"success": False, "message": "الجولة غير موجودة."})
        
    r_data = round_doc.to_dict()
    
    user_doc = db.collection('users').document(uid).get()
    current_bal = round(float(user_doc.to_dict().get('balance', 0.0)), 2) if user_doc.exists else 0.0
    
    return jsonify({
        "success": True,
        "status": r_data.get('status'),
        "winners": r_data.get('winners', []),
        "new_balance": current_bal
    })

@games_bp.route('/check_notifications', methods=['POST'])
def check_notifications():
    """التحقق من المرتجعات والإشعارات المباشرة مع إرجاع الرصيد المحدث لحظياً"""
    success, uid, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res
    
    try:
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": True, "refund": 0, "balance": 0.0})
        
        data = user_doc.to_dict()
        pending_refund = round(float(data.get('pending_refund', 0)), 2)
        current_balance = round(float(data.get('balance', 0.0)), 2)
        
        if pending_refund > 0:
            user_ref.update({'pending_refund': 0})
            return jsonify({
                "success": True, 
                "refund": pending_refund, 
                "balance": current_balance
            })
        
        return jsonify({
            "success": True, 
            "refund": 0, 
            "balance": current_balance
        })
    except Exception as e:
        print(f"Error checking notifications: {e}")
        return jsonify({"success": False, "message": "خطأ في جلب التنبيهات."}), 500

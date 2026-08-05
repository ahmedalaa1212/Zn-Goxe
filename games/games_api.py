# games/games_api.py
import time
import random
import json
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db, get_game_settings, get_system_profit_margin, update_system_treasury
from core.security import get_authenticated_user

games_bp = Blueprint('games', __name__)

# --- Server-Side RAM Caching Systems ---
_ARENA_CONFIG_CACHE = {"data": None, "timestamp": 0}
_ROUND_CACHE = {}            # {round_id: {"data": dict, "timestamp": float}}
_RESOLVED_ROUNDS_CACHE = set()

CACHE_TTL_CONFIG = 600   
CACHE_TTL_ROUND = 5      

# إعدادات عجلة الحظ (المضاعفات والأوزان والاحتمالات)
WHEEL_SLICES = [
    {"index": 0, "label": "0x", "mult": 0.0, "weight": 35},
    {"index": 1, "label": "0.5x", "mult": 0.5, "weight": 25},
    {"index": 2, "label": "1x", "mult": 1.0, "weight": 20},
    {"index": 3, "label": "1.5x", "mult": 1.5, "weight": 10},
    {"index": 4, "label": "2x", "mult": 2.0, "weight": 6},
    {"index": 5, "label": "3x", "mult": 3.0, "weight": 2.5},
    {"index": 6, "label": "5x", "mult": 5.0, "weight": 1.0},
    {"index": 7, "label": "10x", "mult": 10.0, "weight": 0.5}
]

def get_arena_config():
    now = time.time()
    if _ARENA_CONFIG_CACHE["data"] and (now - _ARENA_CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _ARENA_CONFIG_CACHE["data"]

    settings = get_game_settings() or {}
    cfg = settings.get('arena_config', {})
    config_data = {
        "entry_fee": float(cfg.get('entry_fee', 250)),
        "min_participants": int(cfg.get('min_participants', 20)),
        "prize_pool_percentage": float(cfg.get('prize_pool_percentage', 0.45)),
        "round_duration": int(cfg.get('round_duration', 900)),
        "lock_seconds": int(cfg.get('lock_seconds', 15))
    }
    _ARENA_CONFIG_CACHE["data"] = config_data
    _ARENA_CONFIG_CACHE["timestamp"] = now
    return config_data

def get_current_round_info(round_duration):
    current_time = int(time.time())
    round_duration = max(round_duration, 60)
    round_id_num = current_time // round_duration
    end_time = (round_id_num + 1) * round_duration
    return str(round_id_num), end_time, current_time, round_id_num

# --- 1. مسار لف عجلة الحظ (Lucky Wheel API) ---
@games_bp.route('/wheel/spin', methods=['POST'])
def spin_wheel():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    
    settings = get_game_settings() or {}
    wheel_cfg = settings.get('wheel_game_config', {})
    min_bet = float(wheel_cfg.get('min_bet', 100.0))
    target_margin = float(wheel_cfg.get('target_margin', 0.80))
    
    bet = round(float(data.get('bet', min_bet)), 2)

    if bet < min_bet:
        return jsonify({"success": False, "message": f"الحد الأدنى للرهان هو {int(min_bet)} ZN."})

    user_ref = db.collection('users').document(uid_str)
    
    # اختيار القطاع بناءً على الأوزان والاحتمالات مع مراعاة هامش الخزينة
    margin = get_system_profit_margin()
    
    # إذا انخفض هامش أرباح الخزينة، نرفع نسبة الخسارة لحماية النظام
    current_slices = list(WHEEL_SLICES)
    if margin < target_margin:
        weights = [45, 30, 15, 7, 3, 0, 0, 0] # حماية من الجوائز العالية
    else:
        weights = [s['weight'] for s in current_slices]

    winning_slice = random.choices(current_slices, weights=weights, k=1)[0]
    winning_index = winning_slice['index']
    multiplier = winning_slice['mult']
    payout = round(bet * multiplier, 2)

    @firestore.transactional
    def spin_transaction(transaction):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0, 0

        user_data = user_doc.to_dict() or {}
        bal = round(float(user_data.get('balance', 0.0)), 2)
        if bal < bet:
            return False, "رصيدك غير كافٍ للف العجلة", bal, 0

        new_bal = round(bal - bet + payout, 2)
        transaction.update(user_ref, {
            'balance': new_bal,
            'total_bets': firestore.Increment(bet)
        })

        return True, "نجاح", new_bal, payout

    try:
        ok, msg, new_balance, final_payout = spin_transaction(db.transaction())
        if not ok:
            return jsonify({"success": False, "message": msg})

        # تحديث الخزينة
        update_system_treasury(bet_amount=bet, payout_amount=final_payout)

        return jsonify({
            "success": True,
            "winning_index": winning_index,
            "multiplier": multiplier,
            "payout": final_payout,
            "new_balance": new_balance
        })
    except Exception as e:
        print(f"Error spinning wheel: {e}")
        return jsonify({"success": False, "message": "خطأ أثناء معالجة لفة العجلة."}), 500


# --- 2. مسارات الساحة الكبرى (Arena System) المحمية تماماً ---
def resolve_round(round_id):
    str_round_id = str(round_id)
    if str_round_id in _RESOLVED_ROUNDS_CACHE:
        return True

    round_ref = db.collection('arena_rounds').document(str_round_id)
    
    @firestore.transactional
    def resolve_transaction(transaction):
        round_doc = round_ref.get(transaction=transaction)
        if not round_doc.exists:
            _RESOLVED_ROUNDS_CACHE.add(str_round_id)
            return False
            
        data = round_doc.to_dict() or {}
        if data.get('status') != 'active':
            _RESOLVED_ROUNDS_CACHE.add(str_round_id)
            return False
            
        cfg = get_arena_config()
        participants = data.get('participants', [])
        
        if len(participants) < cfg['min_participants']:
            refund_fee = round(cfg['entry_fee'], 2)
            for p in participants:
                user_ref = db.collection('users').document(str(p['uid']))
                transaction.update(user_ref, {
                    'balance': firestore.Increment(refund_fee),
                    'pending_refund': firestore.Increment(refund_fee)
                })
            transaction.update(round_ref, {'status': 'refunded'})
            _RESOLVED_ROUNDS_CACHE.add(str_round_id)
            return True

        total_collected = len(participants) * cfg['entry_fee']
        visible_prize_pool = round(total_collected * cfg['prize_pool_percentage'], 2)
        
        shuffled_participants = list(participants)
        random.shuffle(shuffled_participants)
        
        winners_count = min(len(shuffled_participants), 5)
        winners_list = shuffled_participants[:winners_count]
        
        base_percentages = [0.30, 0.25, 0.20, 0.15, 0.10][:winners_count]
        total_pct = sum(base_percentages) or 1.0
        normalized_percentages = [pct / total_pct for pct in base_percentages]
        
        final_winners = []
        for i, winner in enumerate(winners_list):
            prize_amount = round(visible_prize_pool * normalized_percentages[i], 2)
            user_ref = db.collection('users').document(str(winner['uid']))
            transaction.update(user_ref, {'balance': firestore.Increment(prize_amount)})
            final_winners.append({
                "uid": str(winner['uid']),
                "name": winner.get('name', ''),
                "prize": prize_amount
            })
            
        transaction.update(round_ref, {'status': 'completed', 'winners': final_winners})
        _RESOLVED_ROUNDS_CACHE.add(str_round_id)
        return True

    try:
        res = resolve_transaction(db.transaction())
        _ROUND_CACHE.pop(str_round_id, None)
        return res
    except Exception as e:
        print(f"Error resolving round {round_id}: {e}")
        return False

@games_bp.route('/status', methods=['POST'])
def arena_status():
    try:
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res
        
        uid_str = str(uid)
        cfg = get_arena_config()
        round_id, end_time, current_time, round_id_num = get_current_round_info(cfg['round_duration'])
        
        for i in range(1, 3):
            past_id = str(round_id_num - i)
            if past_id not in _RESOLVED_ROUNDS_CACHE:
                resolve_round(past_id)

        now = time.time()
        cached_round = _ROUND_CACHE.get(round_id)
        if cached_round and (now - cached_round["timestamp"] < CACHE_TTL_ROUND):
            participants = cached_round["participants"]
        else:
            round_ref = db.collection('arena_rounds').document(round_id)
            round_doc = round_ref.get()
            participants = (round_doc.to_dict() or {}).get('participants', []) if round_doc.exists else []
            _ROUND_CACHE[round_id] = {"participants": participants, "timestamp": now}
        
        has_joined = any(str(p.get('uid')) == uid_str for p in participants)
        user_doc = db.collection('users').document(uid_str).get()
        balance = round(float((user_doc.to_dict() or {}).get('balance', 0.0)), 2) if user_doc.exists else 0.0

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
        return jsonify({"success": False, "message": "خطأ في الاتصال بالخادم."}), 500

@games_bp.route('/join', methods=['POST'])
def join_arena():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    cfg = get_arena_config()
    round_id, end_time, current_time, _ = get_current_round_info(cfg['round_duration'])
    
    if current_time >= (end_time - cfg['lock_seconds']):
        return jsonify({"success": False, "message": "تم إغلاق باب الاشتراك لهذه الجولة!"})
        
    round_ref = db.collection('arena_rounds').document(round_id)
    user_ref = db.collection('users').document(uid_str)
    
    @firestore.transactional
    def join_transaction(transaction, round_ref, user_ref):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return False, "المستخدم غير موجود.", 0, 0, []
            
        user_data = user_doc.to_dict() or {}
        current_balance = round(float(user_data.get('balance', 0.0)), 2)
        
        if current_balance < cfg['entry_fee']:
            return False, "رصيدك غير كافٍ للاشتراك.", current_balance, 0, []
            
        round_doc = round_ref.get(transaction=transaction)
        participants = (round_doc.to_dict() or {}).get('participants', []) if round_doc.exists else []
            
        if any(str(p.get('uid')) == uid_str for p in participants):
            return False, "أنت مشترك بالفعل في هذه الجولة.", current_balance, 0, []
            
        player_name = user_data.get('first_name') or user_data.get('name') or f"لاعب #{uid_str[:5]}"
        new_balance = round(current_balance - cfg['entry_fee'], 2)
        
        transaction.update(user_ref, {'balance': new_balance})
        participants.append({"uid": uid_str, "name": player_name})
        transaction.set(round_ref, {'participants': participants, 'status': 'active'}, merge=True)
        
        new_prize_pool = round(len(participants) * cfg['entry_fee'] * cfg['prize_pool_percentage'], 2)
        return True, "تم دخول الساحة بنجاح!", new_balance, new_prize_pool, participants
        
    try:
        success_join, msg, new_bal, new_prize, updated_participants = join_transaction(db.transaction(), round_ref, user_ref)
        res_payload = {"success": success_join, "message": msg}
        if success_join:
            res_payload["new_balance"] = new_bal
            res_payload["prize_pool"] = new_prize
            res_payload["has_joined"] = True
            _ROUND_CACHE[round_id] = {"participants": updated_participants, "timestamp": time.time()}

        return jsonify(res_payload)
    except Exception as e:
        return jsonify({"success": False, "message": "حدث خطأ أثناء معالجة الطلب."}), 500

@games_bp.route('/results', methods=['POST'])
def get_results():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res
    
    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    req_round_id = data.get('round_id')
    
    if not req_round_id:
        return jsonify({"success": False, "message": "معرف الجولة مطلوب."}), 400

    str_round_id = str(req_round_id)
    resolve_round(str_round_id)
    
    round_ref = db.collection('arena_rounds').document(str_round_id)
    round_doc = round_ref.get()
    
    if not round_doc.exists:
        return jsonify({"success": False, "message": "الجولة غير موجودة."})
        
    r_data = round_doc.to_dict() or {}
    user_doc = db.collection('users').document(uid_str).get()
    current_bal = round(float((user_doc.to_dict() or {}).get('balance', 0.0)), 2) if user_doc.exists else 0.0
    
    return jsonify({
        "success": True,
        "status": r_data.get('status'),
        "winners": r_data.get('winners', []),
        "new_balance": current_bal
    })

@games_bp.route('/check_notifications', methods=['POST'])
def check_notifications():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res
    
    try:
        uid_str = str(uid)
        user_ref = db.collection('users').document(uid_str)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": True, "refund": 0, "balance": 0.0})
        
        data = user_doc.to_dict() or {}
        pending_refund = round(float(data.get('pending_refund', 0)), 2)
        current_balance = round(float(data.get('balance', 0.0)), 2)
        
        if pending_refund > 0:
            user_ref.update({'pending_refund': 0})
            return jsonify({"success": True, "refund": pending_refund, "balance": current_balance})
        
        return jsonify({"success": True, "refund": 0, "balance": current_balance})
    except Exception as e:
        return jsonify({"success": False, "message": "خطأ في جلب التنبيهات."}), 500

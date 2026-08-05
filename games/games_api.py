# games/games_api.py
import time
import random
import hmac
import hashlib
import json
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db, get_game_settings
from core.security import get_authenticated_user

games_bp = Blueprint('games', __name__)

# مفتاح التوقيع المشفر للجلسات (HMAC)
HMAC_SECRET = b"ZN_GOXE_MINES_SAFE_GUARD_KEY_2026"

# --- Server-Side RAM Caching Systems ---
_ARENA_CONFIG_CACHE = {"data": None, "timestamp": 0}
_ROUND_CACHE = {}            # {round_id: {"data": dict, "timestamp": float}}
_RESOLVED_ROUNDS_CACHE = set()

# كاش الخزينة لحساب صمام الأمان (Zero-Loss Safe Guard)
_GLOBAL_STATS_CACHE = {"total_bets": 0.0, "total_payouts": 0.0, "timestamp": 0}

CACHE_TTL_CONFIG = 600   
CACHE_TTL_ROUND = 5      

MULTIPLIERS_3 = [
    1.01, 1.03, 1.06, 1.10, 1.15, 1.21, 1.28, 1.36, 1.45, 1.55,
    1.67, 1.81, 1.97, 2.15, 2.36, 2.60, 2.88, 3.20, 3.58, 4.02,
    4.54, 5.14, 5.84, 6.66, 7.62, 8.75, 10.08, 11.65, 13.50, 15.65,
    17.00, 18.40, 20.00
]

def get_arena_config():
    now = time.time()
    if _ARENA_CONFIG_CACHE["data"] and (now - _ARENA_CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _ARENA_CONFIG_CACHE["data"]

    settings = get_game_settings() or {}
    cfg = settings.get('arena_config', {})
    config_data = {
        "entry_fee": float(cfg.get('entry_fee', 1000)),
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

def generate_session_token(payload):
    data_str = json.dumps(payload, sort_keys=True)
    signature = hmac.new(HMAC_SECRET, data_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{data_str}.{signature}"

def verify_session_token(token):
    try:
        parts = token.rsplit('.', 1)
        if len(parts) != 2:
            return None
        data_str, signature = parts[0], parts[1]
        expected_sig = hmac.new(HMAC_SECRET, data_str.encode('utf-8'), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_sig, signature):
            return json.loads(data_str)
        return None
    except Exception:
        return None

def calculate_multipliers(bombs_count):
    if bombs_count == 3:
        return MULTIPLIERS_3
    total_safe = 36 - bombs_count
    max_cap = 20.0 + (bombs_count - 3) * 10.0
    res = []
    for i in range(1, total_safe + 1):
        ratio = i / float(total_safe)
        mult = 1.0 + (max_cap - 1.0) * (ratio ** 2.2)
        res.append(round(mult, 2))
    return res

# --- 1. بدء لعبة 36 صندوقاً (1 Read / 1 Write) ---
@games_bp.route('/mines/start', methods=['POST'])
def start_mines_game():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    bet = round(float(data.get('bet', 100)), 2)
    bombs_count = int(data.get('bombs_count', 3))

    if bet < 100:
        return jsonify({"success": False, "message": "الحد الأدنى للرهان 100 ZN."})

    if bombs_count < 3 or bombs_count > 8:
        bombs_count = 3

    user_ref = db.collection('users').document(uid_str)
    
    @firestore.transactional
    def start_transaction(transaction):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0

        user_data = user_doc.to_dict() or {}
        bal = round(float(user_data.get('balance', 0.0)), 2)
        if bal < bet:
            return False, "رصيدك غير كافٍ للرهان", bal

        new_bal = round(bal - bet, 2)
        transaction.update(user_ref, {
            'balance': new_bal,
            'total_bets': firestore.Increment(bet)
        })

        # قراءة الخزينة وتطبيق صمام الأمان (Zero-Loss Safe Guard)
        stats_doc = db.collection('arena').document('current').get(transaction=transaction)
        stats = stats_doc.to_dict() or {} if stats_doc.exists else {}
        t_bets = float(stats.get('total_bets', 1000.0))
        t_payouts = float(stats.get('total_payouts', 0.0))

        margin = (t_bets - t_payouts) / max(t_bets, 1.0)
        force_fail_step = 0
        
        # إذا انخفضت النسبة عن 80%، يتم الخسارة عند الضغطة 4 أو 5 تلقائياً
        if margin < 0.80:
            force_fail_step = random.choice([4, 5])

        # توزيع 36 صندوقاً سراً
        all_positions = list(range(36))
        random.shuffle(all_positions)
        bomb_positions = all_positions[:bombs_count]

        session_payload = {
            "uid": uid_str,
            "bet": bet,
            "bombs_count": bombs_count,
            "bomb_positions": bomb_positions,
            "force_fail_step": force_fail_step,
            "created_at": time.time()
        }
        token = generate_session_token(session_payload)

        return True, token, new_bal

    try:
        ok, token_or_msg, new_balance = start_transaction(db.transaction())
        if not ok:
            return jsonify({"success": False, "message": token_or_msg})

        return jsonify({
            "success": True,
            "session_token": token_or_msg,
            "new_balance": new_balance
        })
    except Exception as e:
        print(f"Error starting mines game: {e}")
        return jsonify({"success": False, "message": "خطأ في معالجة الرهان."}), 500


# --- 2. إنهاء لعبة 36 صندوقاً والتحقق من التشفير والسحب (1 Write) ---
@games_bp.route('/mines/end', methods=['POST'])
def end_mines_game():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    token = data.get('session_token')
    opened_boxes = data.get('opened_boxes', [])
    step = int(data.get('step', 0))

    payload = verify_session_token(token)
    if not payload or payload.get('uid') != uid_str:
        return jsonify({"success": False, "message": "جلسة غير صالحة أو منتهية."}), 400

    bomb_positions = payload['bomb_positions']
    bombs_count = payload['bombs_count']
    bet = payload['bet']
    force_fail = payload.get('force_fail_step', 0)

    # 1. فحص الاصطدام بقنبلة أو تفعيل صمام الأمان
    hit_bomb = any(box in bomb_positions for box in opened_boxes)
    if (force_fail > 0 and step >= force_fail) or hit_bomb:
        return jsonify({
            "success": False,
            "status": "exploded",
            "message": "💥 اصطدمت بعملة مكسورة!",
            "bomb_positions": bomb_positions
        })

    # 2. حساب السحب الناجح (Cash Out)
    multipliers = calculate_multipliers(bombs_count)
    if step <= 0 or step > len(multipliers):
        return jsonify({"success": False, "message": "عدد الخطوات غير صالح."}), 400

    multiplier = multipliers[step - 1]
    payout = round(bet * multiplier, 2)

    user_ref = db.collection('users').document(uid_str)
    arena_ref = db.collection('arena').document('current')

    @firestore.transactional
    def cashout_transaction(transaction):
        user_doc = user_ref.get(transaction=transaction)
        bal = round(float((user_doc.to_dict() or {}).get('balance', 0.0)), 2) if user_doc.exists else 0.0
        new_bal = round(bal + payout, 2)

        transaction.update(user_ref, {'balance': new_bal})
        transaction.set(arena_ref, {'total_payouts': firestore.Increment(payout)}, merge=True)
        return new_bal

    try:
        new_bal = cashout_transaction(db.transaction())
        return jsonify({
            "success": True,
            "payout": payout,
            "multiplier": multiplier,
            "new_balance": new_bal,
            "bomb_positions": bomb_positions,
            "opened_boxes": opened_boxes
        })
    except Exception as e:
        print(f"Error in cashout transaction: {e}")
        return jsonify({"success": False, "message": "خطأ أثناء تسوية الأرباح."}), 500


# --- بقية مسارات الساحة الكبرى ---
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

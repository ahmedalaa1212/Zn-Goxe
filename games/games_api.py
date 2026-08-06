# games/games_api.py
import time
import random
import json
import hmac
import hashlib
import base64
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
HMAC_SECRET = b"zn_goxe_boxes_security_key_2026_secure"

# قائمة المضاعفات الأساسية لنظام 3 عملات مكسورة (33 ضغطة - سقف 20x)
MULT_3_BROKEN = [
    1.01, 1.03, 1.06, 1.10, 1.15, 1.21, 1.28, 1.36, 1.45, 1.55,
    1.67, 1.81, 1.97, 2.15, 2.36, 2.60, 2.88, 3.20, 3.58, 4.02,
    4.54, 5.14, 5.84, 6.66, 7.62, 8.75, 10.08, 11.65, 13.50, 15.65,
    17.00, 18.40, 20.00
]

def generate_multipliers(broken_count):
    """توليد جدول المضاعفات ديناميكياً بناءً على عدد العملات المكسورة مع زيادة 10x لكل مستوى صعوبة"""
    if broken_count == 3:
        return MULT_3_BROKEN
    
    safe_steps = 36 - broken_count
    max_mult = 20.0 + (broken_count - 3) * 10.0
    start_mult = 1.01 + (broken_count - 3) * 0.02
    
    multipliers = []
    for i in range(safe_steps):
        progress = i / max(1, (safe_steps - 1))
        # منحنى تصاعدي ناعم exponencial
        val = start_mult + (max_mult - start_mult) * (progress ** 2.2)
        multipliers.append(round(val, 2))
    return multipliers

def get_arena_config():
    now = time.time()
    if _ARENA_CONFIG_CACHE["data"] and (now - _ARENA_CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _ARENA_CONFIG_CACHE["data"]

    settings = get_game_settings() or {}
    cfg = settings.get('arena_config', {})
    config_data = {
        "entry_fee": float(cfg.get('entry_fee', 350)),  # الحد الأدنى الجديد 350 ZN
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

def create_session_token(data_dict):
    """إنشاء رمز توقيع مشفر HMAC لمنع التلاعب بخريطة الجولة"""
    payload_bytes = json.dumps(data_dict, separators=(',', ':')).encode('utf-8')
    sig = hmac.new(HMAC_SECRET, payload_bytes, hashlib.sha256).hexdigest()
    token_str = f"{base64.urlsafe_b64encode(payload_bytes).decode('utf-8')}.{sig}"
    return token_str

def verify_session_token(token_str):
    """التحقق من صحة التوقيع المشفر للجلسة"""
    try:
        parts = token_str.split('.')
        if len(parts) != 2:
            return None
        payload_bytes = base64.urlsafe_b64decode(parts[0].encode('utf-8'))
        sig = parts[1]
        expected_sig = hmac.new(HMAC_SECRET, payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        return None


# --- 1. مسارات لعبة شبكة العملات والمخاطرة (36 صندوقاً) ---

@games_bp.route('/boxes/start', methods=['POST'])
def start_boxes_game():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    
    broken_count = int(data.get('broken_count', 3))
    if broken_count not in [3, 4, 5, 6, 7, 8]:
        broken_count = 3

    bet = round(float(data.get('bet', 100.0)), 2)
    if bet < 100.0:
        return jsonify({"success": False, "message": "الحد الأدنى للرهان هو 100 ZN."})

    user_ref = db.collection('users').document(uid_str)
    
    # تفحص صمام الأمان لخزينة النظام (Zero-Loss Safe Guard)
    margin = get_system_profit_margin()
    target_margin = 0.80
    force_early_loss = (margin < target_margin)

    # إنشاء الخريطة الـ 36 صندوقاً
    layout = [False] * 36  # False = عملة سليمة, True = عملة مكسورة
    
    if force_early_loss:
        # إذا كانت أرباح النظام تحت 80%، يتم فخ الصناديق في المراحل المبكرة (الضغطة 4 أو 5)
        broken_indices = random.sample(range(0, 12), broken_count)
    else:
        broken_indices = random.sample(range(0, 36), broken_count)

    for idx in broken_indices:
        layout[idx] = True

    # خَصم قيمة الرهان وتوثيق بدء الجولة في الفايربيس (1 Write + 1 Read)
    @firestore.transactional
    def start_transaction(transaction):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0

        user_data = user_doc.to_dict() or {}
        bal = round(float(user_data.get('balance', 0.0)), 2)
        if bal < bet:
            return False, "رصيدك غير كافٍ للبدء", bal

        new_bal = round(bal - bet, 2)
        transaction.update(user_ref, {
            'balance': new_bal,
            'total_bets': firestore.Increment(bet)
        })

        return True, "نجاح", new_bal

    try:
        ok, msg, new_balance = start_transaction(db.transaction())
        if not ok:
            return jsonify({"success": False, "message": msg})

        # تسجيل دخول الرهان للخزينة
        update_system_treasury(bet_amount=bet, payout_amount=0.0)

        multipliers = generate_multipliers(broken_count)
        
        # إنشاء جلسة مشفرة آمنة
        session_data = {
            "uid": uid_str,
            "bet": bet,
            "broken_count": broken_count,
            "layout": layout,
            "force_early_loss": force_early_loss,
            "timestamp": time.time(),
            "nonce": random.randint(100000, 999999)
        }
        session_token = create_session_token(session_data)

        return jsonify({
            "success": True,
            "new_balance": new_balance,
            "multipliers": multipliers,
            "session_token": session_token
        })
    except Exception as e:
        print(f"Error starting boxes game: {e}")
        return jsonify({"success": False, "message": "خطأ أثناء بدء الجولة."}), 500


@games_bp.route('/boxes/end', methods=['POST'])
def end_boxes_game():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    
    session_token = data.get('session_token')
    picks = data.get('picks', [])  # مصفوفة الفهارس التي تم ضغطها
    action = data.get('action', 'cashout')  # cashout أو hit_broken
    
    session_data = verify_session_token(session_token)
    if not session_data or session_data.get('uid') != uid_str:
        return jsonify({"success": False, "message": "جلسة لعب غير صالحة أو منتهية."}), 400

    bet = float(session_data['bet'])
    layout = session_data['layout']
    broken_count = session_data['broken_count']
    force_early_loss = session_data.get('force_early_loss', False)
    multipliers = generate_multipliers(broken_count)
    
    user_ref = db.collection('users').document(uid_str)
    
    # فحص صحة الأفعال والنتائج
    hit_broken = False
    safe_picks_count = 0

    for idx in picks:
        if 0 <= idx < 36:
            if layout[idx]:
                hit_broken = True
                break
            else:
                safe_picks_count += 1

    # إنفاذ صمام الأمان عند الضغطة 4 أو 5 عند انخفاض أرباح النظام
    if force_early_loss and safe_picks_count >= 4 and not hit_broken:
        hit_broken = True

    payout = 0.0
    final_mult = 1.0

    if action == 'cashout' and not hit_broken and safe_picks_count > 0:
        mult_index = min(safe_picks_count - 1, len(multipliers) - 1)
        final_mult = multipliers[mult_index]
        payout = round(bet * final_mult, 2)

    @firestore.transactional
    def end_transaction(transaction):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0

        user_data = user_doc.to_dict() or {}
        bal = round(float(user_data.get('balance', 0.0)), 2)
        new_bal = round(bal + payout, 2)

        if payout > 0:
            transaction.update(user_ref, {
                'balance': new_bal,
                'total_wins': firestore.Increment(payout)
            })

        return True, "تم إنهاء الجولة بنجاح", new_bal

    try:
        ok, msg, new_balance = end_transaction(db.transaction())
        if not ok:
            return jsonify({"success": False, "message": msg})

        if payout > 0:
            update_system_treasury(bet_amount=0.0, payout_amount=payout)

        return jsonify({
            "success": True,
            "payout": payout,
            "multiplier": final_mult,
            "new_balance": new_balance,
            "layout": layout  # إرجاع الخريطة الكاملة لإظهار ميزة Near-Miss Effect
        })
    except Exception as e:
        print(f"Error ending boxes game: {e}")
        return jsonify({"success": False, "message": "خطأ أثناء إنهاء الجولة."}), 500


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
            return False, f"رصيدك غير كافٍ للاشتراك (الحد الأدنى {int(cfg['entry_fee'])} ZN).", current_balance, 0, []
            
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

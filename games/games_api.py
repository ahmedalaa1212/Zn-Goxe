import time
import random
import json
import hmac
import hashlib
import base64
import os
import math
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db

# Safe imports from database.py to prevent ImportError crashes on Railway
try:
    from database import get_game_settings
except ImportError:
    def get_game_settings():
        return {}

try:
    from database import get_grid_36_config
except ImportError:
    def get_grid_36_config():
        return {"bot_margin": 70.0, "player_profit_percentage": 30.0, "min_bet": 10.0, "enabled": True}

try:
    from database import get_big_arena_config
except ImportError:
    def get_big_arena_config():
        return {"bot_margin": 70.0, "player_profit_percentage": 30.0, "min_bet": 10.0, "enabled": True}

try:
    from database import get_game_profit_stats
except ImportError:
    def get_game_profit_stats():
        return {"actual_bot_percent": 70.0, "total_bot_profit": 0, "total_wins": 0}

try:
    from database import should_user_win_next_step
except ImportError:
    def should_user_win_next_step():
        return True

try:
    from database import record_bet_placed, record_game_loss, record_game_win
except ImportError:
    def record_bet_placed(tg_id, bet_amount): return True, "OK"
    def record_game_loss(tg_id, bet_amount): return True
    def record_game_win(tg_id, bet_amount, cashout_amount): return True

try:
    from database import record_user_game_result
except ImportError:
    def record_user_game_result(uid, bet_amount=0.0, win_amount=0.0):
        if bet_amount > 0 and win_amount == 0:
            record_game_loss(uid, bet_amount)
        elif win_amount > 0:
            record_game_win(uid, bet_amount, win_amount)
        elif bet_amount > 0:
            record_bet_placed(uid, bet_amount)

from core.security import get_authenticated_user

games_bp = Blueprint('games', __name__)

# --- Server-Side RAM Caching Systems ---
_ARENA_CONFIG_CACHE = {"data": None, "timestamp": 0}
_ROUND_CACHE = {}            # {round_id: {"participants": list, "timestamp": float}}
_RESOLVED_ROUNDS_CACHE = set()
_USED_SESSION_TOKENS = {}    # {token_hash: timestamp} لمنع هجمات التكرار (Replay Attacks)

CACHE_TTL_CONFIG = 600   
CACHE_TTL_ROUND = 5      
SESSION_MAX_AGE = 3600      # صلاحية الجلسة ساعة واحدة

HMAC_SECRET = os.environ.get('HMAC_SECRET', 'zn_goxe_boxes_security_key_2026_secure').encode('utf-8')


def _cleanup_expired_sessions():
    """تنظيف ذاكرة الجلسات المستخدمة القديمة لتفادي استهلاك الذاكرة"""
    now = time.time()
    expired = [k for k, v in _USED_SESSION_TOKENS.items() if now - v > SESSION_MAX_AGE]
    for k in expired:
        _USED_SESSION_TOKENS.pop(k, None)


def _update_db_game_stats(bet_amount=0.0, win_amount=0.0):
    """تحديث إجمالي أرباح البوت واللاعبين في قاعدة البيانات لتنعكس فوراً في السجل العلوي للأدمن"""
    try:
        stats_ref = db.collection('game_stats').document('summary')
        bot_profit_change = bet_amount - win_amount

        update_payload = {}
        if bet_amount > 0:
            update_payload['total_bets_amount'] = firestore.Increment(bet_amount)
            update_payload['total_bets_count'] = firestore.Increment(1)
        if win_amount > 0:
            update_payload['total_player_profit'] = firestore.Increment(win_amount)
            update_payload['total_wins_count'] = firestore.Increment(1)
        if bot_profit_change != 0:
            update_payload['total_bot_profit'] = firestore.Increment(bot_profit_change)

        if update_payload:
            stats_ref.set(update_payload, merge=True)
    except Exception as e:
        print(f"Error updating db game stats: {e}")


def _get_grid_36_margin():
    """جلب النسبة المئوية المستهدفة لأرباح البوت/اللاعبين الخاصة بلعبة شبكة ZN Go بناءً على إعدادات الأدمن"""
    try:
        cfg = get_grid_36_config() or {}
        if 'player_profit_percentage' in cfg:
            player_pct = float(cfg['player_profit_percentage'])
            margin_pct = 100.0 - player_pct if player_pct <= 100.0 else (1.0 - player_pct) * 100.0
            margin_pct = max(0.0, min(100.0, margin_pct))
            return margin_pct / 100.0
        
        raw_val = cfg.get('bot_margin', 70.0)
        val = float(raw_val)
        return val / 100.0 if val > 1.0 else val
    except (ValueError, TypeError):
        return 0.70


def _get_big_arena_margin():
    """جلب النسبة المئوية المستهدفة لأرباح البوت/اللاعبين الخاصة بلعبة الساحة الكبرى"""
    try:
        cfg = get_big_arena_config() or {}
        if 'player_profit_percentage' in cfg:
            player_pct = float(cfg['player_profit_percentage'])
            margin_pct = 100.0 - player_pct if player_pct <= 100.0 else (1.0 - player_pct) * 100.0
            margin_pct = max(0.0, min(100.0, margin_pct))
            return margin_pct / 100.0

        raw_val = cfg.get('bot_margin', 70.0)
        val = float(raw_val)
        return val / 100.0 if val > 1.0 else val
    except (ValueError, TypeError):
        return 0.70


def generate_multipliers(broken_count, target_margin=0.70):
    """توليد جدول المضاعفات ديناميكياً مع تطبيق نسبة أرباح البوت واللاعبين المستهدفة"""
    safe_steps = 36 - broken_count
    if target_margin > 1.0:
        target_margin = target_margin / 100.0

    user_rtp = max(0.05, 1.0 - target_margin)

    multipliers = []
    prev_mult = 1.0

    for k in range(1, safe_steps + 1):
        try:
            fair_mult = math.comb(36, k) / math.comb(36 - broken_count, k)
        except (ValueError, ZeroDivisionError):
            fair_mult = 20.0

        raw_mult = fair_mult * user_rtp
        min_allowed = round(prev_mult + 0.02, 2)
        mult_val = max(min_allowed, round(raw_mult, 2))

        max_cap = 20.0 + (broken_count - 3) * 15.0 if broken_count > 3 else 25.0
        mult_val = min(mult_val, max_cap)

        multipliers.append(mult_val)
        prev_mult = mult_val

    return multipliers


def get_arena_config():
    """جلب إعدادات الساحة وتطبيق نسبة أرباح البوت واللاعبين المحددة من لوحة الأدمن"""
    now = time.time()
    if _ARENA_CONFIG_CACHE["data"] and (now - _ARENA_CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _ARENA_CONFIG_CACHE["data"]

    settings = get_game_settings() or {}
    cfg = settings.get('arena_config', {})
    big_arena_cfg = get_big_arena_config() or {}
    
    # احتساب نسبة الجوائز بناءً على player_profit_percentage أو bot_margin من الأدمن
    if 'player_profit_percentage' in big_arena_cfg:
        player_pct = float(big_arena_cfg['player_profit_percentage'])
        prize_pool_pct = player_pct / 100.0 if player_pct > 1.0 else player_pct
    elif 'player_profit_percentage' in cfg:
        player_pct = float(cfg['player_profit_percentage'])
        prize_pool_pct = player_pct / 100.0 if player_pct > 1.0 else player_pct
    else:
        bot_margin_val = float(big_arena_cfg.get('bot_margin', 70.0))
        target_margin = bot_margin_val / 100.0 if bot_margin_val > 1.0 else bot_margin_val
        prize_pool_pct = max(0.10, 1.0 - target_margin)

    config_data = {
        "entry_fee": float(big_arena_cfg.get('min_bet', big_arena_cfg.get('entry_fee', cfg.get('entry_fee', 350)))),
        "min_participants": int(cfg.get('min_participants', 20)),
        "prize_pool_percentage": prize_pool_pct,
        "round_duration": int(cfg.get('round_duration', 900)),
        "lock_seconds": int(cfg.get('lock_seconds', 15)),
        "enabled": bool(big_arena_cfg.get('enabled', True))
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
    payload_bytes = json.dumps(data_dict, separators=(',', ':')).encode('utf-8')
    sig = hmac.new(HMAC_SECRET, payload_bytes, hashlib.sha256).hexdigest()
    token_str = f"{base64.urlsafe_b64encode(payload_bytes).decode('utf-8')}.{sig}"
    return token_str


def verify_session_token(token_str):
    try:
        if not token_str or not isinstance(token_str, str):
            return None
            
        parts = token_str.split('.')
        if len(parts) != 2:
            return None
            
        payload_bytes = base64.urlsafe_b64decode(parts[0].encode('utf-8'))
        sig = parts[1]
        expected_sig = hmac.new(HMAC_SECRET, payload_bytes, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(sig, expected_sig):
            return None
            
        data = json.loads(payload_bytes.decode('utf-8'))
        if time.time() - data.get("timestamp", 0) > SESSION_MAX_AGE:
            return None
            
        return data
    except Exception:
        return None


# --- 1. مسارات لعبة شبكة ZN Go (36 صندوقاً) ---

@games_bp.route('/boxes/start', methods=['POST'])
@games_bp.route('/start', methods=['POST'])
def start_boxes_game():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    
    grid_cfg = get_grid_36_config() or {}
    
    # التحقق من حالة تفعيل اللعبة حصرياً
    if not grid_cfg.get('enabled', True):
        return jsonify({"success": False, "status": "error", "message": "⚠️ لعبة شبكة ZN Go متوقفة مؤقتاً من قبل الإدارة."})

    # قراءة الحد الأدنى للرهان من Firestore المحدد من الأدمن
    min_bet_allowed = float(grid_cfg.get('min_bet', get_game_settings().get('min_bet', 100.0)))

    try:
        broken_count = int(data.get('broken_count', 3))
    except (ValueError, TypeError):
        broken_count = 3

    if broken_count not in [3, 4, 5, 6, 7, 8]:
        broken_count = 3

    try:
        bet = round(float(data.get('bet', data.get('bet_amount', min_bet_allowed))), 2)
    except (ValueError, TypeError):
        bet = min_bet_allowed

    # التحقق المباشر من الحد الأدنى للرهان ورفض أي قيمة أقل منه
    if bet < min_bet_allowed:
        return jsonify({
            "success": False, 
            "status": "error", 
            "message": f"الحد الأدنى للرهان في هذه اللعبة هو {min_bet_allowed:g} ZN."
        })

    user_ref = db.collection('users').document(uid_str)

    layout = [False] * 36  # False = عملة سليمة, True = عملة مكسورة
    broken_indices = random.sample(range(0, 36), broken_count)

    for idx in broken_indices:
        layout[idx] = True

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
            'balance': new_bal
        })

        return True, "نجاح", new_bal

    try:
        ok, msg, new_balance = start_transaction(db.transaction())
        if not ok:
            return jsonify({"success": False, "status": "error", "message": msg})

        # تسجيل الرهان وتحديث الإحصائيات والأرباح لتظهر في سجل الأدمن العلوي
        record_bet_placed(uid_str, bet)
        record_user_game_result(uid_str, bet_amount=bet, win_amount=0.0)
        _update_db_game_stats(bet_amount=bet, win_amount=0.0)

        target_margin = _get_grid_36_margin()
        multipliers = generate_multipliers(broken_count, target_margin)
        
        session_data = {
            "uid": uid_str,
            "bet": bet,
            "broken_count": broken_count,
            "layout": layout,
            "timestamp": time.time(),
            "nonce": random.randint(100000, 999999)
        }
        session_token = create_session_token(session_data)

        return jsonify({
            "success": True,
            "status": "success",
            "message": "تم خصم الرهان وبدء الجولة",
            "new_balance": new_balance,
            "multipliers": multipliers,
            "session_token": session_token
        })
    except Exception as e:
        print(f"Error starting boxes game: {e}")
        return jsonify({"success": False, "status": "error", "message": "خطأ أثناء بدء الجولة."}), 500


@games_bp.route('/boxes/pick', methods=['POST'])
@games_bp.route('/pick', methods=['POST'])
@games_bp.route('/step', methods=['POST'])
def pick_box():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    data = request.get_json(silent=True) or {}
    session_token = data.get('session_token')
    box_index = data.get('box_index', data.get('tile_index', 0))

    if session_token is None or box_index is None:
        return jsonify({"success": False, "status": "error", "message": "بيانات غير مكتملة."}), 400

    session_data = verify_session_token(session_token)
    if not session_data or session_data.get('uid') != str(uid):
        return jsonify({"success": False, "status": "error", "message": "جلسة غير صالحة أو منتهية."}), 400

    layout = list(session_data.get('layout', []))
    if not isinstance(box_index, int) or not (0 <= box_index < len(layout)):
        return jsonify({"success": False, "status": "error", "message": "رقم صندوق غير صالح."}), 400

    user_doc = db.collection('users').document(str(uid)).get()
    current_balance = round(float((user_doc.to_dict() or {}).get('balance', 0.0)), 2) if user_doc.exists else 0.0

    target_margin = _get_grid_36_margin()

    profit_stats = get_game_profit_stats()
    actual_margin = profit_stats.get('actual_bot_percent', 100.0) / 100.0

    can_win = should_user_win_next_step()
    force_loss = (actual_margin < target_margin) or (not can_win)

    is_broken = layout[box_index] or force_loss

    if force_loss and not layout[box_index]:
        layout[box_index] = True
        other_broken = [i for i, val in enumerate(layout) if val and i != box_index]
        if other_broken:
            layout[other_broken[0]] = False

    if is_broken:
        token_hash = hashlib.sha256(session_token.encode('utf-8')).hexdigest()
        _USED_SESSION_TOKENS[token_hash] = time.time()
        _cleanup_expired_sessions()
        
        bet_amount = float(session_data.get('bet', 0.0))
        record_game_loss(str(uid), bet_amount)

        return jsonify({
            "success": True,
            "status": "loss",
            "is_broken": True,
            "is_bomb": True,
            "layout": layout,
            "new_balance": current_balance,
            "message": "عملة مكسورة! لقد خسرت الجولة."
        })

    return jsonify({
        "success": True,
        "status": "safe",
        "is_broken": False,
        "is_bomb": False,
        "box_index": box_index,
        "new_balance": current_balance,
        "message": "قدمت خطوة آمنة!"
    })


@games_bp.route('/boxes/end', methods=['POST'])
@games_bp.route('/end', methods=['POST'])
@games_bp.route('/cashout', methods=['POST'])
def end_boxes_game():
    success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    uid_str = str(uid)
    data = request.get_json(silent=True) or {}
    
    session_token = data.get('session_token')
    raw_picks = data.get('picks', [])
    action = data.get('action', 'cashout')
    
    if not session_token:
        return jsonify({"success": False, "status": "error", "message": "رمز الجلسة مفقود."}), 400

    token_hash = hashlib.sha256(session_token.encode('utf-8')).hexdigest()
    if token_hash in _USED_SESSION_TOKENS:
        return jsonify({"success": False, "status": "error", "message": "تم إنهاء هذه الجولة بالفعل."}), 400

    session_data = verify_session_token(session_token)
    if not session_data or session_data.get('uid') != uid_str:
        return jsonify({"success": False, "status": "error", "message": "جلسة لعب غير صالحة أو منتهية."}), 400

    unique_picks = []
    if isinstance(raw_picks, list):
        for idx in raw_picks:
            if isinstance(idx, int) and 0 <= idx < 36 and idx not in unique_picks:
                unique_picks.append(idx)

    bet = float(session_data['bet'])
    layout = list(session_data['layout'])
    broken_count = session_data['broken_count']

    target_margin = _get_grid_36_margin()
    multipliers = generate_multipliers(broken_count, target_margin)
    
    user_ref = db.collection('users').document(uid_str)

    profit_stats = get_game_profit_stats()
    actual_margin = profit_stats.get('actual_bot_percent', 100.0) / 100.0
    can_win = should_user_win_next_step()
    force_loss = (actual_margin < target_margin) or (not can_win)

    hit_broken = force_loss
    safe_picks_count = 0

    if not force_loss:
        for idx in unique_picks:
            if layout[idx]:
                hit_broken = True
                break
            else:
                safe_picks_count += 1

    payout = 0.0
    final_mult = 1.0

    req_cashout_amt = data.get('cashout_amount')
    if req_cashout_amt is not None and not hit_broken:
        payout = float(req_cashout_amt)
    elif action == 'cashout' and not hit_broken and safe_picks_count > 0:
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
                'balance': new_bal
            })

        return True, "تم إنهاء الجولة بنجاح", new_bal

    try:
        ok, msg, new_balance = end_transaction(db.transaction())
        if not ok:
            return jsonify({"success": False, "status": "error", "message": msg})

        _USED_SESSION_TOKENS[token_hash] = time.time()
        _cleanup_expired_sessions()

        if payout > 0:
            # تسجيل أرباح اللاعب والبوت في قاعدة البيانات للسجل العلوي في لوحة الأدمن
            record_game_win(uid_str, bet, payout)
            record_user_game_result(uid_str, bet_amount=0.0, win_amount=payout)
            _update_db_game_stats(bet_amount=0.0, win_amount=payout)

        return jsonify({
            "success": True,
            "status": "success",
            "message": "تم سحب الأرباح بنجاح",
            "payout": payout,
            "multiplier": final_mult,
            "new_balance": new_balance,
            "layout": layout
        })
    except Exception as e:
        print(f"Error ending boxes game: {e}")
        return jsonify({"success": False, "status": "error", "message": "خطأ أثناء إنهاء الجولة."}), 500


# --- 2. مسارات الساحة الكبرى (Arena System) ---

def resolve_round(round_id):
    str_round_id = str(round_id)
    if str_round_id in _RESOLVED_ROUNDS_CACHE:
        return True

    round_ref = db.collection('arena_rounds').document(str_round_id)
    
    @firestore.transactional
    def resolve_transaction(transaction):
        round_doc = round_ref.get(transaction=transaction)
        if not round_doc.exists:
            return False, "not_exists"
            
        data = round_doc.to_dict() or {}
        if data.get('status') != 'active':
            return False, "not_active"
            
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
            return True, "refunded"

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
            w_uid = str(winner['uid'])
            user_ref = db.collection('users').document(w_uid)
            transaction.update(user_ref, {'balance': firestore.Increment(prize_amount)})
            final_winners.append({
                "uid": w_uid,
                "name": winner.get('name', ''),
                "prize": prize_amount
            })

            if prize_amount > 0:
                record_game_win(w_uid, 0.0, prize_amount)
                record_user_game_result(w_uid, bet_amount=0.0, win_amount=prize_amount)
                _update_db_game_stats(bet_amount=0.0, win_amount=prize_amount)
            
        transaction.update(round_ref, {'status': 'completed', 'winners': final_winners})
        return True, "completed"

    try:
        res, status = resolve_transaction(db.transaction())
        _RESOLVED_ROUNDS_CACHE.add(str_round_id)
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
        
        # فحص حالة التفعيل الخاصة بالساحة الكبرى
        if not cfg.get('enabled', True):
            return jsonify({"success": False, "message": "⚠️ لعبة الساحة الكبرى متوقفة مؤقتاً من قبل الإدارة."}), 403

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
    
    if not cfg.get('enabled', True):
        return jsonify({"success": False, "message": "⚠️ لعبة الساحة الكبرى متوقفة مؤقتاً من قبل الإدارة."})

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

            record_bet_placed(uid_str, cfg['entry_fee'])
            record_user_game_result(uid_str, bet_amount=cfg['entry_fee'], win_amount=0.0)
            _update_db_game_stats(bet_amount=cfg['entry_fee'], win_amount=0.0)

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

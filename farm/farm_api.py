from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from core.security import get_authenticated_user
from database import db, get_game_settings

farm_bp = Blueprint('farm', __name__)

COOLDOWN_SECONDS = 15

DEFAULT_GAME_SETTINGS = {
    "daily_rewards": [
        100, 150, 200, 250, 300, 350, 400, 500, 600, 700,
        800, 900, 1000, 1200, 1400, 1600, 1800, 2000, 2300, 2600,
        3000, 3500, 4000, 4500, 5000, 6000, 7000, 8000, 9000, 10000
    ],
    "mining_config": {
        "daily_boost_reward": 2.0
    },
    "storage_capacities": {
        "0": 200.0, "1": 600.0, "2": 1500.0, "3": 3500.0, "4": 8000.0,
        "5": 18000.0, "6": 40000.0, "7": 90000.0, "8": 200000.0, "9": 450000.0, "10": 1000000.0
    },
    "upgrade_config": {
        "1": {"base_cost": 2000.0, "rate_bonus": 5.0, "price": 2000.0, "rate": 5.0},
        "2": {"base_cost": 7000.0, "rate_bonus": 15.0, "price": 7000.0, "rate": 15.0},
        "3": {"base_cost": 18000.0, "rate_bonus": 35.0, "price": 18000.0, "rate": 35.0},
        "4": {"base_cost": 45000.0, "rate_bonus": 80.0, "price": 45000.0, "rate": 80.0},
        "5": {"base_cost": 110000.0, "rate_bonus": 180.0, "price": 110000.0, "rate": 180.0},
        "6": {"base_cost": 260000.0, "rate_bonus": 400.0, "price": 260000.0, "rate": 400.0},
        "7": {"base_cost": 600000.0, "rate_bonus": 900.0, "price": 600000.0, "rate": 900.0},
        "8": {"base_cost": 1400000.0, "rate_bonus": 2000.0, "price": 1400000.0, "rate": 2000.0},
        "9": {"base_cost": 3200000.0, "rate_bonus": 4500.0, "price": 3200000.0, "rate": 4500.0}
    }
}

def parse_daily_rewards(rewards_data):
    if isinstance(rewards_data, list) and len(rewards_data) > 0:
        return [int(x) for x in rewards_data]
    if isinstance(rewards_data, dict):
        res = []
        for i in range(1, 31):
            val = rewards_data.get(f"day_{i}") or rewards_data.get(str(i)) or DEFAULT_GAME_SETTINGS["daily_rewards"][i-1]
            res.append(int(val))
        return res
    return DEFAULT_GAME_SETTINGS["daily_rewards"]

def get_base_storage_capacity(storage_level, settings):
    try:
        lvl = int(storage_level)
    except (ValueError, TypeError):
        lvl = 0
    lvl = max(0, min(lvl, 10))
    
    caps = settings.get("storage_capacities") or settings.get("storage_config") or DEFAULT_GAME_SETTINGS["storage_capacities"]
    
    if str(lvl) in caps and isinstance(caps[str(lvl)], dict):
        return float(caps[str(lvl)].get("capacity", 200.0))
        
    val = caps.get(str(lvl)) or caps.get(lvl) or 200.0
    return float(val)

def calculate_user_max_cap(user_data, settings):
    stg_lvl = user_data.get("storage_level", 0)
    base_cap = get_base_storage_capacity(stg_lvl, settings)
    extra_cap = float(user_data.get("extra_storage", 0.0))
    return round(base_cap + extra_cap, 2)

def calculate_accrued_mined(data, now, max_cap):
    last_claim_str = data.get("last_claim_time")
    hourly_rate = float(data.get("hourly_rate", 0.0))
    if not last_claim_str or hourly_rate <= 0:
        return 0.0
    try:
        last_claim = datetime.fromisoformat(str(last_claim_str).replace('Z', '+00:00'))
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)
        seconds_passed = max(0.0, (now - last_claim).total_seconds())
        mined = (hourly_rate / 3600.0) * seconds_passed
        return round(min(mined, max_cap), 2)
    except Exception:
        return 0.0

@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
    
    user_id_str = str(telegram_id)
    try:
        user_ref = db.collection('users').document(user_id_str)
        user_doc = user_ref.get()
        now = datetime.now(timezone.utc)
        game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
        
        if not user_doc.exists:
            user_data = {
                "tg_id": user_id_str,
                "telegram_id": user_id_str, 
                "balance": 0.0, 
                "ad_balance": 0.0,
                "usd_balance": 0.0,
                "hourly_rate": 0.0,
                "unclaimed": 0.0, 
                "storage_level": 0,
                "extra_storage": 0.0,
                "max_cap": get_base_storage_capacity(0, game_settings), 
                "daily_day": 1,
                "daily_streak": 1,
                "last_claim_time": now.isoformat(), 
                "last_daily_claim_date": None, 
                "last_boost_date": None,
                "ads_watched": 0, 
                "upgrades": {},
                "referred_by": None,
                "pending_ref_earnings": 0.0,
                "total_ref_earnings": 0.0,
                "invited_friends_count": 0,
                "ref_generated_amount": 0.0,
                "claimed_ref_tasks": []
            }
            user_ref.set(user_data)
        else:
            user_data = user_doc.to_dict() or {}
            
            auto_fix = {}
            if "pending_ref_earnings" not in user_data:
                auto_fix["pending_ref_earnings"] = 0.0
                user_data["pending_ref_earnings"] = 0.0
            if "total_ref_earnings" not in user_data:
                auto_fix["total_ref_earnings"] = 0.0
                user_data["total_ref_earnings"] = 0.0
            
            if auto_fix:
                user_ref.update(auto_fix)
            
        expected_max_cap = calculate_user_max_cap(user_data, game_settings)
        if user_data.get("max_cap") != expected_max_cap:
            user_data["max_cap"] = expected_max_cap
            user_ref.update({"max_cap": expected_max_cap})
            
        max_cap = expected_max_cap
        user_data["balance"] = round(float(user_data.get("balance", 0.0)), 2)
        user_data["unclaimed"] = calculate_accrued_mined(user_data, now, max_cap)
        
        today_str = now.strftime('%Y-%m-%d')
        yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        last_daily_claim = user_data.get("last_daily_claim_date")
        raw_daily_day = int(user_data.get("daily_day") or user_data.get("daily_streak") or 1)
        
        if last_daily_claim == today_str:
            effective_daily_day = raw_daily_day
        elif last_daily_claim == yesterday_str:
            effective_daily_day = raw_daily_day + 1 if raw_daily_day < 30 else 1
        else:
            effective_daily_day = 1
            
        user_data["daily_day"] = effective_daily_day
        user_data["daily_streak"] = effective_daily_day
        
        parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))
        upgrade_configs = game_settings.get("upgrade_config") or game_settings.get("speed_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
        upgrade_costs = {int(k): float(v.get("base_cost", v.get("price", 0))) for k, v in upgrade_configs.items()}
        mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
        daily_boost_reward = round(float(mining_cfg.get("daily_boost_reward", 2.0)), 2)
        
        return jsonify({
            "success": True, 
            "player": user_data, 
            "server_time": now.isoformat(),
            "cooldown_seconds": COOLDOWN_SECONDS,
            "game_config": {
                "daily_rewards": parsed_rewards,
                "upgrade_costs": upgrade_costs,
                "daily_boost_reward": daily_boost_reward
            }
        }), 200
    except Exception as e:
        print(f"Error player_data: {e}")
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500

@farm_bp.route('/claim', methods=['POST'])
def claim_mined_tokens():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    
    try:
        user_ref = db.collection('users').document(user_id_str)
        game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
        
        @firestore.transactional
        def run_claim_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
                
            user_data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            
            last_claim_str = user_data.get("last_claim_time")
            if last_claim_str:
                try:
                    last_claim = datetime.fromisoformat(str(last_claim_str).replace('Z', '+00:00'))
                    if last_claim.tzinfo is None:
                        last_claim = last_claim.replace(tzinfo=timezone.utc)
                    seconds_passed = (now - last_claim).total_seconds()
                    if seconds_passed < COOLDOWN_SECONDS:
                        return {"success": False, "error": f"الرجاء الانتظار {COOLDOWN_SECONDS} ثانية قبل التجميع مجدداً"}
                except Exception:
                    pass
                    
            max_cap = calculate_user_max_cap(user_data, game_settings)
            mined_amount = calculate_accrued_mined(user_data, now, max_cap)
            
            if mined_amount <= 0:
                return {"success": False, "error": "المخزن فارغ حالياً"}

            referred_by = user_data.get("referred_by")
            referrer_ref = None
            referrer_doc = None
            commission = 0.0
            
            if referred_by and str(referred_by).strip() != "" and str(referred_by) != "null":
                try:
                    friends_cfg = game_settings.get("friends_config", {})
                    comm_pct = float(friends_cfg.get("commission_percent", 10))
                    commission = round(mined_amount * (comm_pct / 100.0), 2)
                    if commission > 0:
                        referrer_ref = db.collection('users').document(str(referred_by))
                        referrer_doc = referrer_ref.get(transaction=transaction)
                except Exception as ref_read_err:
                    print(f"⚠️ Error reading referrer document: {ref_read_err}")

            current_balance = float(user_data.get("balance", 0.0))
            new_balance = round(current_balance + mined_amount, 2)
            now_iso = now.isoformat()
            
            transaction.update(ref, {
                "balance": new_balance,
                "last_claim_time": now_iso
            })

            if referrer_ref and referrer_doc and referrer_doc.exists and commission > 0:
                try:
                    transaction.update(referrer_ref, {
                        "pending_ref_earnings": firestore.Increment(commission),
                        "total_ref_earnings": firestore.Increment(commission)
                    })
                    friend_sub_ref = referrer_ref.collection('friends').document(user_id_str)
                    friend_name = user_data.get('first_name') or user_data.get('name') or 'صديق'
                    transaction.set(friend_sub_ref, {
                        "earned_from_him": firestore.Increment(commission),
                        "name": friend_name
                    }, merge=True)
                except Exception as ref_err:
                    print(f"⚠️ Error updating referral commission: {ref_err}")
            
            return {
                "success": True,
                "new_balance": new_balance,
                "last_claim_time": now_iso,
                "server_time": now_iso,
                "claimed_amount": mined_amount
            }

        transaction = db.transaction()
        result = run_claim_transaction(transaction, user_ref)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
        
    except Exception as e:
        print(f"Error claim: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء التجميع"}), 500

@farm_bp.route('/upgrade', methods=['POST'])
def buy_upgrade():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    data = request.json or {}
    level = str(data.get("level"))
    
    if not level or level not in [str(i) for i in range(1, 10)]:
        return jsonify({"success": False, "error": "مستوى غير صحيح"}), 400
        
    user_id_str = str(telegram_id)
    
    try:
        user_ref = db.collection('users').document(user_id_str)
        game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
        
        upgrade_configs = game_settings.get("upgrade_config") or game_settings.get("speed_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
        if level not in upgrade_configs:
            return jsonify({"success": False, "error": "بيانات المستوى غير متوفرة"}), 400
            
        level_cfg = upgrade_configs[level]
        cost = float(level_cfg.get("base_cost", level_cfg.get("price", 0)))
        rate_bonus = round(float(level_cfg.get("rate_bonus", level_cfg.get("rate", 0))), 2)
        
        @firestore.transactional
        def run_upgrade_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
                
            user_data = snapshot.to_dict() or {}
            current_balance = float(user_data.get("balance", 0.0))
            
            if current_balance < cost:
                return {"success": False, "error": "رصيدك غير كافٍ لإتمام الترقية"}
                
            upgrades = user_data.get("upgrades", {})
            if not isinstance(upgrades, dict):
                upgrades = {}
                
            lvl_key = f"lvl{level}"
            current_count = int(upgrades.get(lvl_key, 0))
            
            if current_count >= 10:
                return {"success": False, "error": "لقد وصلت للحد الأقصى لهذا المستوى"}
                
            if int(level) > 1:
                prev_lvl = str(int(level) - 1)
                prev_key = f"lvl{prev_lvl}"
                prev_count = int(upgrades.get(prev_key, 0))
                if prev_count == 0:
                    return {"success": False, "error": "يجب شراء المستوى السابق أولاً"}
            
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            
            max_cap = calculate_user_max_cap(user_data, game_settings)
            mined_amount = calculate_accrued_mined(user_data, now, max_cap)
            
            new_balance = round((current_balance + mined_amount) - cost, 2)
            current_hourly_rate = float(user_data.get("hourly_rate", 0.0))
            new_hourly_rate = round(current_hourly_rate + rate_bonus, 2)
            
            upgrades[lvl_key] = current_count + 1
            
            transaction.update(ref, {
                "balance": new_balance,
                "hourly_rate": new_hourly_rate,
                "upgrades": upgrades,
                "last_claim_time": now_iso
            })

            return {
                "success": True,
                "new_balance": new_balance,
                "new_hourly_rate": new_hourly_rate,
                "upgrades": upgrades,
                "server_time": now_iso
            }

        transaction = db.transaction()
        result = run_upgrade_transaction(transaction, user_ref)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
        
    except Exception as e:
        print(f"Error upgrade: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية الشراء"}), 500

@farm_bp.route('/daily_claim', methods=['POST'])
def claim_daily():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    
    try:
        user_ref = db.collection('users').document(user_id_str)
        game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
        parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))
        
        @firestore.transactional
        def run_daily_claim_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
                
            user_data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            today_str = now.strftime('%Y-%m-%d')
            yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            last_daily_claim = user_data.get("last_daily_claim_date")
            
            if last_daily_claim == today_str:
                return {"success": False, "error": "لقد قمت باستلام المكافأة اليوم بالفعل"}
                
            raw_daily_day = int(user_data.get("daily_day") or user_data.get("daily_streak") or 1)
            
            if last_daily_claim == yesterday_str:
                effective_daily_day = raw_daily_day + 1 if raw_daily_day < 30 else 1
            else:
                effective_daily_day = 1
                
            reward_index = min(max(effective_daily_day - 1, 0), 29)
            reward_amount = float(parsed_rewards[reward_index])
            
            current_balance = float(user_data.get("balance", 0.0))
            new_balance = round(current_balance + reward_amount, 2)
            
            transaction.update(ref, {
                "balance": new_balance,
                "daily_day": effective_daily_day,
                "daily_streak": effective_daily_day,
                "last_daily_claim_date": today_str
            })
            
            return {
                "success": True,
                "new_balance": new_balance,
                "daily_day": effective_daily_day,
                "last_daily_claim_date": today_str,
                "server_time": now.isoformat()
            }

        transaction = db.transaction()
        result = run_daily_claim_transaction(transaction, user_ref)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
        
    except Exception as e:
        print(f"Error daily claim: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة اليومية"}), 500

@farm_bp.route('/daily_boost', methods=['POST'])
def claim_daily_boost():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    
    try:
        user_ref = db.collection('users').document(user_id_str)
        game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
        mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
        daily_boost_reward = round(float(mining_cfg.get("daily_boost_reward", 2.0)), 2)
        
        @firestore.transactional
        def run_boost_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
                
            user_data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            today_str = now.strftime('%Y-%m-%d')
            
            last_boost = user_data.get("last_boost_date")
            
            if last_boost == today_str:
                return {"success": False, "error": "لقد حصلت على تعزيز اليوم بالفعل"}
                
            current_hourly_rate = float(user_data.get("hourly_rate", 0.0))
            new_hourly_rate = round(current_hourly_rate + daily_boost_reward, 2)
            
            transaction.update(ref, {
                "hourly_rate": new_hourly_rate,
                "last_boost_date": today_str
            })
            
            return {
                "success": True,
                "new_rate": new_hourly_rate,
                "last_boost_date": today_str,
                "server_time": now.isoformat()
            }

        transaction = db.transaction()
        result = run_boost_transaction(transaction, user_ref)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
        
    except Exception as e:
        print(f"Error daily boost: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء تفعيل التعزيز"}), 500

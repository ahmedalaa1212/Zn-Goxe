from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from core.security import get_authenticated_user
from database import db, get_game_settings

farm_bp = Blueprint('farm', __name__)

COOLDOWN_SECONDS = 15  # مدة الانتظار الإجبارية بين كل عملية تجميع بالثواني

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

def get_storage_capacity(storage_level, settings):
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
        return min(mined, max_cap)
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
                "max_cap": get_storage_capacity(0, game_settings), 
                "daily_day": 1,
                "daily_streak": 0,
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

        storage_level = user_data.get("storage_level", 0)
        
        if "max_cap" in user_data and user_data["max_cap"] is not None:
            max_cap = float(user_data["max_cap"])
        else:
            max_cap = get_storage_capacity(storage_level, game_settings)
            user_data["max_cap"] = max_cap
            user_ref.update({"max_cap": max_cap})

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

        parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))
        upgrade_configs = game_settings.get("upgrade_config") or game_settings.get("speed_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
        upgrade_costs = {int(k): float(v.get("base_cost", v.get("price", 0))) for k, v in upgrade_configs.items()}

        mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
        daily_boost_reward = float(mining_cfg.get("daily_boost_reward", 2.0))

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
                return None, "الحساب غير موجود", 404

            user_data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            last_claim_str = user_data.get("last_claim_time")
            hourly_rate = float(user_data.get("hourly_rate", 0.0))
            storage_level = user_data.get("storage_level", 0)
            max_cap = float(user_data.get("max_cap") or get_storage_capacity(storage_level, game_settings))

            unclaimed = 0.0

            if last_claim_str:
                try:
                    last_claim = datetime.fromisoformat(str(last_claim_str).replace('Z', '+00:00'))
                    if last_claim.tzinfo is None: 
                        last_claim = last_claim.replace(tzinfo=timezone.utc)
                        
                    seconds_passed = (now - last_claim).total_seconds()
                    
                    if seconds_passed < (COOLDOWN_SECONDS - 2.0):
                        remaining = int(COOLDOWN_SECONDS - seconds_passed)
                        return None, f"انتظر {remaining} ثانية ⏳", 400

                    mined = (hourly_rate / 3600.0) * max(0.0, seconds_passed)
                    unclaimed = min(mined, max_cap)
                except Exception: 
                    pass

            if unclaimed <= 0: 
                return None, "لا يوجد رصيد حالياً في المخزن.", 400

            current_bal = float(user_data.get("balance", 0.0))
            new_balance = round(current_bal + unclaimed, 2)
            now_iso = now.isoformat()

            transaction.update(ref, {
                "balance": new_balance,
                "unclaimed": 0.0,
                "last_claim_time": now_iso
            })
            return {"new_balance": new_balance, "claimed_amount": unclaimed, "last_claim_time": now_iso, "server_time": now_iso}, None, 200

        transaction = db.transaction()
        result_data, error_msg, status_code = run_claim_transaction(transaction, user_ref)
        
        if error_msg:
            return jsonify({
                "success": False, 
                "error": error_msg,
                "server_time": datetime.now(timezone.utc).isoformat()
            }), status_code

        return jsonify({
            "success": True,
            "new_balance": result_data["new_balance"],
            "claimed_amount": result_data["claimed_amount"],
            "last_claim_time": result_data["last_claim_time"],
            "server_time": result_data["server_time"]
        }), 200

    except Exception as e:
        print(f"Error claim: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في عملية التجميع"}), 500

@farm_bp.route('/upgrade', methods=['POST'])
def upgrade_field():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: return error_res

    req_data = request.get_json(silent=True) or {}
    try:
        level = int(req_data.get('level'))
        if level < 1 or level > 9: return jsonify({"success": False, "error": "مستوى ترقية غير صالح"}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "بيانات الترقية غير صالحة"}), 400

    game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
    upgrade_configs = game_settings.get("upgrade_config") or game_settings.get("speed_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
    config = upgrade_configs.get(str(level)) or upgrade_configs.get(level)

    if not config: return jsonify({"success": False, "error": "إعدادات الترقية غير موجودة"}), 400

    user_id_str = str(telegram_id)
    user_ref = db.collection('users').document(user_id_str)

    try:
        @firestore.transactional
        def run_upgrade_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists: return None, "المستخدم غير موجود", 404

            data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            max_cap = float(data.get("max_cap") or get_storage_capacity(data.get("storage_level", 0), game_settings))
            
            accrued = calculate_accrued_mined(data, now, max_cap)
            current_bal = float(data.get("balance", 0.0))
            cost = float(config.get("base_cost") or config.get("price", 0.0))

            if current_bal < cost: return None, f"رصيدك غير كافٍ! تحتاج إلى {cost:,.0f} ZN", 400

            upgrades = data.get("upgrades") or {}
            lvl_key = f"lvl{level}"
            
            val = upgrades.get(lvl_key, upgrades.get(str(level), 0))
            current_count = int(val) if val is not None else 0

            if current_count >= 10: return None, "وصلت للحد الأقصى من الترقية لهذا المستوى", 400

            if level > 1:
                prev_val = upgrades.get(f"lvl{level-1}", upgrades.get(str(level-1), 0))
                prev_lvl_count = int(prev_val) if prev_val is not None else 0
                if prev_lvl_count <= 0: return None, "يجب فتح المستوى السابق أولاً", 400

            upgrades[lvl_key] = current_count + 1
            new_bal = round((current_bal - cost) + accrued, 2)
            rate_bonus = float(config.get("rate_bonus") or config.get("rate", 0.0))
            new_rate = float(data.get("hourly_rate", 0.0)) + rate_bonus

            now_iso = now.isoformat()
            transaction.update(ref, {
                "balance": new_bal,
                "hourly_rate": new_rate,
                "upgrades": upgrades,
                "last_claim_time": now_iso,
                "unclaimed": 0.0
            })

            return {"new_balance": new_bal, "new_hourly_rate": new_rate, "upgrades": upgrades, "server_time": now_iso}, None, 200

        transaction = db.transaction()
        res_data, err_msg, status_code = run_upgrade_transaction(transaction, user_ref)

        if err_msg: return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({
            "success": True,
            "new_balance": res_data["new_balance"],
            "new_hourly_rate": res_data["new_hourly_rate"],
            "upgrades": res_data["upgrades"],
            "server_time": res_data["server_time"]
        }), 200

    except Exception as e:
        print(f"Error in upgrade: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء تنفيذ الترقية"}), 500

@farm_bp.route('/daily_boost', methods=['POST'])
@farm_bp.route('/watch-ad', methods=['POST'])
def daily_boost():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: return error_res

    user_id_str = str(telegram_id)
    user_ref = db.collection('users').document(user_id_str)
    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime('%Y-%m-%d')
    game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    boost_reward = float(mining_cfg.get("daily_boost_reward", 2.0))

    try:
        @firestore.transactional
        def run_boost_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists: return None, "المستخدم غير موجود", 404

            data = snapshot.to_dict() or {}
            if data.get("last_boost_date") == today_str:
                return None, "لقد استخدمت التسريع اليومي بالفعل اليوم!", 400

            max_cap = float(data.get("max_cap") or get_storage_capacity(data.get("storage_level", 0), game_settings))
            accrued = calculate_accrued_mined(data, now_dt, max_cap)
            
            current_rate = float(data.get("hourly_rate", 0.0))
            new_rate = current_rate + boost_reward
            current_bal = float(data.get("balance", 0.0))
            new_balance = round(current_bal + accrued, 2)

            now_iso = now_dt.isoformat()
            transaction.update(ref, {
                "balance": new_balance,
                "hourly_rate": new_rate,
                "last_boost_date": today_str,
                "last_claim_time": now_iso,
                "unclaimed": 0.0,
                "ads_watched": firestore.Increment(1)
            })

            return {"new_rate": new_rate, "new_balance": new_balance, "last_boost_date": today_str, "added_rate": boost_reward, "server_time": now_iso}, None, 200

        transaction = db.transaction()
        res_data, err_msg, status_code = run_boost_transaction(transaction, user_ref)

        if err_msg: return jsonify({"success": False, "error": err_msg, "server_time": now_dt.isoformat()}), status_code

        return jsonify({
            "success": True,
            "new_rate": res_data["new_rate"],
            "new_balance": res_data["new_balance"],
            "last_boost_date": res_data["last_boost_date"],
            "added_rate": res_data["added_rate"],
            "hourly_rate": res_data["new_rate"],
            "server_time": res_data["server_time"]
        }), 200

    except Exception as e:
        print(f"Error daily_boost: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء تفعيل التسريع"}), 500

@farm_bp.route('/daily_claim', methods=['POST'])
@farm_bp.route('/daily-claim', methods=['POST'])
def daily_claim():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: return error_res

    user_id_str = str(telegram_id)
    user_ref = db.collection('users').document(user_id_str)
    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime('%Y-%m-%d')
    yesterday_str = (now_dt - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        @firestore.transactional
        def run_daily_claim_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists: return None, "المستخدم غير موجود", 404

            data = snapshot.to_dict() or {}
            last_claim_date = data.get("last_daily_claim_date")

            if last_claim_date == today_str:
                return None, "لقد استلمت مكافأتك اليومية بالفعل اليوم! عد غداً ⌛", 400

            current_day = int(data.get("daily_day") or data.get("daily_streak") or 1)

            if last_claim_date == yesterday_str:
                new_day = current_day + 1
                if new_day > 30: new_day = 1
            else:
                new_day = 1

            game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
            rewards_list = parse_daily_rewards(game_settings.get("daily_rewards"))

            day_index = min(max(0, new_day - 1), len(rewards_list) - 1)
            reward_amount = float(rewards_list[day_index])

            current_bal = float(data.get("balance", 0.0))
            new_balance = round(current_bal + reward_amount, 2)

            transaction.update(ref, {
                "balance": new_balance,
                "daily_day": new_day,
                "daily_streak": new_day,
                "last_daily_claim_date": today_str,
                "ads_watched": firestore.Increment(1)
            })

            return {
                "reward": reward_amount,
                "new_balance": new_balance,
                "daily_day": new_day,
                "last_daily_claim_date": today_str,
                "server_time": now_dt.isoformat()
            }, None, 200

        transaction = db.transaction()
        res_data, err_msg, status_code = run_daily_claim_transaction(transaction, user_ref)

        if err_msg: return jsonify({"success": False, "error": err_msg, "server_time": now_dt.isoformat()}), status_code

        return jsonify({
            "success": True,
            "reward": res_data["reward"],
            "new_balance": res_data["new_balance"],
            "daily_day": res_data["daily_day"],
            "daily_streak": res_data["daily_day"],
            "last_daily_claim_date": res_data["last_daily_claim_date"],
            "server_time": res_data["server_time"]
        }), 200

    except Exception as e:
        print(f"Error daily_claim: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة اليومية"}), 500

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from google.cloud import firestore
from core.security import get_authenticated_user
from database import db, get_game_settings

farm_bp = Blueprint('farm', __name__)

DEFAULT_GAME_SETTINGS = {
    "daily_rewards": [
        100, 150, 200, 250, 300, 
        350, 400, 450, 500, 550, 
        600, 600, 650, 650, 700, 
        700, 750, 750, 800, 800, 
        850, 850, 900, 900, 950, 
        950, 1000, 1000, 1100, 1250
    ],
    "mining_config": {
        "daily_boost_reward": 2.0
    },
    "storage_capacities": {
        "0": 200.0, "1": 600.0, "2": 1500.0, "3": 3500.0, "4": 8000.0,
        "5": 18000.0, "6": 40000.0, "7": 90000.0, "8": 200000.0, "9": 450000.0, "10": 1000000.0
    },
    "upgrade_config": {
        "1": {"base_cost": 2000.0, "rate_bonus": 5.0},
        "2": {"base_cost": 7000.0, "rate_bonus": 15.0},
        "3": {"base_cost": 18000.0, "rate_bonus": 35.0},
        "4": {"base_cost": 45000.0, "rate_bonus": 80.0},
        "5": {"base_cost": 110000.0, "rate_bonus": 180.0},
        "6": {"base_cost": 260000.0, "rate_bonus": 400.0},
        "7": {"base_cost": 600000.0, "rate_bonus": 900.0},
        "8": {"base_cost": 1400000.0, "rate_bonus": 2000.0},
        "9": {"base_cost": 3200000.0, "rate_bonus": 4500.0}
    }
}

def parse_daily_rewards(rewards_data):
    if isinstance(rewards_data, list):
        return rewards_data
    if isinstance(rewards_data, dict):
        res = []
        for i in range(1, 31):
            val = rewards_data.get(f"day_{i}") or rewards_data.get(str(i)) or 100
            res.append(int(val))
        return res
    return DEFAULT_GAME_SETTINGS["daily_rewards"]

def get_storage_capacity(storage_level, settings):
    try:
        lvl = int(storage_level)
    except (ValueError, TypeError):
        lvl = 0
    if lvl < 0: lvl = 0
    elif lvl > 10: lvl = 10
    
    caps = settings.get("storage_capacities") or settings.get("storage_config") or DEFAULT_GAME_SETTINGS["storage_capacities"]
    
    if str(lvl) in caps and isinstance(caps[str(lvl)], dict):
        return float(caps[str(lvl)].get("capacity", 200.0))
        
    val = caps.get(str(lvl)) or caps.get(lvl) or 200.0
    return float(val)

@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res

    req_data = request.get_json(silent=True)
    if not isinstance(req_data, dict):
        req_data = {}
        
    start_param = req_data.get('start_param') or (user_info.get('start_param') if isinstance(user_info, dict) else '')
    user_id_str = str(telegram_id)

    try:
        user_ref = db.collection('users').document(user_id_str)
        user_doc = user_ref.get()
        now = datetime.now(timezone.utc)
        game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS

        if not user_doc.exists:
            referred_by = None
            if start_param and isinstance(start_param, str) and start_param.startswith('ref_'):
                parts = start_param.split('_')
                if len(parts) > 1 and parts[1] != user_id_str:
                    potential_referrer = str(parts[1])
                    referred_by = potential_referrer
                    try:
                        referrer_ref = db.collection('users').document(potential_referrer)
                        if referrer_ref.get().exists:
                            referrer_ref.update({'invited_friends_count': firestore.Increment(1)})
                            
                            first_name = user_info.get('first_name', 'صديق') if isinstance(user_info, dict) else 'صديق'
                            friend_ref_in_sub = referrer_ref.collection('friends').document(user_id_str)
                            friend_ref_in_sub.set({
                                'tg_id': user_id_str,
                                'first_name': first_name,
                                'joined_at': now.isoformat(),
                                'earned_from_him': 0.0
                            }, merge=True)
                    except Exception as e:
                        print(f"Error updating referrer count: {e}")

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
                "last_claim_time": now.isoformat(), 
                "last_daily_claim_date": None, 
                "last_boost_date": None,
                "ads_watched": 0, 
                "upgrades": {},
                "referred_by": referred_by,
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
        max_cap = get_storage_capacity(storage_level, game_settings)
        user_data["max_cap"] = max_cap

        last_daily_date = user_data.get("last_daily_claim_date")
        if last_daily_date:
            try:
                last_date_obj = datetime.strptime(last_daily_date, '%Y-%m-%d').date()
                days_diff = (now.date() - last_date_obj).days
                if days_diff > 1:
                    user_data["daily_day"] = 1
                    user_ref.update({"daily_day": 1})
            except Exception: 
                pass

        last_claim_str = user_data.get("last_claim_time")
        hourly_rate = float(user_data.get("hourly_rate", 0.0))

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str).replace('Z', '+00:00'))
                if last_claim.tzinfo is None: 
                    last_claim = last_claim.replace(tzinfo=timezone.utc)
                
                seconds_passed = (now - last_claim).total_seconds()
                if seconds_passed > 0:
                    mined = (hourly_rate / 3600.0) * seconds_passed
                    user_data["unclaimed"] = min(mined, max_cap)
            except Exception: 
                pass
        else:
            user_data["last_claim_time"] = now.isoformat()
            user_ref.update({"last_claim_time": now.isoformat()})

        if not isinstance(user_data.get("upgrades"), dict):
            user_data["upgrades"] = {}

        parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))

        upgrade_configs = game_settings.get("upgrade_config") or game_settings.get("speed_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
        upgrade_costs = {}
        for k, v in upgrade_configs.items():
            cost_val = v.get("base_cost") if isinstance(v, dict) and "base_cost" in v else v.get("price", 0)
            upgrade_costs[int(k)] = float(cost_val)

        mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
        daily_boost_reward = float(mining_cfg.get("daily_boost_reward", 2.0))

        return jsonify({
            "success": True, 
            "player": user_data, 
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
            referred_by = user_data.get("referred_by")
            
            inviter_ref = None
            inviter_snap = None
            inviter_friend_doc = None
            
            if referred_by:
                inviter_ref = db.collection('users').document(str(referred_by))
                inviter_snap = inviter_ref.get(transaction=transaction)
                inviter_friend_doc = inviter_ref.collection('friends').document(user_id_str)

            now = datetime.now(timezone.utc)
            last_claim_str = user_data.get("last_claim_time")
            hourly_rate = float(user_data.get("hourly_rate", 0.0))
            storage_level = user_data.get("storage_level", 0)
            max_cap = get_storage_capacity(storage_level, game_settings)
            unclaimed = 0.0

            if last_claim_str:
                try:
                    last_claim = datetime.fromisoformat(str(last_claim_str).replace('Z', '+00:00'))
                    if last_claim.tzinfo is None: 
                        last_claim = last_claim.replace(tzinfo=timezone.utc)
                        
                    seconds_passed = (now - last_claim).total_seconds()
                    if seconds_passed > 0:
                        mined = (hourly_rate / 3600.0) * seconds_passed
                        unclaimed = min(mined, max_cap)
                except Exception: 
                    pass

            if unclaimed <= 0: 
                return None, "لا يوجد رصيد حالياً في المخزن.", 400

            current_bal = float(user_data.get("balance", 0.0))
            new_balance = current_bal + unclaimed
            now_iso = now.isoformat()

            update_data = {
                "balance": new_balance,
                "unclaimed": 0.0,
                "max_cap": max_cap,
                "last_claim_time": now_iso
            }

            if referred_by and inviter_snap and inviter_snap.exists:
                ref_bonus = unclaimed * 0.10
                transaction.update(inviter_ref, {
                    "pending_ref_earnings": firestore.Increment(ref_bonus),
                    "total_ref_earnings": firestore.Increment(ref_bonus)
                })
                if inviter_friend_doc:
                    transaction.set(inviter_friend_doc, {
                        "earned_from_him": firestore.Increment(ref_bonus)
                    }, merge=True)

            transaction.update(ref, update_data)
            return {"new_balance": new_balance, "claimed_amount": unclaimed, "last_claim_time": now_iso}, None, 200

        transaction = db.transaction()
        result_data, error_msg, status_code = run_claim_transaction(transaction, user_ref)
        
        if error_msg:
            return jsonify({"success": False, "error": error_msg}), status_code

        return jsonify({
            "success": True,
            "new_balance": result_data["new_balance"],
            "claimed_amount": result_data["claimed_amount"],
            "last_claim_time": result_data["last_claim_time"]
        }), 200

    except Exception as e:
        print(f"Error claim: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في عملية التجميع"}), 500

@farm_bp.route('/upgrade', methods=['POST'])
def upgrade_field():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    req_data = request.get_json(silent=True)
    if not isinstance(req_data, dict):
        req_data = {}

    level = req_data.get('level')

    try:
        level = int(level)
        if level < 1 or level > 9:
            return jsonify({"success": False, "error": "مستوى ترقية غير صالح"}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "بيانات الترقية غير صالحة"}), 400

    game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
    upgrade_configs = game_settings.get("upgrade_config") or game_settings.get("speed_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
    config = upgrade_configs.get(str(level)) or upgrade_configs.get(level)

    if not config:
        return jsonify({"success": False, "error": "إعدادات الترقية غير موجودة"}), 400

    user_id_str = str(telegram_id)
    user_ref = db.collection('users').document(user_id_str)

    try:
        @firestore.transactional
        def run_upgrade_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return None, "المستخدم غير موجود", 404

            data = snapshot.to_dict() or {}
            current_bal = float(data.get("balance", 0.0))
            cost = float(config.get("base_cost") or config.get("price", 0.0))

            if current_bal < cost:
                return None, f"رصيدك غير كافٍ! تحتاج إلى {cost:,.0f} ZN", 400

            upgrades = data.get("upgrades") or {}
            lvl_key = f"lvl{level}"
            current_count = int(upgrades.get(lvl_key, 0))

            if current_count >= 10:
                return None, "وصلت للحد الأقصى من الترقية لهذا المستوى", 400

            if level > 1:
                prev_lvl_count = int(upgrades.get(f"lvl{level-1}", 0))
                if prev_lvl_count <= 0:
                    return None, "يجب فتح المستوى السابق أولاً", 400

            upgrades[lvl_key] = current_count + 1
            new_bal = current_bal - cost
            rate_bonus = float(config.get("rate_bonus") or config.get("rate", 0.0))
            new_rate = float(data.get("hourly_rate", 0.0)) + rate_bonus

            transaction.update(ref, {
                "balance": new_bal,
                "hourly_rate": new_rate,
                "upgrades": upgrades
            })

            return {"new_balance": new_bal, "new_hourly_rate": new_rate, "upgrades": upgrades}, None, 200

        transaction = db.transaction()
        res_data, err_msg, status_code = run_upgrade_transaction(transaction, user_ref)

        if err_msg:
            return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({
            "success": True,
            "new_balance": res_data["new_balance"],
            "new_hourly_rate": res_data["new_hourly_rate"],
            "upgrades": res_data["upgrades"]
        }), 200

    except Exception as e:
        print(f"Error in upgrade: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء تنفيذ الترقية"}), 500

@farm_bp.route('/daily_boost', methods=['POST'])
def daily_boost():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    user_id_str = str(telegram_id)
    user_ref = db.collection('users').document(user_id_str)
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    boost_reward = float(mining_cfg.get("daily_boost_reward", 2.0))

    try:
        @firestore.transactional
        def run_boost_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return None, "المستخدم غير موجود", 404

            data = snapshot.to_dict() or {}
            if data.get("last_boost_date") == today_str:
                return None, "لقد استخدمت التسريع اليومي بالفعل اليوم!", 400

            current_rate = float(data.get("hourly_rate", 0.0))
            new_rate = current_rate + boost_reward

            transaction.update(ref, {
                "hourly_rate": new_rate,
                "last_boost_date": today_str,
                "ads_watched": firestore.Increment(1)
            })

            return {"new_rate": new_rate, "last_boost_date": today_str, "added_rate": boost_reward}, None, 200

        transaction = db.transaction()
        res_data, err_msg, status_code = run_boost_transaction(transaction, user_ref)

        if err_msg:
            return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({
            "success": True,
            "new_rate": res_data["new_rate"],
            "last_boost_date": res_data["last_boost_date"],
            "added_rate": res_data["added_rate"]
        }), 200

    except Exception as e:
        print(f"Error daily_boost: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء تفعيل التسريع"}), 500

@farm_bp.route('/daily_claim', methods=['POST'])
def daily_claim():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    user_id_str = str(telegram_id)
    user_ref = db.collection('users').document(user_id_str)
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    try:
        @firestore.transactional
        def run_daily_claim_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return None, "المستخدم غير موجود", 404

            data = snapshot.to_dict() or {}
            if data.get("last_daily_claim_date") == today_str:
                return None, "لقد استلمت مكافأتك اليومية بالفعل!", 400

            current_day = int(data.get("daily_day", 1))
            game_settings = get_game_settings() or DEFAULT_GAME_SETTINGS
            rewards_list = parse_daily_rewards(game_settings.get("daily_rewards"))

            day_index = min(current_day - 1, len(rewards_list) - 1)
            reward_amount = float(rewards_list[day_index])

            current_bal = float(data.get("balance", 0.0))
            new_balance = current_bal + reward_amount
            next_day = current_day + 1

            transaction.update(ref, {
                "balance": new_balance,
                "daily_day": next_day,
                "last_daily_claim_date": today_str,
                "ads_watched": firestore.Increment(1)
            })

            return {
                "reward": reward_amount,
                "new_balance": new_balance,
                "daily_day": next_day,
                "last_daily_claim_date": today_str
            }, None, 200

        transaction = db.transaction()
        res_data, err_msg, status_code = run_daily_claim_transaction(transaction, user_ref)

        if err_msg:
            return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({
            "success": True,
            "reward": res_data["reward"],
            "new_balance": res_data["new_balance"],
            "daily_day": res_data["daily_day"],
            "last_daily_claim_date": res_data["last_daily_claim_date"]
        }), 200

    except Exception as e:
        print(f"Error daily_claim: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة اليومية"}), 500

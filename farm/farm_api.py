from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from google.cloud import firestore
from core.security import get_authenticated_user
from database import db

farm_bp = Blueprint('farm', __name__)

STORAGE_CAPACITIES = {
    0: 100.0, 1: 250.0, 2: 450.0, 3: 750.0, 4: 1000.0,
    5: 1500.0, 6: 2000.0, 7: 3000.0, 8: 4000.0, 9: 5500.0, 10: 7000.0
}

UPGRADE_CONFIG = {
    1: {"base_cost": 500.0, "rate_bonus": 1.0},
    2: {"base_cost": 2500.0, "rate_bonus": 5.0},
    3: {"base_cost": 10000.0, "rate_bonus": 20.0},
    4: {"base_cost": 50000.0, "rate_bonus": 100.0},
    5: {"base_cost": 200000.0, "rate_bonus": 450.0},
    6: {"base_cost": 1000000.0, "rate_bonus": 2000.0},
    7: {"base_cost": 5000000.0, "rate_bonus": 10000.0},
    8: {"base_cost": 25000000.0, "rate_bonus": 50000.0},
    9: {"base_cost": 100000000.0, "rate_bonus": 200000.0}
}

DAILY_REWARDS_DEFAULT = [
    3000, 4000, 5000, 6000, 7500, 10000, 12000, 15000, 18000, 20000,
    25000, 30000, 35000, 40000, 50000, 60000, 70000, 80000, 90000, 100000,
    120000, 150000, 180000, 220000, 250000, 300000, 400000, 500000, 750000, 1000000
]

def get_storage_capacity(storage_level):
    try:
        lvl = int(storage_level)
    except (ValueError, TypeError):
        lvl = 0
    if lvl < 0: lvl = 0
    elif lvl > 10: lvl = 10
    return STORAGE_CAPACITIES.get(lvl, 100.0)

def get_game_settings():
    try:
        config_doc = db.collection('config').document('game_settings').get()
        if config_doc.exists:
            return config_doc.to_dict().get('daily_rewards', DAILY_REWARDS_DEFAULT)
        return DAILY_REWARDS_DEFAULT
    except Exception:
        return DAILY_REWARDS_DEFAULT

@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth: 
        return error_response

    req_data = request.get_json(silent=True) or {}
    start_param = req_data.get('start_param', '')

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        now = datetime.now(timezone.utc)

        if not user_doc.exists:
            referred_by = None
            if start_param and isinstance(start_param, str) and start_param.startswith('ref_'):
                parts = start_param.split('_')
                if len(parts) > 1 and parts[1] != str(telegram_id):
                    potential_referrer = parts[1]
                    referred_by = potential_referrer
                    try:
                        referrer_ref = db.collection('users').document(potential_referrer)
                        if referrer_ref.get().exists:
                            referrer_ref.update({'invited_friends_count': firestore.Increment(1)})
                    except Exception as e:
                        print(f"Error updating referrer count: {e}")

            user_data = {
                "telegram_id": telegram_id, 
                "balance": 0.0, 
                "ad_balance": 0.0,
                "usd_balance": 0.0,
                "hourly_rate": 0.0,
                "unclaimed": 0.0, 
                "storage_level": 0,
                "max_cap": 100.0, 
                "daily_day": 1,
                "last_claim_time": now.isoformat(), 
                "last_daily_claim_date": None, 
                "last_boost_date": None,
                "ads_watched": 0, 
                "upgrades": {},
                "referred_by": referred_by,
                "pending_ref_earnings": 0.0,
                "invited_friends_count": 0,
                "ref_generated_amount": 0.0,
                "claimed_ref_tasks": []
            }
            user_ref.set(user_data)
        else:
            user_data = user_doc.to_dict()

        storage_level = user_data.get("storage_level", 0)
        max_cap = get_storage_capacity(storage_level)
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
        unclaimed = float(user_data.get("unclaimed", 0.0))

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str))
                if last_claim.tzinfo is None: 
                    last_claim = last_claim.replace(tzinfo=timezone.utc)
                
                seconds_passed = (now - last_claim).total_seconds()
                if seconds_passed > 0:
                    mined = (hourly_rate / 3600.0) * seconds_passed
                    unclaimed = min(unclaimed + mined, max_cap)
            except Exception: 
                pass

        user_data["unclaimed"] = unclaimed
        user_data["last_claim_time"] = now.isoformat()
        
        if not isinstance(user_data.get("upgrades"), dict):
            user_data["upgrades"] = {}
        
        user_ref.update({
            "unclaimed": unclaimed, 
            "max_cap": max_cap,
            "last_claim_time": now.isoformat()
        })
        
        return jsonify({
            "success": True, 
            "player": user_data, 
            "game_config": {"daily_rewards": get_game_settings()}
        }), 200

    except Exception as e:
        print(f"Error player_data: {e}")
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500

@farm_bp.route('/claim', methods=['POST'])
def claim_mined_tokens():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: 
        return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        
        @firestore.transactional
        def run_claim_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return None, "الحساب غير موجود", 404

            user_data = snapshot.to_dict()
            now = datetime.now(timezone.utc)
            
            last_claim_str = user_data.get("last_claim_time")
            hourly_rate = float(user_data.get("hourly_rate", 0.0))
            storage_level = user_data.get("storage_level", 0)
            max_cap = get_storage_capacity(storage_level)
            unclaimed = float(user_data.get("unclaimed", 0.0))

            if last_claim_str:
                try:
                    last_claim = datetime.fromisoformat(str(last_claim_str))
                    if last_claim.tzinfo is None: 
                        last_claim = last_claim.replace(tzinfo=timezone.utc)
                        
                    seconds_passed = (now - last_claim).total_seconds()
                    if seconds_passed > 0:
                        mined = (hourly_rate / 3600.0) * seconds_passed
                        unclaimed = min(unclaimed + mined, max_cap)
                except Exception: 
                    pass

            if unclaimed <= 0: 
                return None, "لا يوجد رصيد حالياً في المخزن.", 400

            current_bal = float(user_data.get("balance", 0.0))
            new_balance = current_bal + unclaimed
            
            update_data = {
                "balance": new_balance,
                "unclaimed": 0.0,
                "max_cap": max_cap,
                "last_claim_time": now.isoformat()
            }

            referred_by = user_data.get("referred_by")
            upgrades = user_data.get("upgrades", {})
            
            total_upgrades = 0
            if isinstance(upgrades, dict):
                for k, v in upgrades.items():
                    try: 
                        total_upgrades += int(v)
                    except (ValueError, TypeError): 
                        pass

            if referred_by and total_upgrades >= 3:
                bonus_for_inviter = unclaimed * 0.10
                try:
                    inviter_ref = db.collection('users').document(referred_by)
                    if inviter_ref.get().exists:
                        transaction.update(inviter_ref, {
                            "pending_ref_earnings": firestore.Increment(bonus_for_inviter),
                            "ref_generated_amount": firestore.Increment(bonus_for_inviter)
                        })
                        update_data["generated_for_inviter"] = firestore.Increment(bonus_for_inviter)
                except Exception as e:
                    print(f"Error updating inviter balance: {e}")

            transaction.update(ref, update_data)
            return {"claimed": unclaimed, "new_balance": new_balance}, None, 200

        transaction = db.transaction()
        result, err_msg, status_code = run_claim_transaction(transaction, user_ref)
        
        if err_msg:
            return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({"success": True, "claimed": result["claimed"], "new_balance": result["new_balance"]}), 200

    except Exception as e:
        print(f"Error in claim: {e}")
        return jsonify({"success": False, "error": "خطأ في التجميع"}), 500

@farm_bp.route('/upgrade', methods=['POST'])
def upgrade_level():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: 
        return error_response

    req_data = request.get_json(silent=True) or {}
    try:
        level = int(req_data.get('level', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مستوى غير صالح"}), 400

    if level < 1 or level > 9:
        return jsonify({"success": False, "error": "مستوى ترقية غير معروف"}), 400

    try:
        user_ref = db.collection('users').document(telegram_id)

        @firestore.transactional
        def run_upgrade_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return None, "الحساب غير موجود", 404

            user_data = snapshot.to_dict()
            upgrades = user_data.get("upgrades", {})
            if not isinstance(upgrades, dict):
                upgrades = {}

            current_count = int(upgrades.get(f"lvl{level}", 0))
            if current_count >= 10:
                return None, "لقد وصلت للحد الأقصى لهذا المستوى", 400

            if level > 1:
                prev_count = int(upgrades.get(f"lvl{level-1}", 0))
                if prev_count <= 0:
                    return None, "يجب فتح المستوى السابق أولاً", 400

            cfg = UPGRADE_CONFIG.get(level, {"base_cost": 1000.0, "rate_bonus": 1.0})
            cost = cfg["base_cost"] * (1.5 ** current_count)
            rate_bonus = cfg["rate_bonus"]

            current_balance = float(user_data.get("balance", 0.0))
            if current_balance < cost:
                return None, "رصيدك غير كافٍ لإجراء الترقية", 400

            new_balance = current_balance - cost
            upgrades[f"lvl{level}"] = current_count + 1
            new_hourly_rate = float(user_data.get("hourly_rate", 0.0)) + rate_bonus

            transaction.update(ref, {
                "balance": new_balance,
                "upgrades": upgrades,
                "hourly_rate": new_hourly_rate
            })

            return {"new_balance": new_balance, "new_hourly_rate": new_hourly_rate}, None, 200

        transaction = db.transaction()
        result, err_msg, status_code = run_upgrade_transaction(transaction, user_ref)

        if err_msg:
            return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({
            "success": True, 
            "new_balance": result["new_balance"], 
            "new_hourly_rate": result["new_hourly_rate"]
        }), 200

    except Exception as e:
        print(f"Error in upgrade: {e}")
        return jsonify({"success": False, "error": "خطأ في تنفيذ الترقية"}), 500

@farm_bp.route('/daily_boost', methods=['POST'])
def daily_boost():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: 
        return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        
        @firestore.transactional
        def run_boost_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return None, "الحساب غير موجود", 404

            user_data = snapshot.to_dict()
            today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            
            if user_data.get("last_boost_date") == today_str:
                return None, "لقد استخدمت التسريع اليوم! انتظر لمنتصف الليل.", 400

            new_rate = float(user_data.get("hourly_rate", 0.0)) + 1.0
            ads_watched = int(user_data.get("ads_watched", 0)) + 1

            transaction.update(ref, {
                "hourly_rate": new_rate,
                "last_boost_date": today_str,
                "ads_watched": ads_watched
            })
            return {"new_rate": new_rate}, None, 200

        transaction = db.transaction()
        result, err_msg, status_code = run_boost_transaction(transaction, user_ref)

        if err_msg:
            return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({"success": True, "new_rate": result["new_rate"]}), 200

    except Exception as e:
        print(f"Error in daily_boost: {e}")
        return jsonify({"success": False, "error": "خطأ في تفعيل التسريع"}), 500

@farm_bp.route('/daily_claim', methods=['POST'])
def daily_claim():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: 
        return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)

        @firestore.transactional
        def run_daily_claim_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return None, "اللاعب غير مسجل", 404

            user_data = snapshot.to_dict()
            now = datetime.now(timezone.utc)
            today_str = now.strftime('%Y-%m-%d')
            last_daily_date = user_data.get("last_daily_claim_date")
            current_day = int(user_data.get("daily_day", 1))
            reset_message = None

            if last_daily_date == today_str:
                return None, "لقد استلمت المكافأة اليوم بالفعل!", 400

            if last_daily_date:
                try:
                    last_date_obj = datetime.strptime(last_daily_date, '%Y-%m-%d').date()
                    if (now.date() - last_date_obj).days > 1:
                        current_day = 1
                        reset_message = "⚠️ تم تصفير التسجيل اليومي لعدم الدخول أمس!"
                except Exception: 
                    pass

            daily_rewards = get_game_settings()
            reward_amount = daily_rewards[(current_day - 1) % len(daily_rewards)]

            new_balance = float(user_data.get("balance", 0.0)) + reward_amount
            next_day = current_day + 1 if current_day < len(daily_rewards) else 1
            ads_watched = int(user_data.get("ads_watched", 0)) + 1

            transaction.update(ref, {
                "balance": new_balance,
                "daily_day": next_day,
                "last_daily_claim_date": today_str,
                "ads_watched": ads_watched
            })

            return {
                "reward": reward_amount, 
                "new_balance": new_balance, 
                "reset_msg": reset_message
            }, None, 200

        transaction = db.transaction()
        result, err_msg, status_code = run_daily_claim_transaction(transaction, user_ref)

        if err_msg:
            return jsonify({"success": False, "error": err_msg}), status_code

        return jsonify({
            "success": True, 
            "reward": result["reward"], 
            "new_balance": result["new_balance"],
            "reset_msg": result["reset_msg"]
        }), 200

    except Exception as e:
        print(f"Error in daily_claim: {e}")
        return jsonify({"success": False, "error": "خطأ أثناء الاستلام"}), 500

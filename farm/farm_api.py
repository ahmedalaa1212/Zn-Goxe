# farm/farm_api.py
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from core.security import get_authenticated_user
from database import db

farm_bp = Blueprint('farm', __name__)

DAILY_REWARDS_DEFAULT = [
    3000, 4000, 5000, 6000, 7500,
    10000, 12000, 15000, 18000, 20000,
    25000, 30000, 35000, 40000, 50000,
    60000, 70000, 80000, 90000, 100000,
    120000, 150000, 180000, 220000, 250000,
    300000, 400000, 500000, 750000, 1000000
]

def get_game_settings():
    try:
        config_ref = db.collection('config').document('game_settings')
        config_doc = config_ref.get()
        if config_doc.exists:
            data = config_doc.to_dict()
            return data.get('daily_rewards', DAILY_REWARDS_DEFAULT)
        else:
            config_ref.set({'daily_rewards': DAILY_REWARDS_DEFAULT})
            return DAILY_REWARDS_DEFAULT
    except Exception as e:
        return DAILY_REWARDS_DEFAULT

@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    is_post = (request.method == 'POST')
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=is_post)
    if not is_auth: return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        now = datetime.now(timezone.utc)

        if not user_doc.exists:
            user_data = {
                "telegram_id": telegram_id,
                "balance": 0.0,
                "hourly_rate": 100.0,
                "unclaimed": 0.0,
                "max_cap": 10000.0,
                "daily_day": 1,
                "last_claim_time": now.isoformat(),
                "last_daily_claim_time": None,
                "last_boost_time": None, # 🟢 حقل التسريع
                "ads_watched": 0,
                "upgrades": {}
            }
            user_ref.set(user_data)
        else:
            user_data = user_doc.to_dict()
            if "ads_watched" not in user_data: user_data["ads_watched"] = 0
            if "last_boost_time" not in user_data: user_data["last_boost_time"] = None # 🟢 تأمين القدامى

        last_claim_str = user_data.get("last_claim_time")
        hourly_rate = float(user_data.get("hourly_rate", 100.0))
        max_cap = float(user_data.get("max_cap", 10000.0))
        unclaimed = float(user_data.get("unclaimed", 0.0))

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str))
                if last_claim.tzinfo is None: last_claim = last_claim.replace(tzinfo=timezone.utc)
                seconds_passed = (now - last_claim).total_seconds()
                if seconds_passed > 0:
                    mined = (hourly_rate / 3600.0) * seconds_passed
                    unclaimed = min(unclaimed + mined, max_cap)
            except Exception: pass

        user_data["unclaimed"] = unclaimed
        user_data["last_claim_time"] = now.isoformat()
        user_ref.update({"unclaimed": unclaimed, "last_claim_time": now.isoformat()})
        
        return jsonify({"success": True, "player": user_data, "game_config": {"daily_rewards": get_game_settings()}}), 200

    except Exception:
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500

@farm_bp.route('/claim', methods=['POST'])
def claim_mined_tokens():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        if not user_doc.exists: return jsonify({"success": False, "error": "الحساب غير موجود"}), 404

        user_data = user_doc.to_dict()
        now = datetime.now(timezone.utc)
        
        last_claim_str = user_data.get("last_claim_time")
        hourly_rate = float(user_data.get("hourly_rate", 100.0))
        max_cap = float(user_data.get("max_cap", 10000.0))
        unclaimed = float(user_data.get("unclaimed", 0.0))

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str))
                if last_claim.tzinfo is None: last_claim = last_claim.replace(tzinfo=timezone.utc)
                seconds_passed = (now - last_claim).total_seconds()
                
                if seconds_passed < 10: return jsonify({"success": False, "error": "انتظر قليلاً"}), 429
                if seconds_passed > 0:
                    mined = (hourly_rate / 3600.0) * seconds_passed
                    unclaimed = min(unclaimed + mined, max_cap)
            except Exception: pass

        if unclaimed <= 0: return jsonify({"success": False, "error": "لا يوجد رصيد"}), 400

        new_balance = float(user_data.get("balance", 0.0)) + unclaimed
        ads_watched = int(user_data.get("ads_watched", 0)) + 1

        user_ref.update({
            "balance": new_balance,
            "unclaimed": 0.0,
            "last_claim_time": now.isoformat(),
            "ads_watched": ads_watched
        })
        return jsonify({"success": True, "claimed": unclaimed, "new_balance": new_balance}), 200

    except Exception:
        return jsonify({"success": False, "error": "خطأ في التجميع"}), 500

# 🟢 الدالة الجديدة الخاصة بزرار التسريع
@farm_bp.route('/daily_boost', methods=['POST'])
def daily_boost():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        if not user_doc.exists: return jsonify({"success": False, "error": "الحساب غير موجود"}), 404

        user_data = user_doc.to_dict()
        now = datetime.now(timezone.utc)
        last_boost_str = user_data.get("last_boost_time")

        if last_boost_str:
            try:
                last_boost = datetime.fromisoformat(str(last_boost_str))
                if last_boost.tzinfo is None: last_boost = last_boost.replace(tzinfo=timezone.utc)
                time_passed = now - last_boost
                
                if time_passed < timedelta(hours=24):
                    return jsonify({"success": False, "error": "التسريع متاح مرة واحدة كل 24 ساعة!"}), 400
            except Exception: pass

        # 🟢 زيادة سرعة التعدين بمقدار 50 في الساعة (بشكل دائم كحافز يومي)
        current_rate = float(user_data.get("hourly_rate", 100.0))
        new_rate = current_rate + 50.0
        ads_watched = int(user_data.get("ads_watched", 0)) + 1

        user_ref.update({
            "hourly_rate": new_rate,
            "last_boost_time": now.isoformat(),
            "ads_watched": ads_watched
        })

        return jsonify({"success": True, "new_rate": new_rate}), 200

    except Exception:
        return jsonify({"success": False, "error": "خطأ في تفعيل التسريع"}), 500

@farm_bp.route('/daily_claim', methods=['POST'])
def daily_claim():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        if not user_doc.exists: return jsonify({"success": False, "error": "اللاعب غير مسجل"}), 404

        user_data = user_doc.to_dict()
        now = datetime.now(timezone.utc)
        last_claim_str = user_data.get("last_daily_claim_time")
        current_day = int(user_data.get("daily_day", 1))

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str))
                if last_claim.tzinfo is None: last_claim = last_claim.replace(tzinfo=timezone.utc)
                time_passed = now - last_claim
                if time_passed < timedelta(hours=24): return jsonify({"success": False, "error": "يجب الانتظار 24 ساعة!"}), 400
                if time_passed > timedelta(hours=48): current_day = 1
            except Exception: pass

        daily_rewards = get_game_settings()
        reward_index = (current_day - 1) % 30
        reward_amount = daily_rewards[reward_index] if reward_index < len(daily_rewards) else DAILY_REWARDS_DEFAULT[reward_index % 30]

        new_balance = float(user_data.get("balance", 0.0)) + reward_amount
        next_day = current_day + 1 if current_day < 30 else 1
        ads_watched = int(user_data.get("ads_watched", 0)) + 1

        user_ref.update({
            "balance": new_balance,
            "daily_day": next_day,
            "last_daily_claim_time": now.isoformat(),
            "ads_watched": ads_watched
        })

        return jsonify({"success": True, "reward": reward_amount, "new_balance": new_balance}), 200

    except Exception:
        return jsonify({"success": False, "error": "خطأ أثناء الاستلام"}), 500

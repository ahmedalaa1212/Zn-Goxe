# farm/farm_api.py
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
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
        config_doc = db.collection('config').document('game_settings').get()
        if config_doc.exists:
            return config_doc.to_dict().get('daily_rewards', DAILY_REWARDS_DEFAULT)
        return DAILY_REWARDS_DEFAULT
    except:
        return DAILY_REWARDS_DEFAULT

@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth: return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        now = datetime.now(timezone.utc)
        today_str = now.strftime('%Y-%m-%d')

        if not user_doc.exists:
            user_data = {
                "telegram_id": telegram_id, "balance": 0.0, "hourly_rate": 0.0,
                "unclaimed": 0.0, "max_cap": 10000.0, "daily_day": 1,
                "last_claim_time": now.isoformat(), 
                "last_daily_claim_date": None, 
                "last_boost_date": None,
                "ads_watched": 0, "upgrades": {}
            }
            user_ref.set(user_data)
        else:
            user_data = user_doc.to_dict()

        # فحص التسجيل اليومي المتتالي (Streak Check)
        last_daily_date = user_data.get("last_daily_claim_date")
        if last_daily_date:
            try:
                last_date_obj = datetime.strptime(last_daily_date, '%Y-%m-%d').date()
                days_diff = (now.date() - last_date_obj).days
                if days_diff > 1:
                    user_data["daily_day"] = 1
                    user_ref.update({"daily_day": 1})
            except: pass

        # حساب التعدين المتراكم
        last_claim_str = user_data.get("last_claim_time")
        hourly_rate = float(user_data.get("hourly_rate", 0.0))
        max_cap = float(user_data.get("max_cap", 10000.0))
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
            except: pass

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
        hourly_rate = float(user_data.get("hourly_rate", 0.0))
        max_cap = float(user_data.get("max_cap", 10000.0))
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
            except: pass

        if unclaimed <= 0: 
            return jsonify({"success": False, "error": "لا يوجد رصيد حالياً في المخزن."}), 400

        new_balance = float(user_data.get("balance", 0.0)) + unclaimed
        user_ref.update({
            "balance": new_balance,
            "unclaimed": 0.0,
            "last_claim_time": now.isoformat()
        })
        return jsonify({"success": True, "claimed": unclaimed, "new_balance": new_balance}), 200
    except:
        return jsonify({"success": False, "error": "خطأ في التجميع"}), 500

@farm_bp.route('/daily_boost', methods=['POST'])
def daily_boost():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth: return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        if not user_doc.exists: return jsonify({"success": False, "error": "الحساب غير موجود"}), 404

        user_data = user_doc.to_dict()
        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # حماية صارمة من السيرفر
        if user_data.get("last_boost_date") == today_str:
            return jsonify({"success": False, "error": "لقد استخدمت التسريع اليوم! انتظر لمنتصف الليل."}), 400

        new_rate = float(user_data.get("hourly_rate", 0.0)) + 1.0
        ads_watched = int(user_data.get("ads_watched", 0)) + 1

        user_ref.update({
            "hourly_rate": new_rate,
            "last_boost_date": today_str,
            "ads_watched": ads_watched
        })
        return jsonify({"success": True, "new_rate": new_rate}), 200
    except:
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
        today_str = now.strftime('%Y-%m-%d')
        last_daily_date = user_data.get("last_daily_claim_date")
        current_day = int(user_data.get("daily_day", 1))
        reset_message = None

        if last_daily_date == today_str:
            return jsonify({"success": False, "error": "لقد استلمت المكافأة اليوم بالفعل!"}), 400

        if last_daily_date:
            try:
                last_date_obj = datetime.strptime(last_daily_date, '%Y-%m-%d').date()
                if (now.date() - last_date_obj).days > 1:
                    current_day = 1
                    reset_message = "⚠️ تم تصفير التسجيل اليومي لعدم الدخول أمس!"
            except: pass

        daily_rewards = get_game_settings()
        reward_amount = daily_rewards[(current_day - 1) % 30]

        new_balance = float(user_data.get("balance", 0.0)) + reward_amount
        next_day = current_day + 1 if current_day < 30 else 1
        ads_watched = int(user_data.get("ads_watched", 0)) + 1

        user_ref.update({
            "balance": new_balance,
            "daily_day": next_day,
            "last_daily_claim_date": today_str,
            "ads_watched": ads_watched
        })

        return jsonify({
            "success": True, 
            "reward": reward_amount, 
            "new_balance": new_balance,
            "reset_msg": reset_message
        }), 200
    except:
        return jsonify({"success": False, "error": "خطأ أثناء الاستلام"}), 500

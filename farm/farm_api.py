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
    except:
        return DAILY_REWARDS_DEFAULT

@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth: return error_response

    req_data = request.get_json() or {}
    start_param = req_data.get('start_param', '')

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        now = datetime.now(timezone.utc)

        if not user_doc.exists:
            referred_by = None
            if start_param and start_param.startswith('ref_'):
                potential_referrer = start_param.split('_')[1]
                if potential_referrer != str(telegram_id):
                    referred_by = potential_referrer
                    try:
                        referrer_ref = db.collection('users').document(potential_referrer)
                        referrer_ref.update({'invited_friends_count': firestore.Increment(1)})
                    except Exception as e:
                        print(f"Error updating referrer count: {e}")

            user_data = {
                "telegram_id": telegram_id, 
                "balance": 0.0, 
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
            except: pass

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
            except: pass

        user_data["unclaimed"] = unclaimed
        user_data["last_claim_time"] = now.isoformat()
        
        # التأكد من وجود المفاتيح الأساسية عشان مفيش حاجة تضرب في الفرونت إند
        user_data.setdefault("upgrades", {})
        
        user_ref.update({
            "unclaimed": unclaimed, 
            "max_cap": max_cap,
            "last_claim_time": now.isoformat()
        })
        
        return jsonify({"success": True, "player": user_data, "game_config": {"daily_rewards": get_game_settings()}}), 200

    except Exception as e:
        print(f"Error player_data: {e}")
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
            except: pass

        if unclaimed <= 0: 
            return jsonify({"success": False, "error": "لا يوجد رصيد حالياً في المخزن."}), 400

        new_balance = float(user_data.get("balance", 0.0)) + unclaimed
        
        update_data = {
            "balance": new_balance,
            "unclaimed": 0.0,
            "max_cap": max_cap,
            "last_claim_time": now.isoformat()
        }

        # ----------------------------------------------------
        # 🚀 نظام دعوة الأصدقاء - 10% من التعدين (تم التصحيح هنا)
        # ----------------------------------------------------
        referred_by = user_data.get("referred_by")
        upgrades = user_data.get("upgrades", {})
        
        # حساب إجمالي الترقيات بشكل صحيح بجمع القيم
        total_upgrades = 0
        if isinstance(upgrades, dict):
            for k, v in upgrades.items():
                try: total_upgrades += int(v)
                except: pass

        # شرط أن يكون اللاعب لديه 3 ترقيات على الأقل
        if referred_by and total_upgrades >= 3:
            bonus_for_inviter = unclaimed * 0.10
            try:
                inviter_ref = db.collection('users').document(referred_by)
                inviter_ref.update({
                    "pending_ref_earnings": firestore.Increment(bonus_for_inviter),
                    "ref_generated_amount": firestore.Increment(bonus_for_inviter)
                })
                # إضافة السجل للمستخدم الحالي
                update_data["generated_for_inviter"] = firestore.Increment(bonus_for_inviter)
            except Exception as e:
                print(f"Error updating inviter balance: {e}")
        # ----------------------------------------------------

        user_ref.update(update_data)
        return jsonify({"success": True, "claimed": unclaimed, "new_balance": new_balance}), 200
    except Exception as e:
        print(f"Error in claim: {e}")
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

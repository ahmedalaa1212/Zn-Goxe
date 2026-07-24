# farm/farm_api.py
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from core.security import get_authenticated_user
from database import db

farm_bp = Blueprint('farm', __name__)

# جدول جوائز الـ 30 يوم
DAILY_REWARDS = [
    3000, 4000, 5000, 6000, 7500,          # 1 - 5
    10000, 12000, 15000, 18000, 20000,     # 6 - 10
    25000, 30000, 35000, 40000, 50000,     # 11 - 15
    60000, 70000, 80000, 90000, 100000,    # 16 - 20
    120000, 150000, 180000, 220000, 250000,# 21 - 25
    300000, 400000, 500000, 750000, 1000000# 26 - 30
]


@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    """جلب بيانات المزرعة وحساب التعدين الأوفلاين"""
    is_post = (request.method == 'POST')
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=is_post)
    if not is_auth:
        return error_response

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
                "upgrades": {}
            }
            user_ref.set(user_data)
        else:
            user_data = user_doc.to_dict()

        # حساب التعدين الأوفلاين منذ آخر زيارة
        last_claim_str = user_data.get("last_claim_time")
        hourly_rate = float(user_data.get("hourly_rate", 100.0))
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
            except Exception as e:
                print(f"Date parse error: {e}")

        # تحديث بيانات التعدين في فايربيس
        user_data["unclaimed"] = unclaimed
        user_data["last_claim_time"] = now.isoformat()
        user_ref.update({
            "unclaimed": unclaimed,
            "last_claim_time": now.isoformat()
        })

        return jsonify({"success": True, "player": user_data}), 200

    except Exception as e:
        print(f"Player Data Error: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات اللاعب"}), 500


@farm_bp.route('/claim', methods=['POST'])
def claim_mined_tokens():
    """تجميع رصيد التعدين وإضافته إلى المحفظة"""
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "الحساب غير موجود"}), 404

        user_data = user_doc.to_dict()
        now = datetime.now(timezone.utc)

        # حساب الرصيد القابل للتجميع
        last_claim_str = user_data.get("last_claim_time")
        hourly_rate = float(user_data.get("hourly_rate", 100.0))
        max_cap = float(user_data.get("max_cap", 10000.0))
        unclaimed = float(user_data.get("unclaimed", 0.0))

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str))
                if last_claim.tzinfo is None:
                    last_claim = last_claim.replace(tzinfo=timezone.utc)
                
                seconds_passed = (now - last_claim).total_seconds()
                
                # 🛡️ نظام الحماية (Anti-Spam): منع التجميع السريع المتكرر (أقل من 10 ثوانٍ)
                if seconds_passed < 10:
                    return jsonify({"success": False, "error": "يرجى الانتظار قليلاً قبل التجميع مرة أخرى."}), 429
                    
                if seconds_passed > 0:
                    mined = (hourly_rate / 3600.0) * seconds_passed
                    unclaimed = min(unclaimed + mined, max_cap)
            except Exception:
                pass

        if unclaimed <= 0:
            return jsonify({"success": False, "error": "لا يوجد رصيد للتجميع حالياً"}), 400

        current_balance = float(user_data.get("balance", 0.0))
        new_balance = current_balance + unclaimed

        user_ref.update({
            "balance": new_balance,
            "unclaimed": 0.0,
            "last_claim_time": now.isoformat()
        })

        return jsonify({
            "success": True,
            "claimed": unclaimed,
            "new_balance": new_balance
        }), 200

    except Exception as e:
        print(f"Claim Error: {e}")
        return jsonify({"success": False, "error": "خطأ في عملية تجميع الرصيد"}), 500


@farm_bp.route('/daily_claim', methods=['POST'])
def daily_claim():
    """استلام الجائزة اليومية"""
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "اللاعب غير مسجل"}), 404

        user_data = user_doc.to_dict()
        now = datetime.now(timezone.utc)

        last_claim_str = user_data.get("last_daily_claim_time")
        current_day = int(user_data.get("daily_day", 1))

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str))
                if last_claim.tzinfo is None:
                    last_claim = last_claim.replace(tzinfo=timezone.utc)

                time_passed = now - last_claim

                if time_passed < timedelta(hours=24):
                    return jsonify({"success": False, "error": "يجب الانتظار 24 ساعة بين كل استلام!"}), 400

                # غياب أكتر من 48 ساعة يرجع لليوم الأول
                if time_passed > timedelta(hours=48):
                    current_day = 1
            except Exception as e:
                print(f"Daily date parse error: {e}")

        reward_index = (current_day - 1) % 30
        reward_amount = DAILY_REWARDS[reward_index]

        current_balance = float(user_data.get("balance", 0.0))
        new_balance = current_balance + reward_amount

        next_day = current_day + 1
        if next_day > 30:
            next_day = 1

        user_ref.update({
            "balance": new_balance,
            "daily_day": next_day,
            "last_daily_claim_time": now.isoformat()
        })

        return jsonify({
            "success": True,
            "reward": reward_amount,
            "new_balance": new_balance,
            "current_day": current_day,
            "next_day": next_day
        }), 200

    except Exception as e:
        print(f"Daily Claim Error: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام الجائزة اليومية"}), 500

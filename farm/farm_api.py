# farm/farm_api.py
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from core.security import get_authenticated_user
from database import db

farm_bp = Blueprint('farm', __name__)

# جدول جوائز الـ 30 يوم كاملة
DAILY_REWARDS = [
    3000, 4000, 5000, 6000, 7500,          # 1 - 5
    10000, 12000, 15000, 18000, 20000,     # 6 - 10
    25000, 30000, 35000, 40000, 50000,     # 11 - 15
    60000, 70000, 80000, 90000, 100000,    # 16 - 20
    120000, 150000, 180000, 220000, 250000,# 21 - 25
    300000, 400000, 500000, 750000, 1000000# 26 - 30
]

@farm_bp.route('/daily_status', methods=['GET'])
def get_daily_status():
    """فحص حالة التسجيل اليومي للمستخدم عند فتح اللعبة"""
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=False)
    if not is_auth:
        return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            # إنشاء حساب افتراضي لو أول مرة يدخل
            user_data = {
                "telegram_id": telegram_id,
                "balance": 0.0,
                "daily_day": 1,
                "last_daily_claim_time": None
            }
            user_ref.set(user_data)
        else:
            user_data = user_doc.to_dict()

        now = datetime.now(timezone.utc)
        last_claim = user_data.get("last_daily_claim_time")
        current_day = int(user_data.get("daily_day", 1))

        can_claim = True
        time_remaining_seconds = 0

        if last_claim:
            if last_claim.tzinfo is None:
                last_claim = last_claim.replace(tzinfo=timezone.utc)

            time_passed = now - last_claim

            # لو غاب أكتر من 48 ساعة -> يرجع لليوم الأول
            if time_passed > timedelta(hours=48):
                current_day = 1
                user_ref.update({"daily_day": 1})

            # لو مر أقل من 24 ساعة -> لا يمكن الاستلام
            elif time_passed < timedelta(hours=24):
                can_claim = False
                time_remaining_seconds = int((timedelta(hours=24) - time_passed).total_seconds())

        reward_index = (current_day - 1) % 30
        reward_amount = DAILY_REWARDS[reward_index]

        return jsonify({
            "success": True,
            "current_day": current_day,
            "can_claim": can_claim,
            "time_remaining_seconds": time_remaining_seconds,
            "reward_amount": reward_amount,
            "balance": user_data.get("balance", 0)
        }), 200

    except Exception as e:
        print(f"Daily Status Error: {e}")
        return jsonify({"success": False, "error": "خطأ في جلب بيانات التسجيل اليومي"}), 500


@farm_bp.route('/daily_claim', methods=['POST'])
def daily_claim():
    """دالة استلام الجائزة اليومية"""
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return error_response

    try:
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "اللاعب غير مسجل في النظام"}), 404

        user_data = user_doc.to_dict()
        now = datetime.now(timezone.utc)

        last_claim = user_data.get("last_daily_claim_time")
        current_day = int(user_data.get("daily_day", 1))

        if last_claim:
            if last_claim.tzinfo is None:
                last_claim = last_claim.replace(tzinfo=timezone.utc)

            time_passed = now - last_claim

            if time_passed < timedelta(hours=24):
                return jsonify({"success": False, "error": "يجب الانتظار لمرور 24 ساعة على آخر استلام!"}), 400

            if time_passed > timedelta(hours=48):
                current_day = 1

        reward_index = (current_day - 1) % 30
        reward_amount = DAILY_REWARDS[reward_index]

        current_balance = float(user_data.get("balance", 0))
        new_balance = current_balance + reward_amount

        new_day = current_day + 1
        if new_day > 30:
            new_day = 1

        user_ref.update({
            "balance": new_balance,
            "daily_day": new_day,
            "last_daily_claim_time": now
        })

        return jsonify({
            "success": True,
            "reward": reward_amount,
            "new_balance": new_balance,
            "current_day": current_day,
            "next_day": new_day
        }), 200

    except Exception as e:
        print(f"Daily Claim Error: {e}")
        return jsonify({"success": False, "error": "حدث خطأ داخلي في السيرفر"}), 500

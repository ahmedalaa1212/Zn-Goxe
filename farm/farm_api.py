# farm/farm_api.py
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from core.security import get_authenticated_user
from database import db  # الاتصال بقاعدة البيانات Firebase الموجودة في الجذر الرئيسي

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

@farm_bp.route('/daily_claim', methods=['POST'])
def daily_claim():
    # 1. التحقق من الهوية عبر حارس الأمن (Zero Trust)
    is_auth, telegram_id, error_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return error_response

    try:
        # 2. جلب بيانات اللاعب من قاعدة بيانات Firebase
        user_ref = db.collection('users').document(telegram_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "اللاعب غير مسجل في النظام"}), 404

        user_data = user_doc.to_dict()
        now = datetime.now(timezone.utc)
        
        last_claim = user_data.get("last_daily_claim_time")
        current_day = user_data.get("daily_day", 1)
        
        # 3. التحقق من الوقت والـ Streak (الحتة الصيعية)
        if last_claim:
            # التأكد من التوقيت الزمني
            if last_claim.tzinfo is None:
                last_claim = last_claim.replace(tzinfo=timezone.utc)
                
            time_passed = now - last_claim
            
            # أ. لو ممرش 24 ساعة لسه بدري
            if time_passed < timedelta(hours=24):
                return jsonify({"success": False, "error": "يجب الانتظار لمرور 24 ساعة على آخر استلام!"}), 400
            
            # ب. لو غاب أكتر من 48 ساعة (فوت يوم كامل م دخلش) -> نرجع العبد لليوم الأول فوراً! 😈
            if time_passed > timedelta(hours=48):
                current_day = 1

        # 4. حساب الجائزة الحالية من السيرفر حصراً
        reward_index = (current_day - 1) % 30
        reward_amount = DAILY_REWARDS[reward_index]
        
        # 5. حساب الرصيد الجديد واليوم القادم
        current_balance = float(user_data.get("balance", 0))
        new_balance = current_balance + reward_amount
        
        new_day = current_day + 1
        if new_day > 30:
            new_day = 1  # لو خلص الشهر يبدأ من جديد

        # 6. تحديث السجلات في Firebase
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

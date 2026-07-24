# farm/farm_api.py
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from core.security import verify_telegram_data
from core.database import db  # نفترض إنك مجهز اتصال Firebase هنا

farm_bp = Blueprint('farm', __name__)

DAILY_REWARDS = [
    3000, 4000, 5000, 6000, 7500,          
    10000, 12000, 15000, 18000, 20000,     
    25000, 30000, 35000, 40000, 50000,     
    60000, 70000, 80000, 90000, 100000,    
    120000, 150000, 180000, 220000, 250000,
    300000, 400000, 500000, 750000, 1000000
]

@farm_bp.route('/daily_claim', methods=['POST'])
def daily_claim():
    data = request.json
    init_data = data.get('initData')
    
    # 1. تطبيق مبدأ (Zero Trust) - التحقق من اللاعب
    user_data = verify_telegram_data(init_data)
    if not user_data:
        return jsonify({"success": False, "error": "بيانات غير صالحة، تم رفض الطلب!"}), 401
    
    user_id = str(user_data.get('id'))
    
    # 2. الاتصال بـ Firebase Firestore
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return jsonify({"success": False, "error": "اللاعب غير موجود في قاعدة البيانات!"}), 404
        
    user_info = user_doc.to_dict()
    now = datetime.now(timezone.utc)
    
    # التعامل مع وقت آخر استلام (Firebase بيخزن الوقت كـ Datetime)
    last_claim = user_info.get("last_daily_claim_time")
    current_day = user_info.get("daily_day", 1)
    
    # 3. التحقق من مرور 24 ساعة
    if last_claim:
        # التأكد إن last_claim فيه معلومات الـ timezone (للتوافق مع Python)
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)
            
        time_passed = now - last_claim
        if time_passed < timedelta(hours=24):
            return jsonify({"success": False, "error": "يجب الانتظار لمرور 24 ساعة!"}), 400

    # 4. حساب الجائزة من السيرفر (لا نثق في الواجهة)
    reward_index = (current_day - 1) % 30
    reward_amount = DAILY_REWARDS[reward_index]
    
    # 5. تحديث البيانات
    new_balance = user_info.get("balance", 0) + reward_amount
    new_day = current_day + 1 if current_day < 30 else 1
    
    user_ref.update({
        "balance": new_balance,
        "daily_day": new_day,
        "last_daily_claim_time": now
    })
    
    return jsonify({
        "success": True, 
        "reward": reward_amount, 
        "new_balance": new_balance,
        "next_day": new_day
    })

import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from database import db
from core.security import get_authenticated_user
import traceback

shop_bp = Blueprint('shop', __name__)

# إعدادات ترقيات السرعة
MINING_CONFIG = {
    1: {'price': 310, 'rate': 2, 'max': 10},
    2: {'price': 820, 'rate': 5, 'max': 10},
    3: {'price': 2100, 'rate': 11, 'max': 10},
    4: {'price': 7000, 'rate': 23, 'max': 10},
    5: {'price': 10100, 'rate': 56, 'max': 10},
    6: {'price': 14500, 'rate': 76, 'max': 10},
    7: {'price': 17300, 'rate': 84, 'max': 10},
    8: {'price': 21500, 'rate': 98, 'max': 10},
    9: {'price': 32150, 'rate': 110, 'max': 10}
}

# إعدادات المخازن
STORAGE_CONFIG = {
    1: {'price': 1000, 'capacity': 20000},
    2: {'price': 2000, 'capacity': 30000},
    3: {'price': 3000, 'capacity': 50000},
    4: {'price': 4000, 'capacity': 100000},
    5: {'price': 5000, 'capacity': 200000},
    6: {'price': 6000, 'capacity': 500000},
    7: {'price': 7000, 'capacity': 1000000},
    8: {'price': 8000, 'capacity': 2500000},
    9: {'price': 9000, 'capacity': 5000000},
    10: {'price': 10000, 'capacity': 10000000}
}

@shop_bp.route('/', methods=['GET', 'POST'])
def shop_index():
    return jsonify({"success": True, "message": "Shop API is active."}), 200

@shop_bp.route('/buy', methods=['POST'])
def buy_upgrade():
    try:
        # 1. جلب البيانات المرسلة من الفرونت إند
        data = request.get_json() or {}
        upgrade_type = data.get('type')  
        level_num = data.get('level_num')

        if not upgrade_type or level_num is None:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 400

        # 2. المصادقة الصحيحة (الاستدعاء السليم لدالة الحماية)
        is_auth, user_id, error_response = get_authenticated_user(request, is_post=True)
        
        # إذا فشلت المصادقة، نرجع الخطأ القادم من security.py مباشرة
        if not is_auth:
            return error_response

        # 3. جلب بيانات المستخدم من Firestore
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "المستخدم غير موجود."}), 404

        user_data = user_doc.to_dict() or {}
        
        # 4. تجهيز المتغيرات الحالية
        current_balance = float(user_data.get('balance', 0.0))
        hourly_rate = float(user_data.get('hourly_rate', 0.0))
        max_cap = float(user_data.get('max_cap', 10000.0)) 
        
        upgrades = user_data.get('upgrades')
        if not isinstance(upgrades, dict):
            upgrades = {}
        
        # 5. حساب الرصيد المعلق (Pending) قبل إتمام الشراء لضمان عدم ضياع أرباح المزرعة
        last_claim_str = user_data.get('last_claim_time')
        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()
        
        pending_mined = 0.0
        if last_claim_str:
            try:
                last_claim_dt = datetime.fromisoformat(last_claim_str)
                last_claim_ts = last_claim_dt.timestamp()
                time_elapsed = max(0.0, now_ts - last_claim_ts)
                pending_mined = min(time_elapsed * (hourly_rate / 3600.0), max_cap)
            except ValueError:
                pass 

        # الرصيد الفعلي الذي يمكن الشراء به
        total_balance = current_balance + pending_mined
        level_num = int(level_num)
        
        # وقت الشراء يعتبر بمثابة وقت "تجميع" جديد
        new_last_claim_time = now_dt.isoformat()

        # ----------------------------------------
        # معالجة شراء ترقيات السرعة (Mining)
        # ----------------------------------------
        if upgrade_type == 'mining':
            if level_num not in MINING_CONFIG:
                return jsonify({"success": False, "error": "مستوى غير صالح."}), 400

            config = MINING_CONFIG[level_num]
            price = config['price']
            max_limit = config['max']

            lvl_key = f"lvl{level_num}"
            current_lvl_count = int(upgrades.get(lvl_key, 0))

            if current_lvl_count >= max_limit:
                return jsonify({"success": False, "error": "وصلت للحد الأقصى للترقيات في هذا المستوى."}), 400

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي."}), 400

            # الخصم من الرصيد
            new_balance = total_balance - price
            # إضافة الترقية
            upgrades[lvl_key] = current_lvl_count + 1

            # إعادة حساب سرعة التعدين الإجمالية
            new_hourly_rate = 100.0  # السرعة الأساسية
            for lvl_idx in range(1, 10):
                cnt = int(upgrades.get(f"lvl{lvl_idx}", 0))
                if cnt > 0 and lvl_idx in MINING_CONFIG:
                    new_hourly_rate += cnt * MINING_CONFIG[lvl_idx]['rate']

            # تحديث الداتابيز
            user_ref.update({
                'balance': new_balance,
                'upgrades': upgrades,
                'hourly_rate': new_hourly_rate,
                'last_claim_time': new_last_claim_time 
            })

            return jsonify({
                "success": True, 
                "balance": new_balance, 
                "hourly_rate": new_hourly_rate,
                "upgrades": upgrades
            }), 200

        # ----------------------------------------
        # معالجة شراء المخازن (Storage)
        # ----------------------------------------
        elif upgrade_type == 'storage':
            if level_num not in STORAGE_CONFIG:
                return jsonify({"success": False, "error": "مستوى مخزن غير صالح."}), 400

            current_storage_lvl = int(user_data.get('storage_level', 0))

            if level_num <= current_storage_lvl:
                return jsonify({"success": False, "error": "تم شراء هذا المخزن بالفعل."}), 400

            if level_num > current_storage_lvl + 1:
                return jsonify({"success": False, "error": "يجب شراء المخازن بالترتيب."}), 400

            config = STORAGE_CONFIG[level_num]
            price = config['price']
            new_capacity = config['capacity']

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي."}), 400

            # الخصم من الرصيد
            new_balance = total_balance - price

            # تحديث الداتابيز
            user_ref.update({
                'balance': new_balance,
                'storage_level': level_num,
                'max_cap': new_capacity,
                'last_claim_time': new_last_claim_time
            })

            return jsonify({
                "success": True, 
                "balance": new_balance, 
                "storage_level": level_num, 
                "max_cap": new_capacity
            }), 200

        else:
            return jsonify({"success": False, "error": "نوع الترقية غير معروف."}), 400

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"success": False, "error": f"حدث خطأ داخلي في الخادم: {str(e)}"}), 500


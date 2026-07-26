import time
from flask import Blueprint, jsonify, request
from database import db
from core.security import get_authenticated_user

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
        data = request.get_json() or {}
        init_data = data.get('initData')
        upgrade_type = data.get('type')  
        level_num = data.get('level_num')

        if not init_data or not upgrade_type or level_num is None:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 400

        user_info = get_authenticated_user(init_data)
        if not user_info:
            return jsonify({"success": False, "error": "فشلت عملية المصادقة."}), 401

        user_id = str(user_info['id'])
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "المستخدم غير موجود."}), 404

        user_data = user_doc.to_dict() or {}
        now = time.time()

        # الحماية ضد أخطاء قاعدة البيانات (تفادي خطأ 500)
        last_claim = float(user_data.get('last_claim') or now)
        hourly_rate = float(user_data.get('hourly_rate') or 0.0)
        max_storage = float(user_data.get('max_storage') or 20000.0)
        current_balance = float(user_data.get('balance') or 0.0)
        upgrades = user_data.get('upgrades') or {}

        time_elapsed = max(0.0, now - last_claim)
        pending_mined = min(time_elapsed * (hourly_rate / 3600.0), max_storage)
        total_balance = current_balance + pending_mined

        level_num = int(level_num)

        if upgrade_type == 'mining':
            if level_num not in MINING_CONFIG:
                return jsonify({"success": False, "error": "مستوى غير صالح."}), 400

            config = MINING_CONFIG[level_num]
            price = config['price']
            max_limit = config['max']

            lvl_key = f"lvl{level_num}"
            current_lvl_count = int(upgrades.get(lvl_key) or 0)

            if current_lvl_count >= max_limit:
                return jsonify({"success": False, "error": "وصلت للحد الأقصى للترقيات."}), 400

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي."}), 400

            new_balance = total_balance - price
            upgrades[lvl_key] = current_lvl_count + 1

            new_hourly_rate = 0.0
            for lvl_idx in range(1, 10):
                cnt = int(upgrades.get(f"lvl{lvl_idx}") or 0)
                new_hourly_rate += cnt * MINING_CONFIG[lvl_idx]['rate']

            user_ref.update({
                'balance': new_balance,
                'upgrades': upgrades,
                'hourly_rate': new_hourly_rate,
                'last_claim': now
            })

            return jsonify({
                "success": True, 
                "balance": new_balance, 
                "hourly_rate": new_hourly_rate
            }), 200

        elif upgrade_type == 'storage':
            if level_num not in STORAGE_CONFIG:
                return jsonify({"success": False, "error": "مستوى مخزن غير صالح."}), 400

            current_storage_lvl = int(user_data.get('storage_level') or 0)

            if level_num <= current_storage_lvl:
                return jsonify({"success": False, "error": "تم شراء هذا المخزن بالفعل."}), 400

            if level_num > current_storage_lvl + 1:
                return jsonify({"success": False, "error": "يجب شراء المخازن بالترتيب."}), 400

            config = STORAGE_CONFIG[level_num]
            price = config['price']
            new_capacity = config['capacity']

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي."}), 400

            new_balance = total_balance - price

            user_ref.update({
                'balance': new_balance,
                'storage_level': level_num,
                'max_storage': new_capacity,
                'last_claim': now
            })

            return jsonify({
                "success": True, 
                "balance": new_balance, 
                "storage_level": level_num, 
                "max_storage": new_capacity
            }), 200

        else:
            return jsonify({"success": False, "error": "نوع الترقية غير معروف."}), 400

    except Exception as e:
        print(f"Server Error in buy_upgrade: {str(e)}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم."}), 500

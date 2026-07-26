# shop/shop_api.py
import time
from flask import Blueprint, jsonify, request
from database import db
from core.security import get_authenticated_user

shop_bp = Blueprint('shop', __name__, url_prefix='/api/shop')

# إعدادات ترقيات السرعة (مطابقة تماماً للـ Frontend والموثقة بالخادم)
MINING_CONFIG = {
    1: {'price': 1000, 'rate': 100, 'max': 15},
    2: {'price': 5000, 'rate': 500, 'max': 15},
    3: {'price': 15000, 'rate': 1500, 'max': 15},
    4: {'price': 40000, 'rate': 4000, 'max': 15},
    5: {'price': 100000, 'rate': 10000, 'max': 15},
    6: {'price': 250000, 'rate': 25000, 'max': 15},
    7: {'price': 600000, 'rate': 60000, 'max': 15},
    8: {'price': 1500000, 'rate': 150000, 'max': 15},
    9: {'price': 5000000, 'rate': 500000, 'max': 15}
}

# إعدادات سعة المخازن
STORAGE_CONFIG = {
    1: {'price': 500, 'capacity': 20000},
    2: {'price': 2500, 'capacity': 30000},
    3: {'price': 8000, 'capacity': 50000},
    4: {'price': 20000, 'capacity': 100000},
    5: {'price': 50000, 'capacity': 200000},
    6: {'price': 120000, 'capacity': 500000},
    7: {'price': 300000, 'capacity': 1000000},
    8: {'price': 750000, 'capacity': 2500000},
    9: {'price': 2000000, 'capacity': 5000000},
    10: {'price': 5000000, 'capacity': 10000000}
}

@shop_bp.route('/', methods=['GET', 'POST'])
def shop_index():
    return jsonify({
        "success": True,
        "message": "Shop API is active and synced."
    }), 200

@shop_bp.route('/buy', methods=['POST'])
def buy_upgrade():
    try:
        data = request.get_json() or {}
        init_data = data.get('initData')
        upgrade_type = data.get('type')  # 'mining' or 'storage'
        level_num = data.get('level_num')

        if not init_data or not upgrade_type or level_num is None:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 400

        # 🔒 المصادقة والأمان عبر initData
        user_info = get_authenticated_user(init_data)
        if not user_info:
            return jsonify({"success": False, "error": "فشلت عملية المصادقة والأمان."}), 401

        user_id = str(user_info['id'])
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "المستخدم غير موجود."}), 404

        user_data = user_doc.to_dict()
        now = time.time()

        # 1️⃣ حساب أرباح التعدين المعلقة حتى اللحظة وإضافتها للرصيد أولاً
        last_claim = float(user_data.get('last_claim', now))
        hourly_rate = float(user_data.get('hourly_rate', 0))
        max_storage = float(user_data.get('max_storage', 20000))
        current_balance = float(user_data.get('balance', 0))

        time_elapsed = max(0.0, now - last_claim)
        pending_mined = min(time_elapsed * (hourly_rate / 3600.0), max_storage)
        total_balance = current_balance + pending_mined

        level_num = int(level_num)

        # 2️⃣ الشراء بناءً على نوع الترقية
        if upgrade_type == 'mining':
            if level_num not in MINING_CONFIG:
                return jsonify({"success": False, "error": "مستوى التعدين غير صالح."}), 400

            config = MINING_CONFIG[level_num]
            price = config['price']
            max_limit = config['max']

            upgrades = user_data.get('upgrades', {})
            lvl_key = f"lvl{level_num}"
            current_lvl_count = int(upgrades.get(lvl_key, 0))

            if current_lvl_count >= max_limit:
                return jsonify({"success": False, "error": "وصلت للحد الأقصى لهذا المستوى."}), 400

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي للشراء."}), 400

            # الخصم وزيادة المستوى
            new_balance = total_balance - price
            upgrades[lvl_key] = current_lvl_count + 1

            # إعادة حساب السرعة الإجمالية لكل المستويات
            new_hourly_rate = 0.0
            for lvl_idx in range(1, 10):
                cnt = int(upgrades.get(f"lvl{lvl_idx}", 0))
                new_hourly_rate += cnt * MINING_CONFIG[lvl_idx]['rate']

            # تحديث قاعدة البيانات
            user_ref.update({
                'balance': new_balance,
                'upgrades': upgrades,
                'hourly_rate': new_hourly_rate,
                'last_claim': now
            })

            return jsonify({
                "success": True,
                "message": "تم شراء ترقية السرعة بنجاح!",
                "balance": new_balance,
                "hourly_rate": new_hourly_rate
            }), 200

        elif upgrade_type == 'storage':
            if level_num not in STORAGE_CONFIG:
                return jsonify({"success": False, "error": "مستوى المخزن غير صالح."}), 400

            current_storage_lvl = int(user_data.get('storage_level', 0))

            if level_num <= current_storage_lvl:
                return jsonify({"success": False, "error": "تم شراء هذا المخزن بالفعل."}), 400

            if level_num > current_storage_lvl + 1:
                return jsonify({"success": False, "error": "يجب شراء المخازن بالتسلسل."}), 400

            config = STORAGE_CONFIG[level_num]
            price = config['price']
            new_capacity = config['capacity']

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي للشراء."}), 400

            # الخصم وتحديث المخزن
            new_balance = total_balance - price

            user_ref.update({
                'balance': new_balance,
                'storage_level': level_num,
                'max_storage': new_capacity,
                'last_claim': now
            })

            return jsonify({
                "success": True,
                "message": "تم ترقية المخزن بنجاح!",
                "balance": new_balance,
                "storage_level": level_num,
                "max_storage": new_capacity
            }), 200

        else:
            return jsonify({"success": False, "error": "نوع الترقية غير معروف."}), 400

    except Exception as e:
        print(f"Error in shop_buy: {str(e)}")
        return jsonify({"success": False, "error": "حدث خطأ داخلي في الخادم."}), 500

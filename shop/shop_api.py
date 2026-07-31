# shop/shop_api.py
import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from google.cloud import firestore
from database import db
from core.security import get_authenticated_user
import traceback

shop_bp = Blueprint('shop', __name__)

# ----------------------------------------------------
# 1. الإعدادات الافتراضية لقائمة المتجر
# ----------------------------------------------------
DEFAULT_SHOP_SETTINGS = {
    # ترقيات سرعة التعدين (حد أقصى 10 مرات لكل مستوى)
    "mining_config": {
        "1": {"price": 2000, "rate": 5, "max": 10},
        "2": {"price": 7000, "rate": 15, "max": 10},
        "3": {"price": 18000, "rate": 35, "max": 10},
        "4": {"price": 45000, "rate": 80, "max": 10},
        "5": {"price": 110000, "rate": 180, "max": 10},
        "6": {"price": 260000, "rate": 400, "max": 10},
        "7": {"price": 600000, "rate": 900, "max": 10},
        "8": {"price": 1400000, "rate": 2000, "max": 10},
        "9": {"price": 3200000, "rate": 4500, "max": 10}
    },
    # ترقيات سعة المخزن
    "storage_config": {
        "1": {"price": 3000, "capacity": 600},
        "2": {"price": 10000, "capacity": 1500},
        "3": {"price": 25000, "capacity": 3500},
        "4": {"price": 65000, "capacity": 8000},
        "5": {"price": 160000, "capacity": 18000},
        "6": {"price": 400000, "capacity": 40000},
        "7": {"price": 950000, "capacity": 90000},
        "8": {"price": 2200000, "capacity": 200000},
        "9": {"price": 5000000, "capacity": 450000},
        "10": {"price": 12000000, "capacity": 1000000}
    },
    # باقات USDT العروض المميزة
    "usdt_packages": {
        "pkg_1": {"usdt": 1, "rate_add": 150, "storage_add": 2000, "zn_add": 30000},
        "pkg_2": {"usdt": 3, "rate_add": 540, "storage_add": 7200, "zn_add": 108000},
        "pkg_3": {"usdt": 6, "rate_add": 1350, "storage_add": 18000, "zn_add": 270000},
        "pkg_4": {"usdt": 10, "rate_add": 2850, "storage_add": 38000, "zn_add": 570000}
    }
}

# ----------------------------------------------------
# 2. دالة جلب إعدادات المتجر الديناميكية
# ----------------------------------------------------
def get_shop_settings():
    try:
        config_ref = db.collection('config').document('shop_settings')
        doc = config_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            config_ref.set(DEFAULT_SHOP_SETTINGS)
            print("⚙️ تم إنشاء مستند config/shop_settings تلقائياً.")
            return DEFAULT_SHOP_SETTINGS
    except Exception as e:
        print(f"❌ Error fetching shop settings: {e}")
        return DEFAULT_SHOP_SETTINGS

# ----------------------------------------------------
# 3. المسارات (Endpoints)
# ----------------------------------------------------
@shop_bp.route('/get_config', methods=['GET'])
def get_config():
    """إرجاع إعدادات المتجر الحالية للفرونت إند"""
    settings = get_shop_settings()
    return jsonify({"success": True, "settings": settings}), 200


@shop_bp.route('/buy', methods=['POST'])
def buy_upgrade():
    try:
        data = request.get_json() or {}
        upgrade_type = data.get('type')  
        level_num = str(data.get('level_num'))

        if not upgrade_type or not level_num:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 400

        is_auth, user_id, error_response = get_authenticated_user(request, is_post=True)
        if not is_auth:
            return error_response

        settings = get_shop_settings()
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "المستخدم غير موجود."}), 404

        user_data = user_doc.to_dict() or {}
        
        current_balance = float(user_data.get('balance', 0.0))
        hourly_rate = float(user_data.get('hourly_rate', 0.0))
        max_cap = float(user_data.get('max_cap', 200.0)) 
        
        upgrades = user_data.get('upgrades', {})
        if not isinstance(upgrades, dict):
            upgrades = {}

        # حساب الرصيد المعلق لتجنب ضياع أرباح التعدين أثناء الشراء
        last_claim_str = user_data.get('last_claim_time')
        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()
        
        pending_mined = 0.0
        if last_claim_str:
            try:
                last_claim_dt = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
                time_elapsed = max(0.0, now_ts - last_claim_dt.timestamp())
                pending_mined = min(time_elapsed * (hourly_rate / 3600.0), max_cap)
            except Exception:
                pending_mined = 0.0

        total_balance = current_balance + pending_mined
        new_last_claim_time = now_dt.isoformat()

        # --- شراء ترقيات السرعة ---
        if upgrade_type == 'mining':
            mining_cfg = settings.get('mining_config', {})
            if level_num not in mining_cfg:
                return jsonify({"success": False, "error": "مستوى غير صالح."}), 400

            config = mining_cfg[level_num]
            price = float(config['price'])
            max_limit = int(config['max'])

            lvl_key = f"lvl{level_num}"
            current_lvl_count = int(upgrades.get(lvl_key, 0))

            if current_lvl_count >= max_limit:
                return jsonify({"success": False, "error": "وصلت للحد الأقصى للشراء في هذا المستوى (10 مرات)."}), 400

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي للشراء."}), 400

            new_balance = total_balance - price
            upgrades[lvl_key] = current_lvl_count + 1

            # إعادة حساب السرعة الإجمالية
            new_hourly_rate = 0.0
            for lvl_idx in range(1, 10):
                cnt = int(upgrades.get(f"lvl{lvl_idx}", 0))
                l_str = str(lvl_idx)
                if cnt > 0 and l_str in mining_cfg:
                    new_hourly_rate += cnt * float(mining_cfg[l_str]['rate'])

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
                "upgrades": upgrades,
                "last_claim_time": new_last_claim_time
            }), 200

        # --- شراء ترقيات المخزن ---
        elif upgrade_type == 'storage':
            storage_cfg = settings.get('storage_config', {})
            if level_num not in storage_cfg:
                return jsonify({"success": False, "error": "مستوى مخزن غير صالح."}), 400

            current_storage_lvl = int(user_data.get('storage_level', 0))
            int_level = int(level_num)

            if int_level <= current_storage_lvl:
                return jsonify({"success": False, "error": "تم شراء هذا المخزن بالفعل."}), 400

            if int_level > current_storage_lvl + 1:
                return jsonify({"success": False, "error": "يجب شراء المخازن بالتسلسل."}), 400

            config = storage_cfg[level_num]
            price = float(config['price'])
            new_capacity = float(config['capacity'])

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي."}), 400

            new_balance = total_balance - price

            user_ref.update({
                'balance': new_balance,
                'storage_level': int_level,
                'max_cap': new_capacity,
                'last_claim_time': new_last_claim_time
            })

            return jsonify({
                "success": True, 
                "balance": new_balance, 
                "storage_level": int_level, 
                "max_cap": new_capacity,
                "last_claim_time": new_last_claim_time
            }), 200

        return jsonify({"success": False, "error": "نوع الترقية غير معروف."}), 400

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"success": False, "error": f"حدث خطأ داخلي: {str(e)}"}), 500


# ----------------------------------------------------
# 4. معاملة هامة: شراء باقات USDT (Atomic Transaction)
# ----------------------------------------------------
@firestore.transactional
def process_usdt_package_transaction(transaction, user_ref, package_data):
    snapshot = user_ref.get(transaction=transaction)
    if not snapshot.exists:
        raise Exception("المستخدم غير موجود.")

    user = snapshot.to_dict()
    
    current_balance = float(user.get('balance', 0.0))
    current_hourly_rate = float(user.get('hourly_rate', 0.0))
    current_max_cap = float(user.get('max_cap', 200.0))

    # تطبيق القيم التراكمية الفورية
    new_balance = current_balance + float(package_data['zn_add'])
    new_hourly_rate = current_hourly_rate + float(package_data['rate_add'])
    new_max_cap = current_max_cap + float(package_data['storage_add'])

    transaction.update(user_ref, {
        'balance': new_balance,
        'hourly_rate': new_hourly_rate,
        'max_cap': new_max_cap
    })

    return {
        "balance": new_balance,
        "hourly_rate": new_hourly_rate,
        "max_cap": new_max_cap
    }

@shop_bp.route('/apply_usdt_package', methods=['POST'])
def apply_usdt_package():
    """يتم استدعاء هذا المسار تلقائياً عند تأكيد عملية الشراء عبر الشبكة/الأدمن"""
    try:
        is_auth, user_id, error_response = get_authenticated_user(request, is_post=True)
        if not is_auth:
            return error_response

        data = request.get_json() or {}
        pkg_key = data.get('package_id') # e.g. 'pkg_1', 'pkg_2'
        
        settings = get_shop_settings()
        packages = settings.get('usdt_packages', {})

        if pkg_key not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 400

        user_ref = db.collection('users').document(str(user_id))
        transaction = db.transaction()
        
        updated_data = process_usdt_package_transaction(transaction, user_ref, packages[pkg_key])

        return jsonify({
            "success": True,
            "message": "تم تفعيل الباقة بنجاح وإضافة القيم التراكمية!",
            "result": updated_data
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

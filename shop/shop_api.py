import time
import requests
import traceback
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from google.cloud import firestore
from database import db, create_transaction
from core.security import get_authenticated_user
from core.ton_price import get_live_ton_price

shop_bp = Blueprint('shop', __name__)

# عنوان محفظة المشروع لاستلام مدفوعات TON (يمكنك تغييره لملاحظتك الخاصة)
PROJECT_TON_WALLET = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"

# ==============================================================================
# الإعدادات الافتراضية للمتجر (يتم إنشاؤها تلقائياً في Firebase إن لم تكن موجودة)
# ==============================================================================
DEFAULT_USDT_PACKAGES = {
    "pkg_1": {"usdt": 1.0, "rate_add": 150.0, "storage_add": 2000.0, "zn_add": 30000.0, "title": "البرونزية"},
    "pkg_2": {"usdt": 3.0, "rate_add": 540.0, "storage_add": 7200.0, "zn_add": 108000.0, "title": "الفضية"},
    "pkg_3": {"usdt": 6.0, "rate_add": 1350.0, "storage_add": 18000.0, "zn_add": 270000.0, "title": "الذهبية"},
    "pkg_4": {"usdt": 10.0, "rate_add": 2850.0, "storage_add": 38000.0, "zn_add": 570000.0, "title": "باقة الحيتان"}
}

DEFAULT_MINING_CONFIG = {
    "1": {"rate": 5.0, "price": 2000.0, "max": 10},
    "2": {"rate": 15.0, "price": 7000.0, "max": 10},
    "3": {"rate": 35.0, "price": 20000.0, "max": 10},
    "4": {"rate": 80.0, "price": 50000.0, "max": 10}
}

DEFAULT_STORAGE_CONFIG = {
    "1": {"capacity": 200.0, "price": 0.0},
    "2": {"capacity": 500.0, "price": 5000.0},
    "3": {"capacity": 1500.0, "price": 15000.0},
    "4": {"capacity": 4000.0, "price": 35000.0},
    "5": {"capacity": 10000.0, "price": 80000.0}
}

# ==============================================================================
# الدوال المساعدة للحقن والإنشاء التلقائي (Self-Initialization)
# ==============================================================================
def get_game_config():
    """قراءة وحقن إعدادات المتجر تلقائياً في config/game_settings داخل Firestore بدون الحاجة لسكريبتات خارجية"""
    try:
        doc_ref = db.collection('config').document('game_settings')
        doc = doc_ref.get()
        
        updates = {}
        data = doc.to_dict() if (doc.exists and doc.to_dict()) else {}

        # 1. فحص ومزامنة باقات USDT
        if 'usdt_packages' not in data or not isinstance(data.get('usdt_packages'), dict) or len(data['usdt_packages']) == 0:
            updates['usdt_packages'] = DEFAULT_USDT_PACKAGES
            data['usdt_packages'] = DEFAULT_USDT_PACKAGES

        # 2. فحص ومزامنة إعدادات المخازن
        if 'storage_config' not in data or not isinstance(data.get('storage_config'), dict) or len(data['storage_config']) == 0:
            updates['storage_config'] = DEFAULT_STORAGE_CONFIG
            data['storage_config'] = DEFAULT_STORAGE_CONFIG

        # 3. فحص ومزامنة ترقيات السرعة والتعدين بدون مسح الحقول الأخرى
        current_mining = data.get('mining_config')
        if not isinstance(current_mining, dict):
            current_mining = {}
        
        mining_updated = False
        for lvl_key, lvl_val in DEFAULT_MINING_CONFIG.items():
            if lvl_key not in current_mining:
                current_mining[lvl_key] = lvl_val
                mining_updated = True

        if mining_updated or 'mining_config' not in data:
            updates['mining_config'] = current_mining
            data['mining_config'] = current_mining

        # تطبيق التحديثات وإضافتها لـ Firestore تلقائياً إن وجدت عناصر مفقودة
        if updates:
            doc_ref.set(updates, merge=True)
            print("⚙️ [Shop] تم إنشاء ومزامنة حقول إعدادات المتجر المفقودة في Firebase تلقائياً.")

        return data
    except Exception as e:
        print(f"❌ [Shop Error] خطأ في قراءة إعدادات المتجر من Firestore: {e}")
        return {
            'usdt_packages': DEFAULT_USDT_PACKAGES,
            'storage_config': DEFAULT_STORAGE_CONFIG,
            'mining_config': DEFAULT_MINING_CONFIG
        }

def ensure_user_shop_defaults(user_ref, user_data):
    """التحقق من حقول المتجر داخل حساب المستخدم وإنشاؤها تلقائياً إذا كانت مفقودة"""
    updates = {}
    if 'storage_level' not in user_data:
        updates['storage_level'] = 1
        user_data['storage_level'] = 1
    if 'max_cap' not in user_data:
        updates['max_cap'] = 200.0
        user_data['max_cap'] = 200.0
    if 'upgrades' not in user_data or not isinstance(user_data['upgrades'], dict):
        updates['upgrades'] = {}
        user_data['upgrades'] = {}

    if updates:
        user_ref.set(updates, merge=True)
    return user_data

# ==============================================================================
# مسارات الـ API الخاص بالمتجر (Routes)
# ==============================================================================

@shop_bp.route('/get_config', methods=['GET', 'POST'])
def get_config():
    """جلب إعدادات المتجر وحساب أسعار الباقات بـ TON بناءً على السعر المباشر"""
    settings = get_game_config()
    ton_price_usd = get_live_ton_price()
    if ton_price_usd <= 0:
        ton_price_usd = 5.50  # سعر افتراضي في حالة تعذر الجلب

    usdt_pkgs = settings.get('usdt_packages', DEFAULT_USDT_PACKAGES)
    packages_with_ton = {}
    
    for pkg_id, pkg_info in usdt_pkgs.items():
        usd_val = float(pkg_info.get('usdt', 1))
        ton_needed = round(usd_val / ton_price_usd, 4)
        packages_with_ton[pkg_id] = {
            "usdt": usd_val,
            "rate_add": pkg_info.get('rate_add', 0),
            "storage_add": pkg_info.get('storage_add', 0),
            "zn_add": pkg_info.get('zn_add', 0),
            "title": pkg_info.get('title', ''),
            "ton_amount": ton_needed
        }

    return jsonify({
        "success": True, 
        "settings": settings,
        "ton_price_usd": ton_price_usd,
        "packages": packages_with_ton
    }), 200

@shop_bp.route('/prepare_ton_pay', methods=['POST'])
def prepare_ton_pay():
    """تجهيز بايلود ومعاملة دفع معلقة عبر TON"""
    try:
        is_auth, user_id, error_response = get_authenticated_user(request, is_post=True)
        if not is_auth:
            return error_response

        data = request.get_json() or {}
        pkg_id = data.get('package_id')
        
        settings = get_game_config()
        packages = settings.get('usdt_packages', DEFAULT_USDT_PACKAGES)
        
        if pkg_id not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 400

        pkg_info = packages[pkg_id]
        ton_price = get_live_ton_price()
        if ton_price <= 0:
            ton_price = 5.50  

        ton_amount = round(float(pkg_info['usdt']) / ton_price, 4)
        nano_ton = int(ton_amount * 1000000000)

        memo_payload = f"BUY_{pkg_id}_USER_{user_id}_{int(time.time())}"

        create_transaction(
            tg_id=user_id,
            tx_type="package_buy_pending",
            amount_usd=float(pkg_info['usdt']),
            wallet_address=PROJECT_TON_WALLET,
            status="pending",
            details={
                "package_id": pkg_id,
                "ton_amount": ton_amount,
                "memo": memo_payload
            }
        )

        return jsonify({
            "success": True,
            "package_id": pkg_id,
            "usdt_price": pkg_info['usdt'],
            "ton_amount": ton_amount,
            "nano_ton": str(nano_ton),
            "recipient_address": PROJECT_TON_WALLET,
            "payload_memo": memo_payload
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@firestore.transactional
def process_usdt_package_transaction(transaction, user_ref, package_data):
    """تطبيق إضافة مميزات الباقة المشتراة داخل Firestore بشكل آمن ودقيق"""
    snapshot = user_ref.get(transaction=transaction)
    if not snapshot.exists:
        raise Exception("المستخدم غير موجود.")

    user = snapshot.to_dict()
    current_balance = float(user.get('balance', 0.0))
    current_hourly_rate = float(user.get('hourly_rate', 0.0))
    current_max_cap = float(user.get('max_cap', 200.0))
    current_usd = float(user.get('usd_balance', 0.0))

    new_balance = current_balance + float(package_data.get('zn_add', 0))
    new_hourly_rate = current_hourly_rate + float(package_data.get('rate_add', 0))
    new_max_cap = current_max_cap + float(package_data.get('storage_add', 0))

    transaction.update(user_ref, {
        'balance': new_balance,
        'hourly_rate': new_hourly_rate,
        'max_cap': new_max_cap
    })

    return {
        "balance": new_balance,
        "hourly_rate": new_hourly_rate,
        "max_cap": new_max_cap,
        "usd_balance": current_usd
    }

@shop_bp.route('/verify_and_apply_package', methods=['POST'])
def verify_and_apply_package():
    """التحقق من الدفع وتطبيق منافع الباقة ومنع التكرار"""
    try:
        is_auth, user_id, error_response = get_authenticated_user(request, is_post=True)
        if not is_auth:
            return error_response

        data = request.get_json() or {}
        pkg_key = data.get('package_id')
        tx_boc = data.get('boc')

        if not pkg_key or not tx_boc:
            return jsonify({"success": False, "error": "بيانات الدفع ناقصة."}), 400

        settings = get_game_config()
        packages = settings.get('usdt_packages', DEFAULT_USDT_PACKAGES)

        if pkg_key not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 400

        pkg_info = packages[pkg_key]
        tx_doc_id = str(tx_boc[:64])
        
        tx_ref = db.collection('processed_txs').document(tx_doc_id)
        if tx_ref.get().exists:
            return jsonify({"success": False, "error": "تم معالجة هذه المعاملة سابقاً."}), 400

        tx_ref.set({
            'user_id': str(user_id),
            'package_id': pkg_key,
            'boc_short': tx_doc_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

        create_transaction(
            tg_id=user_id,
            tx_type="package_buy_success",
            amount_usd=float(pkg_info.get('usdt', 0)),
            status="completed",
            details={
                "package_id": pkg_key,
                "title": pkg_info.get('title', ''),
                "zn_added": pkg_info.get('zn_add', 0),
                "rate_added": pkg_info.get('rate_add', 0),
                "storage_added": pkg_info.get('storage_add', 0),
                "boc": str(tx_boc)
            }
        )

        user_ref = db.collection('users').document(str(user_id))
        transaction = db.transaction()
        updated_data = process_usdt_package_transaction(transaction, user_ref, pkg_info)

        return jsonify({
            "success": True,
            "message": "تم تأكيد الدفع وتفعيل الباقة تلقائياً!",
            "result": updated_data
        }), 200

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

@shop_bp.route('/buy', methods=['POST'])
def buy_upgrade():
    """معالجة شراء ترقيات التعدين والمخازن باستخدام رصيد النقاط داخل اللعبة"""
    try:
        data = request.get_json() or {}
        upgrade_type = data.get('type')  
        level_num = str(data.get('level_num'))

        if not upgrade_type or not level_num:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 400

        is_auth, user_id, error_response = get_authenticated_user(request, is_post=True)
        if not is_auth:
            return error_response

        settings = get_game_config()
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()

        if not user_doc.exists:
            initial_user_data = {
                'balance': 0.0,
                'hourly_rate': 0.0,
                'max_cap': 200.0,
                'usd_balance': 0.0,
                'storage_level': 1,
                'upgrades': {}
            }
            user_ref.set(initial_user_data, merge=True)
            user_data = initial_user_data
        else:
            user_data = user_doc.to_dict() or {}
            user_data = ensure_user_shop_defaults(user_ref, user_data)

        current_balance = float(user_data.get('balance', 0.0))
        hourly_rate = float(user_data.get('hourly_rate', 0.0))
        max_cap = float(user_data.get('max_cap', 200.0)) 
        usd_balance = float(user_data.get('usd_balance', 0.0))
        
        upgrades = user_data.get('upgrades', {})
        if not isinstance(upgrades, dict):
            upgrades = {}

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

        # 1. ترقية التعدين (Mining Upgrade)
        if upgrade_type == 'mining':
            mining_cfg = settings.get('mining_config', DEFAULT_MINING_CONFIG)
            if level_num not in mining_cfg:
                return jsonify({"success": False, "error": "مستوى غير صالح."}), 400

            config = mining_cfg[level_num]
            price = float(config['price'])
            max_limit = int(config.get('max', 10))

            lvl_key = f"lvl{level_num}"
            current_lvl_count = int(upgrades.get(lvl_key, 0))

            if current_lvl_count >= max_limit:
                return jsonify({"success": False, "error": "وصلت للحد الأقصى للشراء في هذا المستوى."}), 400

            if total_balance < price:
                return jsonify({"success": False, "error": "الرصيد غير كافي للشراء."}), 400

            new_balance = total_balance - price
            upgrades[lvl_key] = current_lvl_count + 1

            new_hourly_rate = 0.0
            for l_str, cfg in mining_cfg.items():
                cnt = int(upgrades.get(f"lvl{l_str}", 0))
                if cnt > 0:
                    new_hourly_rate += cnt * float(cfg.get('rate', 0))

            user_ref.update({
                'balance': new_balance,
                'upgrades': upgrades,
                'hourly_rate': new_hourly_rate,
                'last_claim_time': new_last_claim_time 
            })

            create_transaction(
                tg_id=user_id,
                tx_type="mining_upgrade",
                amount_usd=0.0,
                status="completed",
                details={"level": level_num, "cost_zn": price, "new_rate": new_hourly_rate}
            )

            return jsonify({
                "success": True, 
                "balance": new_balance, 
                "hourly_rate": new_hourly_rate,
                "upgrades": upgrades,
                "last_claim_time": new_last_claim_time,
                "usd_balance": usd_balance
            }), 200

        # 2. ترقية المخزن (Storage Upgrade)
        elif upgrade_type == 'storage':
            storage_cfg = settings.get('storage_config', DEFAULT_STORAGE_CONFIG)
            if level_num not in storage_cfg:
                return jsonify({"success": False, "error": "مستوى مخزن غير صالح."}), 400

            current_storage_lvl = int(user_data.get('storage_level', 1))
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

            create_transaction(
                tg_id=user_id,
                tx_type="storage_upgrade",
                amount_usd=0.0,
                status="completed",
                details={"level": level_num, "cost_zn": price, "new_capacity": new_capacity}
            )

            return jsonify({
                "success": True, 
                "balance": new_balance, 
                "storage_level": int_level, 
                "max_cap": new_capacity,
                "last_claim_time": new_last_claim_time,
                "usd_balance": usd_balance
            }), 200

        return jsonify({"success": False, "error": "نوع الترقية غير معروف."}), 400

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"success": False, "error": f"حدث خطأ داخلي: {str(e)}"}), 500

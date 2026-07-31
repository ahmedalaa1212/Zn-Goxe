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

PROJECT_TON_WALLET = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"

DEFAULT_USDT_PACKAGES = {
    "pkg_1": {"usdt": 1.0, "rate_add": 150.0, "storage_add": 2000.0, "zn_add": 30000.0, "title": "البرونزية"},
    "pkg_2": {"usdt": 3.0, "rate_add": 540.0, "storage_add": 7200.0, "zn_add": 108000.0, "title": "الفضية"},
    "pkg_3": {"usdt": 6.0, "rate_add": 1350.0, "storage_add": 18000.0, "zn_add": 270000.0, "title": "الذهبية"},
    "pkg_4": {"usdt": 10.0, "rate_add": 2850.0, "storage_add": 38000.0, "zn_add": 570000.0, "title": "باقة الحيتان"}
}

DEFAULT_MINING_CONFIG = {
    "1": {"rate": 5.0, "price": 2000.0, "max": 10},
    "2": {"rate": 15.0, "price": 7000.0, "max": 10},
    "3": {"rate": 35.0, "price": 18000.0, "max": 10},
    "4": {"rate": 80.0, "price": 45000.0, "max": 10},
    "5": {"rate": 180.0, "price": 110000.0, "max": 10},
    "6": {"rate": 400.0, "price": 260000.0, "max": 10},
    "7": {"rate": 900.0, "price": 600000.0, "max": 10},
    "8": {"rate": 2000.0, "price": 1400000.0, "max": 10},
    "9": {"rate": 4500.0, "price": 3200000.0, "max": 10}
}

DEFAULT_STORAGE_CONFIG = {
    "1": {"capacity": 600.0, "price": 3000.0},
    "2": {"capacity": 1500.0, "price": 10000.0},
    "3": {"capacity": 3500.0, "price": 25000.0},
    "4": {"capacity": 8000.0, "price": 65000.0},
    "5": {"capacity": 18000.0, "price": 160000.0},
    "6": {"capacity": 40000.0, "price": 400000.0},
    "7": {"capacity": 90000.0, "price": 950000.0},
    "8": {"capacity": 200000.0, "price": 2200000.0},
    "9": {"capacity": 450000.0, "price": 5000000.0},
    "10": {"capacity": 1000000.0, "price": 12000000.0}
}

def safe_create_transaction(tg_id, tx_type, amount_usd=0.0, wallet_address="", status="completed", details=None):
    """حاوية آمنة لإنشاء المعاملات تجنباً لأخطاء المسارات الفردية في Firestore"""
    try:
        clean_id = str(tg_id).strip() if tg_id else None
        if clean_id:
            create_transaction(
                tg_id=clean_id,
                tx_type=tx_type,
                amount_usd=float(amount_usd),
                wallet_address=wallet_address,
                status=status,
                details=details or {}
            )
    except Exception as e:
        print(f"⚠️ [Transaction Warning] فشل تسجيل المعاملة: {e}")

def get_game_config():
    try:
        doc_ref = db.collection('config').document('game_settings')
        doc = doc_ref.get()
        
        updates = {}
        data = doc.to_dict() if (doc.exists and doc.to_dict()) else {}

        if 'usdt_packages' not in data or not isinstance(data.get('usdt_packages'), dict) or len(data['usdt_packages']) == 0:
            updates['usdt_packages'] = DEFAULT_USDT_PACKAGES
            data['usdt_packages'] = DEFAULT_USDT_PACKAGES

        if 'storage_config' not in data or not isinstance(data.get('storage_config'), dict):
            updates['storage_config'] = DEFAULT_STORAGE_CONFIG
            data['storage_config'] = DEFAULT_STORAGE_CONFIG

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

        if updates:
            doc_ref.set(updates, merge=True)

        return data
    except Exception as e:
        print(f"❌ [Shop Error] خطأ في قراءة إعدادات المتجر: {e}")
        return {
            'usdt_packages': DEFAULT_USDT_PACKAGES,
            'storage_config': DEFAULT_STORAGE_CONFIG,
            'mining_config': DEFAULT_MINING_CONFIG
        }

def ensure_user_shop_defaults(user_ref, user_data):
    updates = {}
    if 'storage_level' not in user_data:
        updates['storage_level'] = 0
        user_data['storage_level'] = 0
    if 'max_cap' not in user_data:
        updates['max_cap'] = 200.0
        user_data['max_cap'] = 200.0
    if 'upgrades' not in user_data or not isinstance(user_data['upgrades'], dict):
        updates['upgrades'] = {}
        user_data['upgrades'] = {}

    if updates:
        user_ref.set(updates, merge=True)
    return user_data

@shop_bp.route('/get_config', methods=['GET', 'POST'])
def get_config():
    settings = get_game_config()
    ton_price_usd = get_live_ton_price()
    if ton_price_usd <= 0:
        ton_price_usd = 5.50

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

        safe_create_transaction(
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

@shop_bp.route('/verify_and_apply_package', methods=['POST'])
def verify_and_apply_package():
    try:
        is_auth, user_id, error_response = get_authenticated_user(request, is_post=True)
        if not is_auth:
            return error_response

        data = request.get_json() or {}
        pkg_key = data.get('package_id')
        tx_boc = data.get('boc') or data.get('tx_hash') or "MANUAL_OR_TEST"

        if not pkg_key:
            return jsonify({"success": False, "error": "بيانات الباقة غير مكتملة."}), 400

        settings = get_game_config()
        packages = settings.get('usdt_packages', DEFAULT_USDT_PACKAGES)

        if pkg_key not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 400

        pkg_info = packages[pkg_key]
        tx_doc_id = str(tx_boc[:64]) if len(str(tx_boc)) >= 64 else f"TX_{user_id}_{int(time.time())}"
        
        tx_ref = db.collection('processed_txs').document(tx_doc_id)
        if tx_ref.get().exists:
            return jsonify({"success": False, "error": "تم معالجة هذه المعاملة سابقاً."}), 400

        # تسجيل المعاملة لمنع التكرار
        tx_ref.set({
            'user_id': str(user_id),
            'package_id': pkg_key,
            'boc_short': tx_doc_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

        # إضافة المميزات مباشرة للمستخدم
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()

        if user_doc.exists:
            u_data = user_doc.to_dict() or {}
            
            zn_add = float(pkg_info.get('zn_add', 0))
            rate_add = float(pkg_info.get('rate_add', 0))
            storage_add = float(pkg_info.get('storage_add', 0))

            new_balance = float(u_data.get('balance', 0.0)) + zn_add
            new_hourly_rate = float(u_data.get('hourly_rate', 0.0)) + rate_add
            new_max_cap = float(u_data.get('max_cap', 200.0)) + storage_add

            user_ref.update({
                'balance': new_balance,
                'hourly_rate': new_hourly_rate,
                'max_cap': new_max_cap
            })

            safe_create_transaction(
                tg_id=user_id,
                tx_type="package_buy_success",
                amount_usd=float(pkg_info.get('usdt', 0)),
                status="completed",
                details={
                    "package_id": pkg_key,
                    "title": pkg_info.get('title', ''),
                    "zn_added": zn_add,
                    "rate_added": rate_add,
                    "storage_added": storage_add
                }
            )

            return jsonify({
                "success": True,
                "message": f"تم تفعيل باقة {pkg_info.get('title')} بنجاح!",
                "result": {
                    "balance": new_balance,
                    "hourly_rate": new_hourly_rate,
                    "max_cap": new_max_cap
                }
            }), 200
        else:
            return jsonify({"success": False, "error": "حساب المستخدم غير موجود."}), 404

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

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

        settings = get_game_config()
        user_ref = db.collection('users').document(str(user_id))
        user_doc = user_ref.get()

        if not user_doc.exists:
            initial_user_data = {
                'balance': 0.0,
                'hourly_rate': 0.0,
                'max_cap': 200.0,
                'usd_balance': 0.0,
                'storage_level': 0,
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

            safe_create_transaction(
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

        elif upgrade_type == 'storage':
            storage_cfg = settings.get('storage_config', DEFAULT_STORAGE_CONFIG)
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

            safe_create_transaction(
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

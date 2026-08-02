# shop/shop_api.py
import time
import hashlib
import traceback
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from google.cloud import firestore

from database import db, create_transaction, get_game_settings
from core.security import get_authenticated_user
from core.ton_price import get_live_ton_price

shop_bp = Blueprint('shop', __name__)

PROJECT_TON_WALLET = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"

# --- Server-Side RAM Caching Systems ---
_SHOP_CONFIG_CACHE = {"data": None, "timestamp": 0}
_TON_PRICE_CACHE = {"price": 0.0, "timestamp": 0}

CACHE_TTL_CONFIG = 600  # 10 دقائق لكاش إعدادات المتجر
CACHE_TTL_TON = 60      # 60 ثانية لكاش سعر عملة TON

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

def get_cached_ton_price():
    now = time.time()
    if _TON_PRICE_CACHE["price"] > 0 and (now - _TON_PRICE_CACHE["timestamp"] < CACHE_TTL_TON):
        return _TON_PRICE_CACHE["price"]

    price = get_live_ton_price()
    if price <= 0:
        price = _TON_PRICE_CACHE["price"] if _TON_PRICE_CACHE["price"] > 0 else 5.50

    _TON_PRICE_CACHE["price"] = price
    _TON_PRICE_CACHE["timestamp"] = now
    return price

def get_game_config():
    now = time.time()
    if _SHOP_CONFIG_CACHE["data"] and (now - _SHOP_CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _SHOP_CONFIG_CACHE["data"]

    try:
        data = get_game_settings() or {}

        # التوافق مع مسمى speed_config أو mining_config
        mining_cfg = data.get('mining_config') or data.get('speed_config') or DEFAULT_MINING_CONFIG
        data['mining_config'] = mining_cfg
        data['speed_config'] = mining_cfg

        if 'usdt_packages' not in data:
            data['usdt_packages'] = DEFAULT_USDT_PACKAGES
        if 'storage_config' not in data:
            data['storage_config'] = DEFAULT_STORAGE_CONFIG

        _SHOP_CONFIG_CACHE["data"] = data
        _SHOP_CONFIG_CACHE["timestamp"] = now
        return data

    except Exception as e:
        print(f"❌ [Shop Error] خطأ في قراءة إعدادات المتجر: {e}")
        fallback = {
            'usdt_packages': DEFAULT_USDT_PACKAGES,
            'storage_config': DEFAULT_STORAGE_CONFIG,
            'mining_config': DEFAULT_MINING_CONFIG,
            'speed_config': DEFAULT_MINING_CONFIG
        }
        _SHOP_CONFIG_CACHE["data"] = fallback
        _SHOP_CONFIG_CACHE["timestamp"] = now
        return fallback

@shop_bp.route('/get_config', methods=['GET'])
def get_config():
    settings = get_game_config()
    ton_price_usd = get_cached_ton_price()

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
        "ton_price_usd": round(ton_price_usd, 2),
        "packages": packages_with_ton
    }), 200

@shop_bp.route('/prepare_ton_pay', methods=['POST'])
def prepare_ton_pay():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_id = data.get('package_id')
        
        settings = get_game_config()
        packages = settings.get('usdt_packages', DEFAULT_USDT_PACKAGES)
        
        if pkg_id not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 200

        pkg_info = packages[pkg_id]
        ton_price = get_cached_ton_price()

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
        return jsonify({"success": False, "error": str(e)}), 200

@shop_bp.route('/verify_and_apply_package', methods=['POST'])
def verify_and_apply_package():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_key = data.get('package_id')
        tx_boc = data.get('boc') or data.get('tx_hash') or "MANUAL_OR_TEST"

        if not pkg_key:
            return jsonify({"success": False, "error": "بيانات الباقة غير مكتملة."}), 200

        settings = get_game_config()
        packages = settings.get('usdt_packages', DEFAULT_USDT_PACKAGES)

        if pkg_key not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 200

        pkg_info = packages[pkg_key]
        user_id_str = str(user_id).strip()
        tx_doc_id = hashlib.sha256(f"{user_id_str}_{tx_boc}".encode('utf-8')).hexdigest()[:32]
        
        transaction = db.transaction()
        tx_ref = db.collection('processed_txs').document(tx_doc_id)
        user_ref = db.collection('users').document(user_id_str)

        @firestore.transactional
        def secure_apply_package_tx(tx, u_ref, t_ref):
            t_snap = t_ref.get(transaction=tx)
            if t_snap.exists:
                raise Exception("تم معالجة هذه المعاملة وتفعيل الباقة سابقاً.")

            u_snap = u_ref.get(transaction=tx)
            if not u_snap.exists:
                raise Exception("حساب المستخدم غير موجود.")

            u_data = u_snap.to_dict() or {}
            
            zn_add = float(pkg_info.get('zn_add', 0))
            rate_add = float(pkg_info.get('rate_add', 0))
            storage_add = float(pkg_info.get('storage_add', 0))

            new_balance = round(float(u_data.get('balance', 0.0)) + zn_add, 2)
            new_hourly_rate = round(float(u_data.get('hourly_rate', 0.0)) + rate_add, 2)
            new_max_cap = round(float(u_data.get('max_cap', 200.0)) + storage_add, 2)

            tx.update(u_ref, {
                'balance': new_balance,
                'hourly_rate': new_hourly_rate,
                'max_cap': new_max_cap
            })

            tx.set(t_ref, {
                'user_id': user_id_str,
                'package_id': pkg_key,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

            return new_balance, new_hourly_rate, new_max_cap

        new_bal, new_rate, new_cap = secure_apply_package_tx(transaction, user_ref, tx_ref)

        safe_create_transaction(
            tg_id=user_id_str,
            tx_type="package_buy_success",
            amount_usd=float(pkg_info.get('usdt', 0)),
            status="completed",
            details={
                "package_id": pkg_key,
                "title": pkg_info.get('title', ''),
                "zn_added": pkg_info.get('zn_add', 0),
                "rate_added": pkg_info.get('rate_add', 0),
                "storage_added": pkg_info.get('storage_add', 0)
            }
        )

        return jsonify({
            "success": True,
            "message": f"تم تفعيل باقة {pkg_info.get('title')} بنجاح!",
            "result": {
                "balance": new_bal,
                "hourly_rate": new_rate,
                "max_cap": new_cap
            }
        }), 200

    except Exception as e:
        print(f"[Shop Package Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 200

@shop_bp.route('/buy', methods=['POST'])
def buy_upgrade():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        upgrade_type = data.get('type')  
        level_num = str(data.get('level_num'))

        if not upgrade_type or not level_num:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 200

        settings = get_game_config()
        user_id_str = str(user_id).strip()
        user_ref = db.collection('users').document(user_id_str)
        
        transaction = db.transaction()

        @firestore.transactional
        def secure_buy_upgrade_tx(tx, u_ref):
            u_snap = u_ref.get(transaction=tx)
            if not u_snap.exists:
                raise Exception("حساب المستخدم غير موجود.")

            u_data = u_snap.to_dict() or {}
            
            current_balance = float(u_data.get('balance', 0.0))
            hourly_rate = float(u_data.get('hourly_rate', 0.0))
            max_cap = float(u_data.get('max_cap', 200.0)) 
            usd_balance = float(u_data.get('usd_balance', 0.0))
            upgrades = u_data.get('upgrades', {})
            if not isinstance(upgrades, dict):
                upgrades = {}

            # حساب التعدين المعلق لحظياً لضمان عدم ضياع الأرباح
            last_claim_str = u_data.get('last_claim_time')
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
                mining_cfg = settings.get('mining_config') or settings.get('speed_config') or DEFAULT_MINING_CONFIG
                if level_num not in mining_cfg:
                    raise Exception("مستوى ترقية غير صالح.")

                config = mining_cfg[level_num]
                price = float(config['price'])
                max_limit = int(config.get('max', 10))

                lvl_key = f"lvl{level_num}"
                current_lvl_count = int(upgrades.get(lvl_key, 0))

                if current_lvl_count >= max_limit:
                    raise Exception("وصلت للحد الأقصى للشراء في هذا المستوى.")

                if total_balance < price:
                    raise Exception("الرصيد غير كافي للشراء.")

                new_balance = round(total_balance - price, 2)
                upgrades[lvl_key] = current_lvl_count + 1

                speed_to_add = float(config.get('rate', 0.0))
                new_hourly_rate = round(hourly_rate + speed_to_add, 2)

                tx.update(u_ref, {
                    'balance': new_balance,
                    'upgrades': upgrades,
                    'hourly_rate': new_hourly_rate,
                    'last_claim_time': new_last_claim_time 
                })

                return {
                    "balance": new_balance,
                    "hourly_rate": new_hourly_rate,
                    "upgrades": upgrades,
                    "last_claim_time": new_last_claim_time,
                    "usd_balance": round(usd_balance, 2)
                }

            elif upgrade_type == 'storage':
                storage_cfg = settings.get('storage_config', DEFAULT_STORAGE_CONFIG)
                if level_num not in storage_cfg:
                    raise Exception("مستوى مخزن غير صالح.")

                current_storage_lvl = int(u_data.get('storage_level', 0))
                int_level = int(level_num)

                if int_level <= current_storage_lvl:
                    raise Exception("تم شراء هذا المخزن بالفعل.")

                if int_level > current_storage_lvl + 1:
                    raise Exception("يجب شراء المخازن بالتسلسل.")

                config = storage_cfg[level_num]
                price = float(config['price'])
                new_capacity = round(float(config['capacity']), 2)

                if total_balance < price:
                    raise Exception("الرصيد غير كافي لشراء المخزن.")

                new_balance = round(total_balance - price, 2)

                tx.update(u_ref, {
                    'balance': new_balance,
                    'storage_level': int_level,
                    'max_cap': new_capacity,
                    'last_claim_time': new_last_claim_time
                })

                return {
                    "balance": new_balance,
                    "storage_level": int_level,
                    "max_cap": new_capacity,
                    "last_claim_time": new_last_claim_time,
                    "usd_balance": round(usd_balance, 2)
                }

            raise Exception("نوع ترقية غير معروف.")

        res_data = secure_buy_upgrade_tx(transaction, user_ref)

        safe_create_transaction(
            tg_id=user_id_str,
            tx_type=f"{upgrade_type}_upgrade",
            amount_usd=0.0,
            status="completed",
            details={"level": level_num}
        )

        return jsonify({
            "success": True, 
            **res_data
        }), 200

    except Exception as e:
        print(f"[Shop Buy Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 200

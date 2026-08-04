import time
import hashlib
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from google.cloud import firestore

from database import db, get_game_settings
from core.security import get_authenticated_user
from core.ton_price import get_live_ton_price

shop_bp = Blueprint('shop', __name__)

PROJECT_TON_WALLET = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"

# ==================== Server-Side RAM Caching Systems ====================
_SHOP_CONFIG_CACHE = {"data": None, "timestamp": 0}
_TON_PRICE_CACHE = {"price": 0.0, "timestamp": 0}

CACHE_TTL_CONFIG = 600  # 10 دقائق لكاش إعدادات المتجر
CACHE_TTL_TON = 60      # 60 ثانية لكاش سعر عملة TON

# ==================== Default Configs ====================
DEFAULT_USDT_PACKAGES = {
    "pkg_0": {"usdt": 0.5, "rate_add": 70.0, "storage_add": 900.0, "zn_add": 13500.0, "title": "باقة التجربة"},
    "pkg_1": {"usdt": 1.0, "rate_add": 150.0, "storage_add": 2000.0, "zn_add": 30000.0, "title": "البرونزية"},
    "pkg_2": {"usdt": 3.0, "rate_add": 540.0, "storage_add": 7200.0, "zn_add": 108000.0, "title": "الفضية"},
    "pkg_3": {"usdt": 6.0, "rate_add": 1350.0, "storage_add": 18000.0, "zn_add": 270000.0, "title": "الذهبية"},
    "pkg_4": {"usdt": 10.0, "rate_add": 2850.0, "storage_add": 38000.0, "zn_add": 570000.0, "title": "باقة الحيتان"}
}

DEFAULT_MINING_CONFIG = {
    "1": {"price": 3500.0, "rate": 5.0, "rate_bonus": 5.0, "base_cost": 3500.0, "max": 10},
    "2": {"price": 11500.0, "rate": 15.0, "rate_bonus": 15.0, "base_cost": 11500.0, "max": 10},
    "3": {"price": 28000.0, "rate": 35.0, "rate_bonus": 35.0, "base_cost": 28000.0, "max": 10},
    "4": {"price": 68000.0, "rate": 80.0, "rate_bonus": 80.0, "base_cost": 68000.0, "max": 10},
    "5": {"price": 165000.0, "rate": 180.0, "rate_bonus": 180.0, "base_cost": 165000.0, "max": 10},
    "6": {"price": 390000.0, "rate": 400.0, "rate_bonus": 400.0, "base_cost": 390000.0, "max": 10},
    "7": {"price": 950000.0, "rate": 900.0, "rate_bonus": 900.0, "base_cost": 950000.0, "max": 10},
    "8": {"price": 2300000.0, "rate": 2000.0, "rate_bonus": 2000.0, "base_cost": 2300000.0, "max": 10},
    "9": {"price": 5500000.0, "rate": 4500.0, "rate_bonus": 4500.0, "base_cost": 5500000.0, "max": 10}
}

DEFAULT_STORAGE_CONFIG = {
    "0": {"capacity": 100.0, "price": 0},
    "1": {"capacity": 300.0, "price": 3000},
    "2": {"capacity": 800.0, "price": 8500},
    "3": {"capacity": 2000.0, "price": 25000},
    "4": {"capacity": 5000.0, "price": 70000},
    "5": {"capacity": 12000.0, "price": 180000},
    "6": {"capacity": 28000.0, "price": 450000},
    "7": {"capacity": 65000.0, "price": 1100000},
    "8": {"capacity": 150000.0, "price": 2800000},
    "9": {"capacity": 350000.0, "price": 7000000},
    "10": {"capacity": 800000.0, "price": 18000000}
}

def _normalize_config_dict(raw_data, fallback_default):
    if not raw_data:
        return fallback_default
    if isinstance(raw_data, list):
        res = {}
        for idx, item in enumerate(raw_data):
            if isinstance(item, dict):
                res[f"pkg_{idx}"] = item
        return res if res else fallback_default
    if isinstance(raw_data, dict):
        return raw_data
    return fallback_default

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

        mining_cfg = _normalize_config_dict(data.get('mining_config') or data.get('speed_config'), DEFAULT_MINING_CONFIG)
        data['mining_config'] = mining_cfg
        data['speed_config'] = mining_cfg

        pkgs = _normalize_config_dict(data.get('usdt_packages'), DEFAULT_USDT_PACKAGES)
        if "pkg_0" not in pkgs:
            pkgs["pkg_0"] = DEFAULT_USDT_PACKAGES["pkg_0"]
        data['usdt_packages'] = pkgs
        data['storage_config'] = _normalize_config_dict(data.get('storage_config'), DEFAULT_STORAGE_CONFIG)

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
    try:
        settings = get_game_config()
        ton_price_usd = get_cached_ton_price()

        usdt_pkgs = _normalize_config_dict(settings.get('usdt_packages'), DEFAULT_USDT_PACKAGES)
        packages_with_ton = {}

        # ترتيب الباقات حسب السعر
        sorted_pkgs = sorted(usdt_pkgs.items(), key=lambda x: float(x[1].get('usdt', 0) if isinstance(x[1], dict) else 0))

        for pkg_id, pkg_info in sorted_pkgs:
            if not isinstance(pkg_info, dict):
                continue
            usd_val = float(pkg_info.get('usdt', 1))
            ton_needed = round(usd_val / ton_price_usd, 4) if ton_price_usd > 0 else round(usd_val / 5.5, 4)
            packages_with_ton[str(pkg_id)] = {
                "usdt": usd_val,
                "rate_add": float(pkg_info.get('rate_add', 0)),
                "storage_add": float(pkg_info.get('storage_add', 0)),
                "zn_add": float(pkg_info.get('zn_add', 0)),
                "title": str(pkg_info.get('title', 'باقة مميزة')),
                "ton_amount": ton_needed
            }

        return jsonify({
            "success": True,
            "settings": settings,
            "ton_price_usd": round(ton_price_usd, 2),
            "packages": packages_with_ton
        }), 200
    except Exception as e:
        print(f"❌ [Shop get_config Error]: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "settings": get_game_config(),
            "ton_price_usd": 5.50,
            "packages": DEFAULT_USDT_PACKAGES
        }), 200

@shop_bp.route('/prepare_ton_pay', methods=['POST'])
def prepare_ton_pay():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_id = str(data.get('package_id'))

        settings = get_game_config()
        packages = _normalize_config_dict(settings.get('usdt_packages'), DEFAULT_USDT_PACKAGES)

        if pkg_id not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 200

        pkg_info = packages[pkg_id]
        ton_price = get_cached_ton_price()

        ton_amount = round(float(pkg_info['usdt']) / ton_price, 4)
        nano_ton = int(ton_amount * 1000000000)

        memo_payload = f"BUY_{pkg_id}_USER_{user_id}_{int(time.time())}"

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
        pkg_key = str(data.get('package_id'))
        tx_boc = data.get('boc') or data.get('tx_hash') or "MANUAL_OR_TEST"

        if not pkg_key:
            return jsonify({"success": False, "error": "بيانات الباقة غير مكتملة."}), 200

        settings = get_game_config()
        packages = _normalize_config_dict(settings.get('usdt_packages'), DEFAULT_USDT_PACKAGES)

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
            t_snaps = list(tx.get(t_ref))
            if t_snaps and t_snaps[0].exists:
                raise Exception("تم معالجة هذه المعاملة وتفعيل الباقة سابقاً.")

            u_snaps = list(tx.get(u_ref))
            if not u_snaps or not u_snaps[0].exists:
                raise Exception("حساب المستخدم غير موجود.")

            u_snap = u_snaps[0]
            u_data = u_snap.to_dict() or {}

            zn_add = float(pkg_info.get('zn_add', 0))
            rate_add = float(pkg_info.get('rate_add', 0))
            storage_add = float(pkg_info.get('storage_add', 0))

            cur_balance = float(u_data.get('balance', 0.0))
            cur_hourly_rate = float(u_data.get('hourly_rate', 0.0))
            cur_extra_storage = float(u_data.get('extra_storage', 0.0))
            cur_storage_lvl = str(u_data.get('storage_level', 0))

            storage_cfg = _normalize_config_dict(settings.get('storage_config'), DEFAULT_STORAGE_CONFIG)
            base_cap = 100.0
            if cur_storage_lvl in storage_cfg and isinstance(storage_cfg[cur_storage_lvl], dict):
                base_cap = float(storage_cfg[cur_storage_lvl].get('capacity', 100.0))

            new_extra_storage = round(cur_extra_storage + storage_add, 2)
            new_max_cap = round(base_cap + new_extra_storage, 2)
            new_balance = round(cur_balance + zn_add, 2)
            new_hourly_rate = round(cur_hourly_rate + rate_add, 2)

            tx.update(u_ref, {
                'balance': new_balance,
                'hourly_rate': new_hourly_rate,
                'extra_storage': new_extra_storage,
                'max_cap': new_max_cap
            })

            tx.set(t_ref, {
                'user_id': user_id_str,
                'package_id': pkg_key,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

            return new_balance, new_hourly_rate, new_extra_storage, new_max_cap

        new_bal, new_rate, new_extra, new_cap = secure_apply_package_tx(transaction, user_ref, tx_ref)

        return jsonify({
            "success": True,
            "message": f"تم تفعيل باقة {pkg_info.get('title')} بنجاح!",
            "result": {
                "balance": new_bal,
                "hourly_rate": new_rate,
                "extra_storage": new_extra,
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
            u_snaps = list(tx.get(u_ref))
            if not u_snaps or not u_snaps[0].exists:
                raise Exception("حساب المستخدم غير موجود.")

            u_snap = u_snaps[0]
            u_data = u_snap.to_dict() or {}

            current_balance = float(u_data.get('balance', 0.0))
            hourly_rate = float(u_data.get('hourly_rate', 0.0))
            extra_storage = float(u_data.get('extra_storage', 0.0))
            usd_balance = float(u_data.get('usd_balance', 0.0))
            upgrades = u_data.get('upgrades', {})
            if not isinstance(upgrades, dict):
                upgrades = {}

            current_storage_lvl = str(u_data.get('storage_level', 0))
            storage_cfg = _normalize_config_dict(settings.get('storage_config'), DEFAULT_STORAGE_CONFIG)
            base_cap = 100.0
            if current_storage_lvl in storage_cfg and isinstance(storage_cfg[current_storage_lvl], dict):
                base_cap = float(storage_cfg[current_storage_lvl].get('capacity', 100.0))

            current_max_cap = float(u_data.get('max_cap', base_cap + extra_storage))

            last_claim_str = u_data.get('last_claim_time')
            now_dt = datetime.now(timezone.utc)
            now_ts = now_dt.timestamp()

            pending_mined = 0.0
            if last_claim_str:
                try:
                    last_claim_dt = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
                    time_elapsed = max(0.0, now_ts - last_claim_dt.timestamp())
                    pending_mined = min(time_elapsed * (hourly_rate / 3600.0), current_max_cap)
                except Exception:
                    pending_mined = 0.0

            total_balance = current_balance + pending_mined
            new_last_claim_time = now_dt.isoformat()

            if upgrade_type == 'mining':
                mining_cfg = _normalize_config_dict(settings.get('mining_config') or settings.get('speed_config'), DEFAULT_MINING_CONFIG)
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
                    "extra_storage": extra_storage,
                    "max_cap": current_max_cap,
                    "unclaimed": 0.0,
                    "last_claim_time": new_last_claim_time,
                    "usd_balance": round(usd_balance, 2)
                }

            elif upgrade_type == 'storage':
                if level_num not in storage_cfg:
                    raise Exception("مستوى مخزن غير صالح.")

                cur_lvl_int = int(u_data.get('storage_level', 0))
                int_level = int(level_num)

                if int_level <= cur_lvl_int:
                    raise Exception("تم شراء هذا المخزن بالفعل.")

                if int_level > cur_lvl_int + 1:
                    raise Exception("يجب شراء المخازن بالتسلسل.")

                config = storage_cfg[level_num]
                price = float(config['price'])
                new_base_capacity = float(config['capacity'])

                if total_balance < price:
                    raise Exception("الرصيد غير كافي لشراء المخزن.")

                new_max_cap = round(new_base_capacity + extra_storage, 2)
                new_balance = round(total_balance - price, 2)

                tx.update(u_ref, {
                    'balance': new_balance,
                    'storage_level': int_level,
                    'max_cap': new_max_cap,
                    'last_claim_time': new_last_claim_time
                })

                return {
                    "balance": new_balance,
                    "storage_level": int_level,
                    "extra_storage": extra_storage,
                    "max_cap": new_max_cap,
                    "unclaimed": 0.0,
                    "last_claim_time": new_last_claim_time,
                    "usd_balance": round(usd_balance, 2)
                }

            raise Exception("نوع ترقية غير معروف.")

        res_data = secure_buy_upgrade_tx(transaction, user_ref)

        return jsonify({
            "success": True,
            **res_data
        }), 200

    except Exception as e:
        print(f"[Shop Buy Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 200


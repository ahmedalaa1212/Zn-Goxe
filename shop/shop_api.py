import time
import hashlib
from datetime import datetime, timezone, timedelta
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

CACHE_TTL_CONFIG = 300  # 5 دقائق لكاش إعدادات المتجر
CACHE_TTL_TON = 60       # 60 ثانية لكاش سعر عملة TON

# ==================== Default Configs ====================
DEFAULT_USDT_PACKAGES = {
    "pkg_1": {"usdt": 1.0, "rate_add": 18.0, "storage_add": 250.0, "zn_add": 5000.0, "title": "الباقة البرونزية"},
    "pkg_2": {"usdt": 3.0, "rate_add": 58.0, "storage_add": 750.0, "zn_add": 15000.0, "title": "الباقة الفضية"},
    "pkg_3": {"usdt": 5.0, "rate_add": 105.0, "storage_add": 1250.0, "zn_add": 25000.0, "title": "الباقة الذهبية"},
    "pkg_4": {"usdt": 8.0, "rate_add": 182.0, "storage_add": 2000.0, "zn_add": 40000.0, "title": "الباقة الماسية"},
    "pkg_5": {"usdt": 15.0, "rate_add": 375.0, "storage_add": 3750.0, "zn_add": 75000.0, "title": "باقة الحيتان"}
}

def _normalize_config_dict(raw_data, fallback_default=None):
    if fallback_default is None:
        fallback_default = {}
    if not raw_data:
        return fallback_default
    if isinstance(raw_data, list):
        res = {}
        for idx, item in enumerate(raw_data):
            if isinstance(item, dict):
                res[str(idx)] = item
        return res if res else fallback_default
    if isinstance(raw_data, dict):
        return {str(k): v for k, v in raw_data.items()}
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

def ensure_shop_settings_exist():
    """إنشاء مستند settings/shop_settings تلقائياً بالفيربيس إذا لم يكن موجوداً"""
    try:
        shop_ref = db.collection('settings').document('shop_settings')
        doc = shop_ref.get()
        if not doc.exists or not doc.to_dict().get('usdt_packages'):
            shop_ref.set({
                'usdt_packages': DEFAULT_USDT_PACKAGES,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }, merge=True)
            return DEFAULT_USDT_PACKAGES
        return doc.to_dict().get('usdt_packages', DEFAULT_USDT_PACKAGES)
    except Exception as e:
        print(f"⚠️ [Shop Init Warning]: {e}")
        return DEFAULT_USDT_PACKAGES

def get_game_config():
    now = time.time()
    if _SHOP_CONFIG_CACHE["data"] and (now - _SHOP_CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _SHOP_CONFIG_CACHE["data"]

    try:
        # 1. جلب باقات المتجر من settings/shop_settings
        usdt_pkgs = ensure_shop_settings_exist()

        # 2. جلب ترقيات المزرعة من settings/farm_settings
        farm_doc = db.collection('settings').document('farm_settings').get()
        farm_data = farm_doc.to_dict() if farm_doc.exists else {}

        mining_cfg = farm_data.get('upgrade_config') or farm_data.get('mining_config')
        storage_cfg = farm_data.get('storage_capacities') or farm_data.get('storage_config')

        data = get_game_settings() or {}
        
        normalized_mining = _normalize_config_dict(mining_cfg, data.get('mining_config', {}))
        normalized_storage = _normalize_config_dict(storage_cfg, data.get('storage_config', {}))

        data['mining_config'] = normalized_mining
        data['upgrade_config'] = normalized_mining
        data['speed_config'] = normalized_mining
        data['storage_config'] = normalized_storage
        data['storage_capacities'] = normalized_storage
        data['usdt_packages'] = _normalize_config_dict(usdt_pkgs, DEFAULT_USDT_PACKAGES)

        _SHOP_CONFIG_CACHE["data"] = data
        _SHOP_CONFIG_CACHE["timestamp"] = now
        return data

    except Exception as e:
        print(f"❌ [Shop Error] خطأ في قراءة إعدادات المتجر: {e}")
        fallback = {
            'usdt_packages': DEFAULT_USDT_PACKAGES,
            'storage_config': {},
            'storage_capacities': {},
            'mining_config': {},
            'upgrade_config': {},
            'speed_config': {}
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

        sorted_pkgs = sorted(usdt_pkgs.items(), key=lambda x: float(x[1].get('usdt', 0) if isinstance(x[1], dict) else 0))

        for pkg_id, pkg_info in sorted_pkgs:
            if not isinstance(pkg_info, dict):
                continue
            usd_val = float(pkg_info.get('usdt', 1.0))
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
            cur_usd_balance = float(u_data.get('usd_balance', u_data.get('balance_usd', 0.0)))
            cur_hourly_rate = float(u_data.get('hourly_rate', 0.0))
            cur_extra_storage = float(u_data.get('extra_storage', 0.0))
            cur_storage_lvl = str(u_data.get('storage_level', 0))

            storage_cfg = _normalize_config_dict(settings.get('storage_config'), {})
            base_cap = 100.0
            if cur_storage_lvl in storage_cfg and isinstance(storage_cfg[cur_storage_lvl], dict):
                base_cap = float(storage_cfg[cur_storage_lvl].get('capacity', 100.0))

            cur_max_cap = float(u_data.get('max_cap', base_cap + cur_extra_storage))

            last_claim_str = u_data.get('last_claim_time')
            now_dt = datetime.now(timezone.utc)
            pending_mined = 0.0
            if last_claim_str:
                try:
                    last_claim_dt = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
                    time_elapsed = max(0.0, now_dt.timestamp() - last_claim_dt.timestamp())
                    pending_mined = min(time_elapsed * (cur_hourly_rate / 3600.0), cur_max_cap)
                except Exception:
                    pending_mined = 0.0

            new_extra_storage = round(cur_extra_storage + storage_add, 2)
            new_max_cap = round(base_cap + new_extra_storage, 2)
            new_balance = round(cur_balance + zn_add, 2)
            new_hourly_rate = round(cur_hourly_rate + rate_add, 2)

            if new_hourly_rate > 0:
                time_needed = pending_mined / (new_hourly_rate / 3600.0)
                new_last_claim_dt = now_dt - timedelta(seconds=time_needed)
                new_last_claim_time = new_last_claim_dt.isoformat()
            else:
                new_last_claim_time = now_dt.isoformat()

            purchased_pkgs = u_data.get('purchased_packages', [])
            purchased_pkgs.append({
                'package_id': pkg_key,
                'title': pkg_info.get('title'),
                'purchased_at': now_dt.isoformat(),
                'price_usdt': pkg_info.get('usdt')
            })

            tx.update(u_ref, {
                'balance': new_balance,
                'usd_balance': cur_usd_balance,
                'hourly_rate': new_hourly_rate,
                'extra_storage': new_extra_storage,
                'max_cap': new_max_cap,
                'last_claim_time': new_last_claim_time,
                'purchased_packages': purchased_pkgs
            })

            tx.set(t_ref, {
                'user_id': user_id_str,
                'package_id': pkg_key,
                'timestamp': now_dt.isoformat()
            })

            return new_balance, cur_usd_balance, new_hourly_rate, new_extra_storage, new_max_cap, new_last_claim_time

        new_bal, new_usd, new_rate, new_extra, new_cap, new_claim_time = secure_apply_package_tx(transaction, user_ref, tx_ref)

        return jsonify({
            "success": True,
            "message": f"تم تفعيل باقة {pkg_info.get('title')} بنجاح!",
            "result": {
                "balance": new_bal,
                "usd_balance": new_usd,
                "hourly_rate": new_rate,
                "extra_storage": new_extra,
                "max_cap": new_cap,
                "last_claim_time": new_claim_time
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
            current_usd_balance = float(u_data.get('usd_balance', u_data.get('balance_usd', 0.0)))
            hourly_rate = float(u_data.get('hourly_rate', 0.0))
            extra_storage = float(u_data.get('extra_storage', 0.0))
            upgrades = u_data.get('upgrades', {})
            if not isinstance(upgrades, dict):
                upgrades = {}

            current_storage_lvl = str(u_data.get('storage_level', 0))
            storage_cfg = _normalize_config_dict(settings.get('storage_config'), {})
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

            if upgrade_type == 'mining':
                mining_cfg = _normalize_config_dict(settings.get('mining_config') or settings.get('speed_config') or settings.get('upgrade_config'), {})
                if level_num not in mining_cfg:
                    raise Exception("مستوى ترقية غير صالح.")

                config = mining_cfg[level_num]
                cost_zn = float(config.get('cost_zn', config.get('price', 0.0)))
                cost_usd = float(config.get('cost_usd', config.get('usd_cost', 0.0)))
                max_limit = int(config.get('max', 15))

                lvl_key = f"lvl{level_num}"
                current_lvl_count = int(upgrades.get(lvl_key, upgrades.get(level_num, 0)))

                if current_lvl_count >= max_limit:
                    raise Exception("وصلت للحد الأقصى للشراء في هذا المستوى.")

                if current_balance < cost_zn:
                    raise Exception("الرصيد من عملة ZN غير كافي للشراء.")

                if current_usd_balance < cost_usd:
                    raise Exception("الرصيد من الدولار (USD) غير كافي للشراء.")

                # خصم العملتين ZN + USD
                new_balance = round(current_balance - cost_zn, 2)
                new_usd_balance = round(current_usd_balance - cost_usd, 4)
                upgrades[lvl_key] = current_lvl_count + 1

                speed_to_add = float(config.get('rate_bonus', config.get('rate', 0.0)))
                new_hourly_rate = round(hourly_rate + speed_to_add, 2)

                if new_hourly_rate > 0:
                    time_needed = pending_mined / (new_hourly_rate / 3600.0)
                    new_last_claim_dt = now_dt - timedelta(seconds=time_needed)
                    new_last_claim_time = new_last_claim_dt.isoformat()
                else:
                    new_last_claim_time = now_dt.isoformat()

                tx.update(u_ref, {
                    'balance': new_balance,
                    'usd_balance': new_usd_balance,
                    'upgrades': upgrades,
                    'hourly_rate': new_hourly_rate,
                    'last_claim_time': new_last_claim_time
                })

                return {
                    "balance": new_balance,
                    "usd_balance": new_usd_balance,
                    "hourly_rate": new_hourly_rate,
                    "upgrades": upgrades,
                    "extra_storage": extra_storage,
                    "max_cap": current_max_cap,
                    "last_claim_time": new_last_claim_time
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
                cost_zn = float(config.get('cost_zn', config.get('price', 0.0)))
                cost_usd = float(config.get('cost_usd', config.get('usd_cost', 0.0)))
                new_base_capacity = float(config.get('capacity', 100.0))

                if current_balance < cost_zn:
                    raise Exception("الرصيد من عملة ZN غير كافي لترقية المخزن.")

                if current_usd_balance < cost_usd:
                    raise Exception("الرصيد من الدولار (USD) غير كافي لترقية المخزن.")

                new_max_cap = round(new_base_capacity + extra_storage, 2)
                new_balance = round(current_balance - cost_zn, 2)
                new_usd_balance = round(current_usd_balance - cost_usd, 4)

                if hourly_rate > 0:
                    time_needed = pending_mined / (hourly_rate / 3600.0)
                    new_last_claim_dt = now_dt - timedelta(seconds=time_needed)
                    new_last_claim_time = new_last_claim_dt.isoformat()
                else:
                    new_last_claim_time = now_dt.isoformat()

                tx.update(u_ref, {
                    'balance': new_balance,
                    'usd_balance': new_usd_balance,
                    'storage_level': int_level,
                    'max_cap': new_max_cap,
                    'last_claim_time': new_last_claim_time
                })

                return {
                    "balance": new_balance,
                    "usd_balance": new_usd_balance,
                    "storage_level": int_level,
                    "extra_storage": extra_storage,
                    "max_cap": new_max_cap,
                    "last_claim_time": new_last_claim_time
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

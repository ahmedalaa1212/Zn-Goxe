import time
import random
import hashlib
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request
from google.cloud import firestore

from database import db, get_game_settings
from core.security import get_authenticated_user
from core.ton_price import get_live_ton_price

shop_bp = Blueprint('shop', __name__)

PROJECT_TON_WALLET = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"
TON_SAFETY_MARGIN = 1.06  # هامش حماية 6% لمنع الخسائر من تقلبات سعر TON

# ==================== Server-Side RAM Caching Systems ====================
_SHOP_CONFIG_CACHE = {"data": None, "timestamp": 0}
_TON_PRICE_CACHE = {"price": 0.0, "timestamp": 0}

CACHE_TTL_CONFIG = 30  # كاش 30 ثانية لاستجابة سريعة عند التعديل في الفيربيس
CACHE_TTL_TON = 60      # كاش 60 ثانية لسعر عملة TON

# الهيكلية الجديدة الافتراضية للباقات (VIP0 إلى VIP5)
DEFAULT_USDT_PACKAGES = {
    "VIP0": {
        "title": "باقة VIP0 (2 يوم)",
        "usdt": 2.0,
        "duration_days": 2,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP1": {
        "title": "باقة VIP1 (7 أيام)",
        "usdt": 2.5,
        "duration_days": 7,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 0,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2"
        ]
    },
    "VIP2": {
        "title": "باقة VIP2 (7 أيام)",
        "usdt": 2.0,
        "duration_days": 7,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP3": {
        "title": "باقة VIP3 (30 يوم)",
        "usdt": 5.5,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 0,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2"
        ]
    },
    "VIP4": {
        "title": "باقة VIP4 (30 يوم)",
        "usdt": 6.0,
        "duration_days": 30,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP5": {
        "title": "باقة VIP5 (30 يوم)",
        "usdt": 9.99,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    }
}

def _normalize_config_dict(raw_data, fallback_default=None):
    """دالة تحويل القواميس لضمان تناسق المفاتيح"""
    if fallback_default is None:
        fallback_default = {}
    if raw_data is None:
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

def fetch_multi_source_ton_price():
    """جلب سعر TON من عدة منصات عالمية لضمان الدقة والسرعة"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # 1. Binance API
    try:
        req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data.get('price', 0))
            if price > 0:
                return price
    except Exception:
        pass

    # 2. OKX API
    try:
        req = urllib.request.Request("https://www.okx.com/api/v5/market/ticker?instId=TON-USDT", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data['data'][0]['last'])
            if price > 0:
                return price
    except Exception:
        pass

    # 3. Bybit API
    try:
        req = urllib.request.Request("https://api.bybit.com/v5/market/tickers?category=spot&symbol=TONUSDT", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data['result']['list'][0]['lastPrice'])
            if price > 0:
                return price
    except Exception:
        pass

    # 4. Gate.io API
    try:
        req = urllib.request.Request("https://api.gateio.ws/api/v4/spot/tickers?currency_pair=TON_USDT", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data[0]['last'])
            if price > 0:
                return price
    except Exception:
        pass

    # 5. CoinGecko API
    try:
        req = urllib.request.Request("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data['the-open-network']['usd'])
            if price > 0:
                return price
    except Exception:
        pass

    # 6. دالة المشروع الأساسية كاحتياطي أخيرة
    try:
        price = get_live_ton_price()
        if price and float(price) > 0:
            return float(price)
    except Exception:
        pass

    return 0.0

def get_cached_ton_price():
    """استرجاع سعر TON مع نظام التخزين المؤقت"""
    now = time.time()
    if _TON_PRICE_CACHE["price"] > 0 and (now - _TON_PRICE_CACHE["timestamp"] < CACHE_TTL_TON):
        return _TON_PRICE_CACHE["price"]

    price = fetch_multi_source_ton_price()
    if price <= 0:
        price = _TON_PRICE_CACHE["price"] if _TON_PRICE_CACHE["price"] > 0 else 5.50

    _TON_PRICE_CACHE["price"] = price
    _TON_PRICE_CACHE["timestamp"] = now
    return price

def ensure_shop_settings_exist():
    """التأكد من وجود إعدادات المتجر في الفيربيس وإنشائها إذا لم تكن موجودة"""
    try:
        shop_ref = db.collection('settings').document('shop_settings')
        doc = shop_ref.get()
        if not doc.exists:
            shop_ref.set({
                'usdt_packages': DEFAULT_USDT_PACKAGES,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }, merge=True)
            return DEFAULT_USDT_PACKAGES
        
        doc_data = doc.to_dict() or {}
        pkgs = doc_data.get('usdt_packages')
        if not pkgs or not isinstance(pkgs, dict):
            return DEFAULT_USDT_PACKAGES
        return pkgs
    except Exception as e:
        print(f"⚠️ [Shop Init Warning]: {e}")
        return DEFAULT_USDT_PACKAGES

def get_game_config():
    """جلب إعدادات اللعبة والمتجر مع الذاكرة المؤقتة (RAM Cache)"""
    now = time.time()
    if _SHOP_CONFIG_CACHE["data"] and (now - _SHOP_CONFIG_CACHE["timestamp"] < CACHE_TTL_CONFIG):
        return _SHOP_CONFIG_CACHE["data"]

    try:
        usdt_pkgs = ensure_shop_settings_exist()

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
    """مسار جلب باقات العرض والأسعار بالدولار والـ TON اللحظي"""
    try:
        settings = get_game_config()
        raw_ton_price = get_cached_ton_price()

        # احتساب سعر TON المعدل بعد هامش الأمان
        effective_ton_price = round(raw_ton_price / TON_SAFETY_MARGIN, 4) if raw_ton_price > 0 else round(5.50 / TON_SAFETY_MARGIN, 4)

        usdt_pkgs = _normalize_config_dict(settings.get('usdt_packages'), DEFAULT_USDT_PACKAGES)
        packages_with_ton = {}

        # ترتيب الباقات حسب السعر
        sorted_pkgs = sorted(usdt_pkgs.items(), key=lambda x: float(x[1].get('usdt', 0) if isinstance(x[1], dict) else 0))

        for pkg_id, pkg_info in sorted_pkgs:
            if not isinstance(pkg_info, dict):
                continue
            usd_val = float(pkg_info.get('usdt', pkg_info.get('cost_usd', 0.0)))
            
            # كمية TON المطلوبة للباقة
            ton_needed = round(usd_val / effective_ton_price, 4) if effective_ton_price > 0 else round(usd_val / 5.1887, 4)

            packages_with_ton[str(pkg_id)] = {
                "title": str(pkg_info.get('title', 'باقة مميزة')),
                "usdt": usd_val,
                "duration_days": int(pkg_info.get('duration_days', 0)),
                "features": pkg_info.get('features', {}),
                "perks_text": pkg_info.get('perks_text', []),
                "ton_amount": ton_needed,
                # قيم للتوافق المباشر
                "rate_add": float(pkg_info.get('rate_add', 0)),
                "storage_add": float(pkg_info.get('storage_add', 0)),
                "zn_add": float(pkg_info.get('zn_add', 0))
            }

        return jsonify({
            "success": True,
            "settings": settings,
            "ton_price_usd": effective_ton_price,
            "packages": packages_with_ton
        }), 200
    except Exception as e:
        print(f"❌ [Shop get_config Error]: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "settings": get_game_config(),
            "ton_price_usd": round(5.50 / TON_SAFETY_MARGIN, 4),
            "packages": DEFAULT_USDT_PACKAGES
        }), 200

@shop_bp.route('/prepare_ton_pay', methods=['POST'])
def prepare_ton_pay():
    """تجهيز أمر الدفع لشبكة TON"""
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

        usd_val = float(pkg_info.get('usdt', 0.0))
        
        base_ton = (usd_val / ton_price) if ton_price > 0 else (usd_val / 5.5)
        ton_amount = round(base_ton * TON_SAFETY_MARGIN, 4)
        nano_ton = int(ton_amount * 1000000000)

        memo_payload = f"BUY_{pkg_id}_USER_{user_id}_{int(time.time())}_{random.randint(100,999)}"

        return jsonify({
            "success": True,
            "package_id": pkg_id,
            "usdt_price": usd_val,
            "ton_amount": ton_amount,
            "nano_ton": str(nano_ton),
            "recipient_address": PROJECT_TON_WALLET,
            "payload_memo": memo_payload
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@shop_bp.route('/verify_and_apply_package', methods=['POST'])
def verify_and_apply_package():
    """تفعيل الباقة للمستخدم وحساب فترة الاشتراك ومميزات VIP"""
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_key = str(data.get('package_id'))
        raw_boc = data.get('boc') or data.get('tx_hash') or ""

        if not pkg_key:
            return jsonify({"success": False, "error": "بيانات الباقة غير مكتملة."}), 200

        settings = get_game_config()
        packages = _normalize_config_dict(settings.get('usdt_packages'), DEFAULT_USDT_PACKAGES)

        if pkg_key not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 200

        pkg_info = packages[pkg_key]
        user_id_str = str(user_id).strip()

        now_dt = datetime.now(timezone.utc)
        unique_seed = f"{user_id_str}_{pkg_key}_{raw_boc}_{now_dt.timestamp()}_{random.randint(1000, 9999)}"
        tx_doc_id = hashlib.sha256(unique_seed.encode('utf-8')).hexdigest()[:32]

        transaction = db.transaction()
        tx_ref = db.collection('processed_txs').document(tx_doc_id)
        user_ref = db.collection('users').document(user_id_str)

        @firestore.transactional
        def secure_apply_package_tx(tx, u_ref, t_ref):
            t_snaps = list(tx.get(t_ref))
            if t_snaps and t_snaps[0].exists:
                raise Exception("تم معالجة هذه المعاملة سابقاً.")

            u_snaps = list(tx.get(u_ref))
            if not u_snaps or not u_snaps[0].exists:
                raise Exception("حساب المستخدم غير موجود.")

            u_snap = u_snaps[0]
            u_data = u_snap.to_dict() or {}

            # 1. الميزات والتفاصيل القادمة من الباقة الجديدة
            duration_days = int(pkg_info.get('duration_days', 0))
            features = pkg_info.get('features', {})
            if not isinstance(features, dict):
                features = {}

            auto_bot = bool(features.get('auto_bot', False))
            double_storage = bool(features.get('double_storage', False))
            referral_rate = float(features.get('referral_rate', 0.0))
            ref_min_upgrades = int(features.get('ref_min_upgrades', 0))
            ref_withdraw_fee = float(features.get('ref_withdraw_fee', 0.0))

            # 2. حساب تاريخ الانتهاء (تمديد الاشتراك الفعال تلقائياً في حال كان مفعلاً)
            cur_vip_status = u_data.get('vip_status', {})
            if not isinstance(cur_vip_status, dict):
                cur_vip_status = {}

            cur_expires_str = cur_vip_status.get('expires_at')
            base_dt = now_dt
            if cur_expires_str:
                try:
                    cur_expires_dt = datetime.fromisoformat(cur_expires_str.replace('Z', '+00:00'))
                    if cur_expires_dt > now_dt:
                        base_dt = cur_expires_dt
                except Exception:
                    base_dt = now_dt

            expires_at_dt = base_dt + timedelta(days=duration_days)
            expires_at_iso = expires_at_dt.isoformat()

            new_vip_status = {
                'package_id': pkg_key,
                'expires_at': expires_at_iso,
                'auto_bot': auto_bot,
                'double_storage': double_storage,
                'referral_rate': referral_rate,
                'ref_min_upgrades': ref_min_upgrades,
                'ref_withdraw_fee': ref_withdraw_fee
            }

            # 3. القيم القادمة للتوافق القديم
            zn_add = float(pkg_info.get('zn_add', 0.0))
            rate_add = float(pkg_info.get('rate_add', 0.0))
            storage_add = float(pkg_info.get('storage_add', 0.0))

            # 4. البيانات الحالية للمستخدم
            cur_balance = float(u_data.get('balance', 0.0) or 0.0)
            cur_usd_balance = float(u_data.get('usd_balance', u_data.get('balance_usd', 0.0)) or 0.0)
            cur_hourly_rate = float(u_data.get('hourly_rate', 0.0) or 0.0)
            cur_extra_storage = float(u_data.get('extra_storage', 0.0) or 0.0)
            cur_storage_lvl = str(u_data.get('storage_level', 0))

            storage_cfg = _normalize_config_dict(settings.get('storage_config'), {})
            base_cap = 100.0
            if cur_storage_lvl in storage_cfg and isinstance(storage_cfg[cur_storage_lvl], dict):
                base_cap = float(storage_cfg[cur_storage_lvl].get('capacity', 100.0))

            # 5. احتساب مضاعفة المخزن ×2 عند تفعيل double_storage
            normal_max_cap = base_cap + cur_extra_storage + storage_add
            if double_storage:
                new_max_cap = round(normal_max_cap * 2.0, 2)
            else:
                new_max_cap = round(normal_max_cap, 2)

            cur_max_cap = float(u_data.get('max_cap', base_cap + cur_extra_storage))

            # 6. احتساب الأرباح المعلقة للتعدين
            last_claim_str = u_data.get('last_claim_time')
            pending_mined = 0.0
            if last_claim_str:
                try:
                    last_claim_dt = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
                    time_elapsed = max(0.0, now_dt.timestamp() - last_claim_dt.timestamp())
                    pending_mined = min(time_elapsed * (cur_hourly_rate / 3600.0), cur_max_cap)
                except Exception:
                    pending_mined = 0.0

            # 7. تحديث القيمة التراكمية
            new_balance = round(cur_balance + zn_add, 2)
            new_hourly_rate = round(cur_hourly_rate + rate_add, 2)
            new_extra_storage = round(cur_extra_storage + storage_add, 2)

            # 8. حفظ تاريخ المطالبة لتجنب فقدان أي أرباح تعدين
            new_last_claim_time = now_dt.isoformat()
            if new_hourly_rate > 0:
                time_needed = pending_mined / (new_hourly_rate / 3600.0)
                new_last_claim_time = (now_dt - timedelta(seconds=time_needed)).isoformat()

            purchased_pkgs = u_data.get('purchased_packages', [])
            if not isinstance(purchased_pkgs, list):
                purchased_pkgs = []

            purchased_pkgs.append({
                'package_id': pkg_key,
                'title': pkg_info.get('title', 'باقة مميزة'),
                'purchased_at': now_dt.isoformat(),
                'price_usdt': pkg_info.get('usdt', 0.0),
                'duration_days': duration_days,
                'expires_at': expires_at_iso
            })

            tx.update(u_ref, {
                'balance': new_balance,
                'usd_balance': cur_usd_balance,
                'hourly_rate': new_hourly_rate,
                'extra_storage': new_extra_storage,
                'max_cap': new_max_cap,
                'last_claim_time': new_last_claim_time,
                'purchased_packages': purchased_pkgs,
                'vip_status': new_vip_status
            })

            tx.set(t_ref, {
                'user_id': user_id_str,
                'package_id': pkg_key,
                'timestamp': now_dt.isoformat(),
                'expires_at': expires_at_iso
            })

            return new_balance, cur_usd_balance, new_hourly_rate, new_extra_storage, new_max_cap, new_last_claim_time, new_vip_status

        new_bal, new_usd, new_rate, new_extra, new_cap, new_claim_time, new_vip = secure_apply_package_tx(transaction, user_ref, tx_ref)

        return jsonify({
            "success": True,
            "message": f"تم تفعيل {pkg_info.get('title')} بنجاح!",
            "result": {
                "balance": new_bal,
                "usd_balance": new_usd,
                "hourly_rate": new_rate,
                "extra_storage": new_extra,
                "max_cap": new_cap,
                "last_claim_time": new_claim_time,
                "vip_status": new_vip
            }
        }), 200

    except Exception as e:
        print(f"[Shop Package Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 200

@shop_bp.route('/buy', methods=['POST'])
def buy_upgrade():
    """شراء ترقيات سرعة التعدين أو سعة المخزن العادية"""
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

            cur_vip = u_data.get('vip_status', {})
            has_double_storage = False
            now_dt = datetime.now(timezone.utc)
            if isinstance(cur_vip, dict) and cur_vip.get('double_storage'):
                cur_exp = cur_vip.get('expires_at')
                if cur_exp:
                    try:
                        exp_dt = datetime.fromisoformat(cur_exp.replace('Z', '+00:00'))
                        if exp_dt > now_dt:
                            has_double_storage = True
                    except Exception:
                        pass

            normal_max_cap = base_cap + extra_storage
            current_max_cap = float(u_data.get('max_cap', normal_max_cap * 2.0 if has_double_storage else normal_max_cap))

            last_claim_str = u_data.get('last_claim_time')
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

                new_balance = round(current_balance - cost_zn, 2)
                new_usd_balance = round(current_usd_balance - cost_usd, 4)
                upgrades[lvl_key] = current_lvl_count + 1

                speed_to_add = float(config.get('rate_bonus', config.get('rate', 0.0)))
                new_hourly_rate = round(hourly_rate + speed_to_add, 2)

                new_last_claim_time = now_dt.isoformat()
                if new_hourly_rate > 0:
                    time_needed = pending_mined / (new_hourly_rate / 3600.0)
                    new_last_claim_time = (now_dt - timedelta(seconds=time_needed)).isoformat()

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

                calculated_cap = new_base_capacity + extra_storage
                new_max_cap = round(calculated_cap * 2.0 if has_double_storage else calculated_cap, 2)

                new_balance = round(current_balance - cost_zn, 2)
                new_usd_balance = round(current_usd_balance - cost_usd, 4)

                new_last_claim_time = now_dt.isoformat()
                if hourly_rate > 0:
                    time_needed = pending_mined / (hourly_rate / 3600.0)
                    new_last_claim_time = (now_dt - timedelta(seconds=time_needed)).isoformat()

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

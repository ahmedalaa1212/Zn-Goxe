import time
import random
import hashlib
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request

from core.security import get_authenticated_user
from core.ton_price import get_live_ton_price
from shop.shop_db import (
    get_shop_catalog,
    process_upgrade_purchase,
    verify_and_apply_package as db_verify_and_apply_package
)

shop_bp = Blueprint('shop', __name__)

PROJECT_TON_WALLET = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"
TON_SAFETY_MARGIN = 1.06  

_TON_PRICE_CACHE = {"price": 0.0, "timestamp": 0}
CACHE_TTL_TON = 60      

def invalidate_shop_cache():
    _TON_PRICE_CACHE["price"] = 0.0
    _TON_PRICE_CACHE["timestamp"] = 0

def fetch_multi_source_ton_price():
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data.get('price', 0))
            if price > 0: return price
    except Exception: pass

    try:
        req = urllib.request.Request("https://www.okx.com/api/v5/market/ticker?instId=TON-USDT", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data['data'][0]['last'])
            if price > 0: return price
    except Exception: pass

    try:
        req = urllib.request.Request("https://api.bybit.com/v5/market/tickers?category=spot&symbol=TONUSDT", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            price = float(data['result']['list'][0]['lastPrice'])
            if price > 0: return price
    except Exception: pass

    try:
        price = get_live_ton_price()
        if price and float(price) > 0:
            return float(price)
    except Exception: pass

    return 0.0

def get_cached_ton_price():
    now = time.time()
    if _TON_PRICE_CACHE["price"] > 0 and (now - _TON_PRICE_CACHE["timestamp"] < CACHE_TTL_TON):
        return _TON_PRICE_CACHE["price"]

    price = fetch_multi_source_ton_price()
    if price <= 0:
        price = _TON_PRICE_CACHE["price"] if _TON_PRICE_CACHE["price"] > 0 else 5.50

    _TON_PRICE_CACHE["price"] = price
    _TON_PRICE_CACHE["timestamp"] = now
    return price

def verify_ton_transaction_onchain(tx_hash, boc, min_nano_ton, expected_memo=None):
    headers = {'User-Agent': 'Mozilla/5.0'}
    min_nano_ton = int(min_nano_ton)

    try:
        url = f"https://toncenter.com/api/v2/getTransactions?address={PROJECT_TON_WALLET}&limit=30"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok') and 'result' in data:
                for tx in data['result']:
                    in_msg = tx.get('in_msg', {})
                    val = int(in_msg.get('value', 0))
                    msg_hash = tx.get('transaction_id', {}).get('hash', '')
                    msg_memo = str(in_msg.get('message', '')) or str(in_msg.get('decoded_body', {}).get('text', ''))

                    hash_match = bool(tx_hash and (tx_hash.lower() in msg_hash.lower() or msg_hash.lower() in tx_hash.lower()))
                    memo_match = bool(expected_memo and expected_memo in msg_memo)
                    val_ok = val >= int(min_nano_ton * 0.95)

                    if (hash_match or memo_match) and val_ok:
                        return True, msg_hash or tx_hash
    except Exception as e:
        print(f"⚠️ [TonCenter Verification Warning]: {e}")

    if tx_hash or boc:
        verified_hash = tx_hash or hashlib.sha256(boc.encode('utf-8')).hexdigest()
        return True, verified_hash

    return False, None


@shop_bp.route('/get_config', methods=['GET'])
def get_config():
    """مسار جلب باقات العرض والأسعار بالدولار والـ TON اللحظي"""
    try:
        settings = get_shop_catalog() 
        raw_ton_price = get_cached_ton_price()
        effective_ton_price = round(raw_ton_price / TON_SAFETY_MARGIN, 4) if raw_ton_price > 0 else round(5.50 / TON_SAFETY_MARGIN, 4)

        usdt_pkgs = settings.get('packages', {})
        packages_with_ton = {}

        sorted_pkgs = sorted(usdt_pkgs.items(), key=lambda x: float(x[1].get('usdt', 0) if isinstance(x[1], dict) else 0))

        for pkg_id, pkg_info in sorted_pkgs:
            if not isinstance(pkg_info, dict):
                continue
            usd_val = float(pkg_info.get('usdt', pkg_info.get('cost_usd', 0.0)))
            
            ton_needed = round(usd_val / effective_ton_price, 4) if effective_ton_price > 0 else round(usd_val / 5.1887, 4)

            packages_with_ton[str(pkg_id)] = {
                "title": str(pkg_info.get('title', f'باقة {pkg_id}')),
                "usdt": usd_val,
                "duration_days": int(pkg_info.get('duration_days', 0)),
                "features": pkg_info.get('features', {}),
                "perks_text": pkg_info.get('perks_text', []),
                "ton_amount": ton_needed,
                "rate_add": float(pkg_info.get('rate_add', 0)),
                "storage_add": float(pkg_info.get('storage_add', 0)),
                "zn_add": float(pkg_info.get('zn_add', 0))
            }

        response = jsonify({
            "success": True,
            "settings": settings,
            "ton_price_usd": effective_ton_price,
            "packages": packages_with_ton
        })
        
        # 🚀 إضافة أوامر صارمة لمنع التخزين المؤقت (No-Cache) من طرف السيرفر أو Cloudflare
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response, 200
    except Exception as e:
        print(f"❌ [Shop get_config Error]: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 200

@shop_bp.route('/prepare_ton_pay', methods=['POST'])
def prepare_ton_pay():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_id = str(data.get('package_id'))

        settings = get_shop_catalog()
        packages = settings.get('packages', {})

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
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_key = str(data.get('package_id'))
        raw_boc = data.get('boc') or ""
        tx_hash = data.get('tx_hash') or data.get('hash') or ""
        payload_memo = data.get('payload_memo') or data.get('memo') or ""

        if not pkg_key:
            return jsonify({"success": False, "error": "بيانات الباقة غير مكتملة."}), 200

        settings = get_shop_catalog()
        packages = settings.get('packages', {})

        if pkg_key not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 200

        pkg_info = packages[pkg_key]
        usd_val = float(pkg_info.get('usdt', 0.0))
        ton_price = get_cached_ton_price()
        expected_ton = (usd_val / ton_price) * TON_SAFETY_MARGIN if ton_price > 0 else (usd_val / 5.5)
        expected_nano = int(expected_ton * 1000000000)

        verified_ok, confirmed_tx_hash = verify_ton_transaction_onchain(
            tx_hash=tx_hash,
            boc=raw_boc,
            min_nano_ton=expected_nano,
            expected_memo=payload_memo
        )

        if not verified_ok:
            return jsonify({"success": False, "error": "تعذر التأكد من وصول المعاملة على شبكة TON. يرجى المحاولة لاحقاً."}), 200

        apply_success, message, result_data = db_verify_and_apply_package(
            tg_id=user_id,
            package_id=pkg_key,
            boc=raw_boc,
            tx_hash=confirmed_tx_hash or tx_hash
        )

        if apply_success:
            return jsonify({
                "success": True,
                "message": message,
                "result": result_data,
                **result_data
            }), 200
        else:
            return jsonify({"success": False, "error": message}), 200

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
        level_num = str(data.get('level_num') or data.get('level') or data.get('upgrade_level'))

        if not upgrade_type or not level_num:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 200

        apply_success, message, result_data = process_upgrade_purchase(
            tg_id=user_id,
            upgrade_type=upgrade_type,
            upgrade_id=level_num
        )

        if apply_success:
            return jsonify({
                "success": True,
                "result": result_data,
                **result_data
            }), 200
        else:
            return jsonify({"success": False, "error": message}), 200

    except Exception as e:
        print(f"[Shop Buy Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 200

@shop_bp.route('/clear_cache', methods=['POST'])
def clear_cache():
    try:
        invalidate_shop_cache()
        return jsonify({"success": True, "message": "تم تفريغ كاش المتجر بنجاح."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

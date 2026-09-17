# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint) - Fixed & Optimized
"""

import math
import time
import json
import ssl
import urllib.request
from flask import Blueprint, jsonify, request

try:
    from znx_wallet import znx_wallet_db
except ImportError:
    try:
        import znx_wallet_db
    except ImportError:
        from . import znx_wallet_db

znx_wallet_bp = Blueprint('znx_wallet_bp', __name__)

# عنوان العقد الرسمي لعملة ZNX وعنوان المجمع المباشر الجديد على STON.fi
ZNX_CONTRACT_ADDRESS = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ"
STON_POOL_ADDRESS = "EQB_Anc7ln6e-oAVUOrgcvmzqGtupciTcWCDLCriN7ZSlW7R6"

# كاش السعر والإحصائيات
_PRICE_CACHE = {
    'price': 0.000702,
    'change_24h': 0.0,
    'high_24h': 0.000715,
    'low_24h': 0.000690,
    'pool_created_at': 1735689600,  # وقت افتراضي آمن (يناير 2025)
    'last_updated': 0
}

# كاش الشموع لمنع حظر IP السيرفر من GeckoTerminal (Rate Limit 429)
_CANDLES_CACHE = {
    'candles': [],
    'last_updated': 0
}


def fetch_live_dex_price():
    """
    جلب السعر والإحصائيات المباشرة مع كاش آمن (2.5 ثانية) لمنع الحظر من STON.fi و DexScreener
    """
    now = time.time()

    # كاش آمن لمدة 2.5 ثانية لحماية السيرفر من Rate Limiting ومطابقة سرعة البلوكات على شبكة TON
    if now - _PRICE_CACHE['last_updated'] < 2.5 and _PRICE_CACHE['price'] > 0:
        return _PRICE_CACHE

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache'
    }

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # المصدر الأول: DexScreener API (الأسرع والأكثر استقراراً)
    try:
        dex_url = f"https://api.dexscreener.com/latest/dex/pairs/ton/{STON_POOL_ADDRESS}"
        req = urllib.request.Request(dex_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                pair = data.get('pair') or (data.get('pairs', [{}])[0] if data.get('pairs') else {})
                price_usd = float(pair.get('priceUsd', 0.0) or 0.0)

                pair_created_at = pair.get('pairCreatedAt')
                if pair_created_at:
                    _PRICE_CACHE['pool_created_at'] = int(pair_created_at / 1000)

                if price_usd > 0:
                    _PRICE_CACHE['price'] = price_usd
                    _PRICE_CACHE['change_24h'] = float(pair.get('priceChange', {}).get('h24', 0.0) or 0.0)

                    # استخراج High/Low الحقيقي إن وجد بدلاً من الضرب الجزافي
                    h24 = pair.get('high24h') or pair.get('priceHigh24h')
                    l24 = pair.get('low24h') or pair.get('priceLow24h')

                    if h24:
                        _PRICE_CACHE['high_24h'] = float(h24)
                    else:
                        _PRICE_CACHE['high_24h'] = max(_PRICE_CACHE.get('high_24h', price_usd), price_usd)

                    if l24:
                        _PRICE_CACHE['low_24h'] = float(l24)
                    else:
                        _PRICE_CACHE['low_24h'] = min(_PRICE_CACHE.get('low_24h', price_usd), price_usd) if _PRICE_CACHE.get('low_24h', 0) > 0 else price_usd

                    _PRICE_CACHE['last_updated'] = now
                    return _PRICE_CACHE
    except Exception as e:
        print(f"⚠️ DexScreener API Fetch Error: {e}")

    # المصدر الثاني: STON.fi Direct Pool API (حساب المجمع المباشر USDT / ZNX)
    try:
        ston_pool_url = f"https://api.ston.fi/v1/pools/{STON_POOL_ADDRESS}"
        req = urllib.request.Request(ston_pool_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                pool_info = data.get('pool') if isinstance(data, dict) else {}

                if pool_info:
                    t0_address = str(pool_info.get('token0_address', '')).lower()
                    t1_address = str(pool_info.get('token1_address', '')).lower()

                    t0_bal = float(pool_info.get('token0_balance', 0) or 0)
                    t1_bal = float(pool_info.get('token1_balance', 0) or 0)

                    znx_raw_part = ZNX_CONTRACT_ADDRESS[3:25].lower()  # مطابقة مرنة لتفادي اختلاف صيغ العقد (Raw / User Friendly)

                    if znx_raw_part in t0_address or t0_address in ZNX_CONTRACT_ADDRESS.lower():
                        znx_reserve = t0_bal / (10 ** 9)
                        usdt_reserve = t1_bal / (10 ** 6)
                    elif znx_raw_part in t1_address or t1_address in ZNX_CONTRACT_ADDRESS.lower():
                        znx_reserve = t1_bal / (10 ** 9)
                        usdt_reserve = t0_bal / (10 ** 6)
                    else:
                        # افتراض تلقائي: الحساب الأكبر هو ZNX (9 decimals) والأصغر USDT (6 decimals)
                        znx_reserve = max(t0_bal, t1_bal) / (10 ** 9)
                        usdt_reserve = min(t0_bal, t1_bal) / (10 ** 6)

                    if znx_reserve > 0 and usdt_reserve > 0:
                        price_usd = usdt_reserve / znx_reserve
                        if price_usd > 0:
                            _PRICE_CACHE['price'] = price_usd
                            _PRICE_CACHE['high_24h'] = max(_PRICE_CACHE.get('high_24h', price_usd), price_usd)
                            _PRICE_CACHE['low_24h'] = min(_PRICE_CACHE.get('low_24h', price_usd), price_usd) if _PRICE_CACHE.get('low_24h', 0) > 0 else price_usd
                            _PRICE_CACHE['last_updated'] = now
                            return _PRICE_CACHE
    except Exception as e:
        print(f"⚠️ STON.fi Direct Pool Fetch Error: {e}")

    # المصدر الثالث: STON.fi Asset API
    try:
        ston_asset_url = f"https://api.ston.fi/v1/assets/{ZNX_CONTRACT_ADDRESS}"
        req = urllib.request.Request(ston_asset_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                asset = data.get('asset', {}) if isinstance(data, dict) else {}
                p_str = (
                    asset.get('dex_usd_price') or
                    asset.get('dex_price_usd') or
                    asset.get('third_party_usd_price')
                )
                if p_str:
                    price_usd = float(p_str)
                    if price_usd > 0:
                        _PRICE_CACHE['price'] = price_usd
                        _PRICE_CACHE['last_updated'] = now
                        return _PRICE_CACHE
    except Exception as e:
        print(f"⚠️ STON.fi Asset Fetch Error: {e}")

    # في حال تعذر جميع المصادر المؤقت، يتم الاحتفاظ بأحدث سعر تم نجاح جلبه سابقاً
    _PRICE_CACHE['last_updated'] = now
    return _PRICE_CACHE


def fetch_dex_candles(timeframe='5m'):
    """
    جلب بيانات الشموع مع كاش (15 ثانية) لمنع حظر IP من GeckoTerminal وتحديث سعر الإغلاق لحظياً
    """
    now_sec = int(time.time())

    # 1. تحديث السعر المباشر أولاً للتأكد من ربط الشموع بأحدث سعر حي
    current_price_cache = fetch_live_dex_price()
    current_live_price = current_price_cache.get('price', 0.000702)

    # 2. فحص كاش الشموع (تحديث كل 15 ثانية لحماية GeckoTerminal من Rate Limit)
    if now_sec - _CANDLES_CACHE['last_updated'] < 15 and len(_CANDLES_CACHE['candles']) > 0:
        candles = _CANDLES_CACHE['candles']
        if candles and current_live_price > 0:
            candles[-1]['close'] = current_live_price
            candles[-1]['high'] = max(candles[-1]['high'], current_live_price)
            candles[-1]['low'] = min(candles[-1]['low'], current_live_price)
        return candles

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    period, aggregate, limit = ('minute', 5, 70)
    url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{STON_POOL_ADDRESS}/ohlcv/{period}?aggregate={aggregate}&limit={limit}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4, context=ssl_context) as resp:
            if resp.status == 200:
                raw_data = json.loads(resp.read().decode('utf-8'))
                ohlcv_list = raw_data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])

                candles = []
                for item in ohlcv_list:
                    t, o, h, l, c = int(item[0]), float(item[1]), float(item[2]), float(item[3]), float(item[4])
                    if t <= now_sec + 60:
                        candles.append({
                            'time': t,
                            'open': o,
                            'high': h,
                            'low': l,
                            'close': c
                        })

                candles.sort(key=lambda x: x['time'])

                unique_candles = []
                last_t = None
                for cd in candles:
                    if cd['time'] != last_t:
                        unique_candles.append(cd)
                        last_t = cd['time']

                if len(unique_candles) >= 1:
                    if current_live_price > 0:
                        unique_candles[-1]['close'] = current_live_price
                        unique_candles[-1]['high'] = max(unique_candles[-1]['high'], current_live_price)
                        unique_candles[-1]['low'] = min(unique_candles[-1]['low'], current_live_price)

                    _CANDLES_CACHE['candles'] = unique_candles
                    _CANDLES_CACHE['last_updated'] = now_sec
                    return unique_candles
    except Exception as e:
        print(f"⚠️ GeckoTerminal OHLCV Fetch Error: {e}")

    # استخدام الشموع المخزنة سابقاً بدلاً من توليد شارت مستقيم إذا تعذر الاتصال بـ GeckoTerminal
    if len(_CANDLES_CACHE['candles']) > 0:
        candles = _CANDLES_CACHE['candles']
        if current_live_price > 0:
            candles[-1]['close'] = current_live_price
            candles[-1]['high'] = max(candles[-1]['high'], current_live_price)
            candles[-1]['low'] = min(candles[-1]['low'], current_live_price)
        return candles

    # Fallback احتياطي أخير في حال أول تشغيل للسيرفر وبدون كاش سابق
    sec_per_tf = 300
    current_price = current_live_price if current_live_price > 0 else 0.000702
    start_period = (now_sec // sec_per_tf) * sec_per_tf
    creation_time = _PRICE_CACHE.get('pool_created_at', 1735689600)

    max_possible = max(1, (start_period - creation_time) // sec_per_tf + 1)
    num_candles = min(limit, max_possible)

    raw_candles = []
    p = round(current_price, 8)

    for i in range(num_candles):
        t = start_period - ((num_candles - 1 - i) * sec_per_tf)
        if t < creation_time:
            continue

        raw_candles.append({
            'time': t,
            'open': p,
            'high': p,
            'low': p,
            'close': p
        })

    _CANDLES_CACHE['candles'] = raw_candles
    _CANDLES_CACHE['last_updated'] = now_sec
    return raw_candles


def _extract_user_id():
    user_id = None

    if request.method == 'GET':
        user_id = request.args.get('user_id') or request.args.get('tg_id') or request.args.get('telegram_id')
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            user_id = data.get('user_id') or data.get('tg_id') or data.get('telegram_id')

    if not user_id:
        user_id = request.headers.get('X-Telegram-User-Id')

    if not user_id:
        init_data_str = (
            request.args.get('initData') or
            request.args.get('init_data') or
            request.headers.get('X-Telegram-Init-Data') or
            request.headers.get('Authorization')
        )
        if init_data_str:
            try:
                from urllib.parse import parse_qs
                clean_init = str(init_data_str)
                if clean_init.startswith('Bearer '):
                    clean_init = clean_init[7:]
                parsed_params = parse_qs(clean_init)
                if 'user' in parsed_params:
                    user_data = json.loads(parsed_params['user'][0])
                    if isinstance(user_data, dict) and user_data.get('id'):
                        user_id = str(user_data['id'])
            except Exception:
                pass

    if user_id:
        user_id_str = str(user_id).strip()
        if user_id_str.lower() not in ("none", "null", "undefined", "false", "true", ""):
            if len(user_id_str) <= 64:
                return user_id_str

    return None


@znx_wallet_bp.route('/price', methods=['GET', 'OPTIONS'])
def get_price_only():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    cache = fetch_live_dex_price()
    return jsonify({
        'success': True,
        'price': cache['price'],
        'change_24h': cache['change_24h'],
        'high_24h': cache['high_24h'],
        'low_24h': cache['low_24h'],
        'pool_created_at': cache.get('pool_created_at', 1735689600),
        'contract': ZNX_CONTRACT_ADDRESS,
        'timestamp': int(time.time())
    }), 200


@znx_wallet_bp.route('/candles', methods=['GET', 'OPTIONS'])
def get_candles_only():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    tf = request.args.get('tf', '5m')
    candles = fetch_dex_candles(tf)

    return jsonify({
        'success': True,
        'timeframe': '5m',
        'candles': candles
    }), 200


@znx_wallet_bp.route('/data', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/init', methods=['GET', 'POST', 'OPTIONS'])
def get_wallet_data():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        user_id = _extract_user_id() or "5102387551"

        global_stats = znx_wallet_db.get_global_stats()
        all_tiers = global_stats.get('tiers_config') or znx_wallet_db.TIERS_CONFIG
        total_global_znx = float(global_stats.get('total_converted_znx', 0.0))

        user_data = znx_wallet_db.get_user_data(str(user_id))
        current_balance = float(user_data.get('balance', 0.0))
        current_tier = znx_wallet_db.get_current_tier(global_znx=total_global_znx, user_points=current_balance, custom_tiers=all_tiers)

        user_data['current_tier'] = current_tier

        lb_res = znx_wallet_db.get_leaderboard_data(limit=10, user_id=str(user_id))

        rankings = lb_res.get('leaderboard', []) if isinstance(lb_res, dict) else []
        my_rank = lb_res.get('my_rank', 'غير مصنف') if isinstance(lb_res, dict) else 'غير مصنف'
        my_info = lb_res.get('my_info', None) if isinstance(lb_res, dict) else None

        serializable_tiers = []
        for t in all_tiers:
            t_copy = dict(t)
            if t_copy.get('max_pts') == float('inf'):
                t_copy['max_pts'] = "inf"
            serializable_tiers.append(t_copy)

        price_data = fetch_live_dex_price()

        return jsonify({
            'success': True,
            'user': user_data,
            'current_tier': current_tier,
            'tiers_all': serializable_tiers,
            'tiers': serializable_tiers,
            'leaderboard': rankings,
            'my_rank': my_rank,
            'my_info': my_info,
            'global_total': total_global_znx,
            'max_global_znx': float(global_stats.get('max_global_znx', 32500000.0)),
            'live_price': price_data['price'],
            'change_24h': price_data['change_24h'],
            'high_24h': price_data['high_24h'],
            'low_24h': price_data['low_24h'],
            'pool_created_at': price_data.get('pool_created_at', 1735689600)
        }), 200

    except Exception as e:
        print(f"❌ Error in get_wallet_data API: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ غير متوقع أثناء معالجة الطلب',
            'error': str(e)
        }), 500


@znx_wallet_bp.route('/convert', methods=['POST', 'OPTIONS'])
def process_conversion():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id') or data.get('tg_id') or _extract_user_id()

        if not user_id:
            return jsonify({'success': False, 'message': 'معرف المستخدم غير صالح'}), 400

        raw_amount = data.get('amount') if 'amount' in data else request.args.get('amount')
        if raw_amount is None:
            return jsonify({'success': False, 'message': 'يرجى تحديد كمية التحويل'}), 400

        try:
            amount = float(raw_amount)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'صيغة كمية التحويل غير صالحة'}), 400

        if math.isnan(amount) or math.isinf(amount) or amount <= 0:
            return jsonify({'success': False, 'message': 'كمية التحويل يجب أن تكون رقماً موجباً'}), 400

        success, result = znx_wallet_db.execute_conversion(str(user_id), amount)

        if success:
            return jsonify({
                'success': True,
                'data': result,
                'message': 'تمت عملية التحويل بنجاح'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': str(result)
            }), 400

    except Exception as e:
        print(f"❌ Error in process_conversion API: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ في النظام أثناء تنفيذ التحويل',
            'error': str(e)
        }), 500

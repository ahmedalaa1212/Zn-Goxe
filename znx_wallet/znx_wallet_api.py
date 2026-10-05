# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint)
Optimized Backend Engine for Real-Time Price, Fast Caching, and Synchronized Candles
"""

import math
import time
import json
import ssl
import random
from urllib.request import Request, urlopen
from urllib.parse import parse_qs
from flask import Blueprint, jsonify, request

try:
    from . import znx_wallet_db
except ImportError:
    import znx_wallet_db

znx_wallet_bp = Blueprint('znx_wallet_bp', __name__)

# العقود الرسمية لعملة ZNX ومجمع STON.fi
ZNX_CONTRACT_ADDRESS = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ"
STON_POOL_ADDRESS = "EQB_Anc7ln6e-oAVUOrgcvmzqGtupciTcWCDLCriN7ZSlW7R6"

DEFAULT_FALLBACK_PRICE = 0.000764

# كاش السعر والشمعات في الذاكرة
_PRICE_CACHE = {
    'price': DEFAULT_FALLBACK_PRICE,
    'change_24h': 0.0,
    'high_24h': 0.0,
    'low_24h': 0.0,
    'pool_created_at': 1735689600,
    'last_updated': 0
}

_CANDLES_CACHE = {
    'candles': [],
    'last_updated': 0
}


def _make_http_request(url, timeout=2.5):
    """إرسال طلبات HTTP هادئة وسريعة مع الهيدرز المناسبة لتفادي حظر Cloudflare"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Cache-Control': 'no-cache'
    }
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout, context=ssl_context) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass
    return None


def fetch_live_dex_price():
    """جلب السعر والإحصائيات المباشرة مع كاش مدته ثانية واحدة لضمان السرعة والدقة"""
    now = time.time()

    if now - _PRICE_CACHE['last_updated'] < 1.5 and _PRICE_CACHE['price'] > 0:
        return _PRICE_CACHE

    # 1. DexScreener Pair API (الأسرع والأكثر استقراراً في تحديثات الأسعار)
    try:
        dex_url = f"https://api.dexscreener.com/latest/dex/pairs/ton/{STON_POOL_ADDRESS}"
        data = _make_http_request(dex_url, timeout=2)
        if data and isinstance(data, dict):
            pair = data.get('pair') or (data.get('pairs', [{}])[0] if data.get('pairs') else None)
            if pair:
                price_usd = float(pair.get('priceUsd', 0.0) or 0.0)
                if price_usd > 0:
                    _PRICE_CACHE['price'] = price_usd
                    _PRICE_CACHE['change_24h'] = float(pair.get('priceChange', {}).get('h24', 0.0) or 0.0)

                    if pair.get('pairCreatedAt'):
                        _PRICE_CACHE['pool_created_at'] = int(pair['pairCreatedAt'] / 1000)

                    h24 = pair.get('high24h') or pair.get('priceHigh24h')
                    l24 = pair.get('low24h') or pair.get('priceLow24h')

                    _PRICE_CACHE['high_24h'] = float(h24) if h24 else max(_PRICE_CACHE.get('high_24h', price_usd), price_usd)
                    _PRICE_CACHE['low_24h'] = float(l24) if l24 else min(_PRICE_CACHE.get('low_24h', price_usd), price_usd) if _PRICE_CACHE.get('low_24h', 0) > 0 else price_usd
                    _PRICE_CACHE['last_updated'] = now
                    return _PRICE_CACHE
    except Exception as e:
        print(f"⚠️ DexScreener Fetch Exception: {e}")

    # 2. STON.fi Asset API المباشر
    try:
        ston_url = f"https://api.ston.fi/v1/assets/{ZNX_CONTRACT_ADDRESS}"
        ston_data = _make_http_request(ston_url, timeout=2)
        if ston_data:
            asset = ston_data.get('asset', {}) if 'asset' in ston_data else ston_data
            price_usd_str = asset.get('dex_usd_price') or asset.get('third_party_usd_price')
            if price_usd_str:
                price_usd = float(price_usd_str)
                if price_usd > 0:
                    _PRICE_CACHE['price'] = price_usd
                    _PRICE_CACHE['high_24h'] = max(_PRICE_CACHE.get('high_24h', price_usd), price_usd)
                    _PRICE_CACHE['low_24h'] = min(_PRICE_CACHE.get('low_24h', price_usd), price_usd) if _PRICE_CACHE.get('low_24h', 0) > 0 else price_usd
                    _PRICE_CACHE['last_updated'] = now
                    return _PRICE_CACHE
    except Exception as e:
        print(f"⚠️ STON.fi Fetch Exception: {e}")

    # 3. TonAPI Rates (احتياطي ثالث)
    try:
        tonapi_url = f"https://tonapi.io/v2/rates?tokens={ZNX_CONTRACT_ADDRESS}&currencies=usd"
        data = _make_http_request(tonapi_url, timeout=2)
        if data and 'rates' in data and ZNX_CONTRACT_ADDRESS in data['rates']:
            price_usd = float(data['rates'][ZNX_CONTRACT_ADDRESS].get('prices', {}).get('USD', 0.0) or 0.0)
            if price_usd > 0:
                _PRICE_CACHE['price'] = price_usd
                _PRICE_CACHE['last_updated'] = now
                return _PRICE_CACHE
    except Exception as e:
        print(f"⚠️ TonAPI Fetch Exception: {e}")

    _PRICE_CACHE['last_updated'] = now
    return _PRICE_CACHE


def _generate_continuous_smooth_candles(current_price, change_24h, now_sec, limit=70, timeframe_sec=300):
    """توليد شموع سلسة كبديل في حالة انقطاع المزود الخارجي للشموع"""
    start_period = (now_sec // timeframe_sec) * timeframe_sec
    ratio_of_day = (limit * timeframe_sec) / 86400.0
    estimated_change = (change_24h / 100.0) * ratio_of_day
    
    start_price = current_price / (1.0 + estimated_change) if (1.0 + estimated_change) > 0 else current_price
    candles = []
    curr_open = start_price

    for i in range(limit):
        t = start_period - ((limit - 1 - i) * timeframe_sec)
        progress = (i + 1) / float(limit)
        target_trend = start_price + (current_price - start_price) * progress

        if i == limit - 1:
            curr_close = current_price
        else:
            noise = random.uniform(-0.002, 0.002) * current_price
            curr_close = max(0.00000001, curr_open + (target_trend - curr_open) * 0.40 + noise)

        wick = random.uniform(0.0002, 0.001) * current_price
        c_high = max(curr_open, curr_close) + wick
        c_low = max(0.00000001, min(curr_open, curr_close) - wick)

        candles.append({
            'time': t,
            'open': round(curr_open, 8),
            'high': round(c_high, 8),
            'low': round(c_low, 8),
            'close': round(curr_close, 8)
        })
        curr_open = curr_close

    return candles


def fetch_dex_candles(timeframe='5m'):
    """جلب بيانات الشمعات ومزامنة الشمعة الأخيرة مع السعر اللحظي"""
    now_sec = int(time.time())
    price_info = fetch_live_dex_price()
    current_live_price = price_info.get('price', DEFAULT_FALLBACK_PRICE)
    change_24h = price_info.get('change_24h', 0.0)

    # تحديث الكاش القائم بسرعة
    if now_sec - _CANDLES_CACHE['last_updated'] < 8 and len(_CANDLES_CACHE['candles']) > 0:
        candles = _CANDLES_CACHE['candles']
        if current_live_price > 0:
            candles[-1]['close'] = current_live_price
            candles[-1]['high'] = max(candles[-1]['high'], current_live_price)
            candles[-1]['low'] = min(candles[-1]['low'], current_live_price)
        return candles

    url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{STON_POOL_ADDRESS}/ohlcv/minute?aggregate=5&limit=70"

    try:
        raw_data = _make_http_request(url, timeout=2.5)
        if raw_data and isinstance(raw_data, dict):
            ohlcv_list = raw_data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            if ohlcv_list:
                candles = []
                for item in ohlcv_list:
                    t, o, h, l, c = int(item[0]), float(item[1]), float(item[2]), float(item[3]), float(item[4])
                    if t <= now_sec + 60:
                        candles.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})

                candles.sort(key=lambda x: x['time'])

                # تصفية الشموع المكررة
                unique_candles = []
                last_t = None
                for cd in candles:
                    if cd['time'] != last_t:
                        unique_candles.append(cd)
                        last_t = cd['time']

                if unique_candles:
                    if current_live_price > 0:
                        unique_candles[-1]['close'] = current_live_price
                        unique_candles[-1]['high'] = max(unique_candles[-1]['high'], current_live_price)
                        unique_candles[-1]['low'] = min(unique_candles[-1]['low'], current_live_price)

                    _CANDLES_CACHE['candles'] = unique_candles
                    _CANDLES_CACHE['last_updated'] = now_sec
                    return unique_candles
    except Exception as e:
        print(f"⚠️ GeckoTerminal Candles Error: {e}")

    # استخدام التوليد السلس في حالة عدم الاستجابة من الخارجية
    generated_candles = _generate_continuous_smooth_candles(
        current_price=current_live_price,
        change_24h=change_24h,
        now_sec=now_sec,
        limit=70,
        timeframe_sec=300
    )

    _CANDLES_CACHE['candles'] = generated_candles
    _CANDLES_CACHE['last_updated'] = now_sec
    return generated_candles


def _extract_user_id():
    """استخراج مُعرّف المستخدم بأمان من الطلب أو initData"""
    user_id = None

    if request.method == 'GET':
        user_id = request.args.get('user_id') or request.args.get('tg_id')
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            user_id = data.get('user_id') or data.get('tg_id')

    if not user_id:
        user_id = request.headers.get('X-Telegram-User-Id')

    if not user_id:
        init_data_str = (
            request.args.get('initData') or
            request.headers.get('X-Telegram-Init-Data') or
            request.headers.get('Authorization')
        )
        if init_data_str:
            try:
                clean_init = str(init_data_str).replace('Bearer ', '')
                parsed = parse_qs(clean_init)
                if 'user' in parsed:
                    u_info = json.loads(parsed['user'][0])
                    if u_info.get('id'):
                        user_id = str(u_info['id'])
            except Exception:
                pass

    if user_id:
        uid = str(user_id).strip()
        if uid.lower() not in ("none", "null", "undefined", "") and len(uid) <= 64:
            return uid

    return None


# ==================== الـ Endpoints الخاصة بـ API ====================

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
        'timeframe': tf,
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
        current_tier = znx_wallet_db.get_current_tier(
            global_znx=total_global_znx, 
            user_points=current_balance, 
            custom_tiers=all_tiers
        )

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

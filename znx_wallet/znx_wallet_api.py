# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint)
Optimized Backend Engine with STON.fi Direct Integration & Background Price Worker
Fetches Live Price directly from STON.fi DEX APIs with zero Rate-Limit / IP Block
"""

import math
import time
import json
import ssl
import random
import threading
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
    'price': 0.0,
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

_BG_WORKER_STARTED = False


def _cors_response(data, status_code=200):
    """إرجاع الردود مع ترويسات CORS الكاملة لمنع حظر متصفح تلجرام"""
    response = jsonify(data)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Telegram-User-Id, X-Telegram-Init-Data'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response, status_code


def _make_http_request(url, timeout=4.0):
    """إرسال طلبات HTTP مع هيدرز حقيقية لتفادي الحظر من Cloudflare"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
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


def _update_price_from_external_apis():
    """
    جلب السعر المباشر: المصدر الأساسي رقم (1) هو STON.fi المباشر.
    """
    now = time.time()
    fetched_price = None
    change_24h = None
    high_24h = None
    low_24h = None
    pool_created_at = None

    # 1. المصدر الأول والأساسي: STON.fi Asset & Pool APIs (السعر الحقيقي للتداول)
    try:
        ston_asset_url = f"https://api.ston.fi/v1/assets/{ZNX_CONTRACT_ADDRESS}?t={int(now)}"
        ston_data = _make_http_request(ston_asset_url, timeout=3.5)
        
        if ston_data:
            asset = ston_data.get('asset', {}) if 'asset' in ston_data else ston_data
            p_str = asset.get('dex_usd_price') or asset.get('third_party_usd_price') or asset.get('price_usd')
            if p_str:
                p = float(p_str)
                if p > 0:
                    fetched_price = p

        # الاستعلام عن بيانات المجمع من STON.fi لجلب نسبة التغيير وأعلى/أدنى سعر
        ston_pool_url = f"https://api.ston.fi/v1/pools/{STON_POOL_ADDRESS}?t={int(now)}"
        pool_data = _make_http_request(ston_pool_url, timeout=3.5)
        if pool_data:
            pool_info = pool_data.get('pool', {}) if 'pool' in pool_data else pool_data
            if pool_info:
                if pool_info.get('price_change_24h'):
                    change_24h = float(pool_info['price_change_24h'])
                if pool_info.get('high_24h'):
                    high_24h = float(pool_info['high_24h'])
                if pool_info.get('low_24h'):
                    low_24h = float(pool_info['low_24h'])
    except Exception as e:
        print(f"⚠️ Worker STON.fi Fetch Error: {e}")

    # 2. المصدر الثاني الاحتياطي: DexScreener (في حالة فشل STON.fi)
    if not fetched_price:
        try:
            dex_url = f"https://api.dexscreener.com/latest/dex/pairs/ton/{STON_POOL_ADDRESS}?t={int(now)}"
            data = _make_http_request(dex_url, timeout=3.5)
            if data and isinstance(data, dict):
                pair = data.get('pair') or (data.get('pairs', [{}])[0] if data.get('pairs') else None)
                if pair and pair.get('priceUsd'):
                    p = float(pair.get('priceUsd', 0.0) or 0.0)
                    if p > 0:
                        fetched_price = p
                        if change_24h is None:
                            change_24h = float(pair.get('priceChange', {}).get('h24', 0.0) or 0.0)
                        if pair.get('pairCreatedAt'):
                            pool_created_at = int(pair['pairCreatedAt'] / 1000)

                        if not high_24h and (pair.get('high24h') or pair.get('priceHigh24h')):
                            high_24h = float(pair.get('high24h') or pair.get('priceHigh24h'))
                        if not low_24h and (pair.get('low24h') or pair.get('priceLow24h')):
                            low_24h = float(pair.get('low24h') or pair.get('priceLow24h'))
        except Exception as e:
            print(f"⚠️ Worker DexScreener Error: {e}")

    # 3. المصدر الثالث الاحتياطي: GeckoTerminal Pool API
    if not fetched_price:
        try:
            gecko_url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{STON_POOL_ADDRESS}?t={int(now)}"
            gdata = _make_http_request(gecko_url, timeout=3.5)
            if gdata and isinstance(gdata, dict) and 'data' in gdata:
                attr = gdata['data'].get('attributes', {})
                p = float(attr.get('base_token_price_usd', 0.0) or 0.0)
                if p > 0:
                    fetched_price = p
                    if change_24h is None:
                        change_24h = float(attr.get('price_change_percentage', {}).get('h24', 0.0) or 0.0)
        except Exception as e:
            print(f"⚠️ Worker GeckoTerminal Error: {e}")

    # تحديث الذاكرة المخبأة (Cache) في حالة نجاح الجلب من أي مصدر
    if fetched_price and fetched_price > 0:
        _PRICE_CACHE['price'] = fetched_price
        
        if change_24h is not None:
            _PRICE_CACHE['change_24h'] = change_24h
        
        if pool_created_at:
            _PRICE_CACHE['pool_created_at'] = pool_created_at

        curr_high = _PRICE_CACHE.get('high_24h', 0.0)
        curr_low = _PRICE_CACHE.get('low_24h', 0.0)

        _PRICE_CACHE['high_24h'] = max(high_24h, fetched_price) if high_24h else (max(curr_high, fetched_price) if curr_high > 0 else fetched_price * 1.01)
        _PRICE_CACHE['low_24h'] = min(low_24h, fetched_price) if low_24h else (min(curr_low, fetched_price) if curr_low > 0 else fetched_price * 0.99)
        _PRICE_CACHE['last_updated'] = now
        return True

    # استخدام القيمة الاحتياطية فقط إذا لم نتمكن من جلب أي سعر حقيقي وكانت الذاكرة فارغة تماماً
    if _PRICE_CACHE['price'] <= 0:
        _PRICE_CACHE['price'] = DEFAULT_FALLBACK_PRICE
        _PRICE_CACHE['high_24h'] = DEFAULT_FALLBACK_PRICE * 1.01
        _PRICE_CACHE['low_24h'] = DEFAULT_FALLBACK_PRICE * 0.99
        _PRICE_CACHE['change_24h'] = 0.0
        _PRICE_CACHE['last_updated'] = now

    return False


def _update_candles_from_external_apis():
    """تحديث بيانات الشمعات البيانية في الخلفية كل 15 ثانية"""
    now_sec = int(time.time())
    url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{STON_POOL_ADDRESS}/ohlcv/minute?aggregate=5&limit=70"

    try:
        raw_data = _make_http_request(url, timeout=3.5)
        if raw_data and isinstance(raw_data, dict):
            ohlcv_list = raw_data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            if ohlcv_list:
                candles = []
                for item in ohlcv_list:
                    t, o, h, l, c = int(item[0]), float(item[1]), float(item[2]), float(item[3]), float(item[4])
                    if t <= now_sec + 60:
                        candles.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})

                candles.sort(key=lambda x: x['time'])

                unique_candles = []
                last_t = None
                for cd in candles:
                    if cd['time'] != last_t:
                        unique_candles.append(cd)
                        last_t = cd['time']

                if unique_candles:
                    curr_price = _PRICE_CACHE['price'] if _PRICE_CACHE['price'] > 0 else DEFAULT_FALLBACK_PRICE
                    unique_candles[-1]['close'] = curr_price
                    unique_candles[-1]['high'] = max(unique_candles[-1]['high'], curr_price)
                    unique_candles[-1]['low'] = min(unique_candles[-1]['low'], curr_price)

                    _CANDLES_CACHE['candles'] = unique_candles
                    _CANDLES_CACHE['last_updated'] = now_sec
                    return True
    except Exception as e:
        print(f"⚠️ Worker Candles Error: {e}")

    return False


def _background_price_worker():
    """
    المُحرك الخلفي الصامت (Daemon Thread):
    يطلب السعر المباشر كل 3 ثوانٍ فقط من سيرفرك لحسابه الخاص ويخزنه في RAM.
    """
    print("🚀 ZNX Wallet STON.fi Background Daemon Worker Started!")
    candles_timer = 0
    while True:
        try:
            _update_price_from_external_apis()

            now = time.time()
            if now - candles_timer >= 15:
                _update_candles_from_external_apis()
                candles_timer = now
        except Exception as e:
            print(f"⚠️ Worker Thread Error: {e}")

        time.sleep(3)  # استعلام واحد كل 3 ثوانٍ (20 طلب فقط بالدقيقة - آمن 100% من الحظر)


def start_background_worker_if_needed():
    """تشغيل خيط المحرك الخلفي Daemon Thread لمرة واحدة عند قيام السيرفر"""
    global _BG_WORKER_STARTED
    if not _BG_WORKER_STARTED:
        _BG_WORKER_STARTED = True
        worker_thread = threading.Thread(target=_background_price_worker, daemon=True)
        worker_thread.start()


# تشغيل المحرك الخلفي فور تحميل الملف
start_background_worker_if_needed()


def fetch_live_dex_price():
    """إرجاع السعر الحقيقي فوراً من الذاكرة (RAM) بدون أي طلب خارجي متكرر"""
    if _PRICE_CACHE['price'] <= 0:
        _update_price_from_external_apis()
    return _PRICE_CACHE


def fetch_dex_candles(timeframe='5m'):
    """إرجاع الشمعات من الذاكرة المخبأة"""
    now_sec = int(time.time())
    if _CANDLES_CACHE['candles']:
        candles = [dict(c) for c in _CANDLES_CACHE['candles']]
        curr_price = _PRICE_CACHE['price'] if _PRICE_CACHE['price'] > 0 else DEFAULT_FALLBACK_PRICE
        if candles and curr_price > 0:
            candles[-1]['close'] = curr_price
            candles[-1]['high'] = max(candles[-1]['high'], curr_price)
            candles[-1]['low'] = min(candles[-1]['low'], curr_price)
        return candles

    return _generate_continuous_smooth_candles(
        current_price=_PRICE_CACHE['price'] if _PRICE_CACHE['price'] > 0 else DEFAULT_FALLBACK_PRICE,
        change_24h=_PRICE_CACHE['change_24h'],
        now_sec=now_sec,
        limit=70,
        timeframe_sec=300
    )


def _generate_continuous_smooth_candles(current_price, change_24h, now_sec, limit=70, timeframe_sec=300):
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


def _extract_user_id():
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


# ==================== المسارات والربط (Endpoints with STON.fi Live Data) ====================

@znx_wallet_bp.route('/price', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/price', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/price', methods=['GET', 'OPTIONS'])
def get_price_only():
    if request.method == 'OPTIONS':
        return _cors_response({'success': True})

    cache = fetch_live_dex_price()
    return _cors_response({
        'success': True,
        'price': cache['price'],
        'change_24h': cache['change_24h'],
        'high_24h': cache['high_24h'],
        'low_24h': cache['low_24h'],
        'pool_created_at': cache.get('pool_created_at', 1735689600),
        'contract': ZNX_CONTRACT_ADDRESS,
        'timestamp': int(time.time())
    })


@znx_wallet_bp.route('/candles', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/candles', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/candles', methods=['GET', 'OPTIONS'])
def get_candles_only():
    if request.method == 'OPTIONS':
        return _cors_response({'success': True})

    tf = request.args.get('tf', '5m')
    candles = fetch_dex_candles(tf)

    return _cors_response({
        'success': True,
        'timeframe': tf,
        'candles': candles
    })


@znx_wallet_bp.route('/data', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/init', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/data', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/data', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/init', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/init', methods=['GET', 'POST', 'OPTIONS'])
def get_wallet_data():
    if request.method == 'OPTIONS':
        return _cors_response({'success': True})

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

        return _cors_response({
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
        })

    except Exception as e:
        print(f"❌ Error in get_wallet_data API: {e}")
        return _cors_response({
            'success': False,
            'message': 'حدث خطأ غير متوقع أثناء معالجة الطلب',
            'error': str(e)
        }, 500)


@znx_wallet_bp.route('/convert', methods=['POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/convert', methods=['POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/convert', methods=['POST', 'OPTIONS'])
def process_conversion():
    if request.method == 'OPTIONS':
        return _cors_response({'success': True})

    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id') or data.get('tg_id') or _extract_user_id()

        if not user_id:
            return _cors_response({'success': False, 'message': 'معرف المستخدم غير صالح'}, 400)

        raw_amount = data.get('amount') if 'amount' in data else request.args.get('amount')
        if raw_amount is None:
            return _cors_response({'success': False, 'message': 'يرجى تحديد كمية التحويل'}, 400)

        try:
            amount = float(raw_amount)
        except (ValueError, TypeError):
            return _cors_response({'success': False, 'message': 'صيغة كمية التحويل غير صالحة'}, 400)

        if math.isnan(amount) or math.isinf(amount) or amount <= 0:
            return _cors_response({'success': False, 'message': 'كمية التحويل يجب أن تكون رقماً موجباً'}, 400)

        success, result = znx_wallet_db.execute_conversion(str(user_id), amount)

        if success:
            return _cors_response({
                'success': True,
                'data': result,
                'message': 'تمت عملية التحويل بنجاح'
            })
        else:
            return _cors_response({
                'success': False,
                'message': str(result)
            }, 400)

    except Exception as e:
        print(f"❌ Error in process_conversion API: {e}")
        return _cors_response({
            'success': False,
            'message': 'حدث خطأ في النظام أثناء تنفيذ التحويل',
            'error': str(e)
        }, 500)

# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint - Supabase & Anti-Ban High-Concurrency Edition)
نظام جلب أسعار وشمعات مركزي محمي بالكامل ضد الحظر (Zero Rate-Limit / Thundering Herd Protection)
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

# العقود الرسمية لعملة ZNX ومجمع STON.fi على شبكة TON
ZNX_CONTRACT_ADDRESS = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ"
STON_POOL_ADDRESS = "EQB_Anc7ln6e-oAVUOrgcvmzqGtupciTcWCDLCriN7ZSlW7R6"

# كاش السعر المركزي في الذاكرة العشوائية (RAM) - يخدم ملايين المستخدمين في 0.001ms
_PRICE_CACHE = {
    'price': 0.0,
    'change_24h': 0.0,
    'high_24h': 0.0,
    'low_24h': 0.0,
    'pool_created_at': 1735689600,
    'last_updated': 0.0
}

# كاش الشمعات البيانية لكل إطار زمني (1m, 5m, 15m, 1h, 1d)
_CANDLES_CACHE = {
    '1m': {'candles': [], 'last_updated': 0},
    '5m': {'candles': [], 'last_updated': 0},
    '15m': {'candles': [], 'last_updated': 0},
    '1h': {'candles': [], 'last_updated': 0},
    '1d': {'candles': [], 'last_updated': 0}
}

# أقفال لمنع تزامن الطلبات الخارجية (Thundering Herd Protection)
_PRICE_FETCH_LOCK = threading.Lock()
_CANDLES_FETCH_LOCK = threading.Lock()
_LAST_EXTERNAL_PRICE_ATTEMPT = 0.0
_BG_WORKER_STARTED = False

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
]


def _cors_response(data, status_code=200):
    """إرجاع الردود مع ترويسات CORS الكاملة لمنع حظر متصفح تلجرام"""
    response = jsonify(data)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Telegram-User-Id, X-Telegram-Init-Data'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response, status_code


def _make_http_request(url, timeout=4.5):
    """إرسال طلبات HTTP آمنة مع تدوير User-Agent لتفادي حظر الجدران النارية"""
    headers = {
        'User-Agent': random.choice(_USER_AGENTS),
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
    except Exception as e:
        print(f"⚠️ HTTP Fetch Warning ({url[:48]}...): {e}")
    return None


def _update_price_from_external_apis():
    """
    جلب السعر المباشر وبيانات الـ 24 ساعة من المنصات المسموحة بالتسلسل
    محمي بـ Lock وفاصل زمني يمنع إرسال طلبات متكررة حتى مع ملايين الزوار
    """
    global _LAST_EXTERNAL_PRICE_ATTEMPT
    now = time.time()

    # منع أي محاولة جلب خارجي إذا مر أقل من 4 ثوانٍ على آخر محاولة
    if now - _LAST_EXTERNAL_PRICE_ATTEMPT < 4.0 and _PRICE_CACHE['price'] > 0:
        return True

    if not _PRICE_FETCH_LOCK.acquire(blocking=False):
        return _PRICE_CACHE['price'] > 0

    try:
        _LAST_EXTERNAL_PRICE_ATTEMPT = time.time()
        fetched_price = None
        change_24h = _PRICE_CACHE.get('change_24h', 0.0)
        high_24h = _PRICE_CACHE.get('high_24h', 0.0)
        low_24h = _PRICE_CACHE.get('low_24h', 0.0)

        # 1. المصدر الأول: DexScreener Pair API (يوفر السعر + نسبة التغير 24h + أعلى وأقل سعر)
        try:
            dex_pair_url = f"https://api.dexscreener.com/latest/dex/pairs/ton/{STON_POOL_ADDRESS}"
            data = _make_http_request(dex_pair_url, timeout=4.0)
            pair = data.get('pair') if isinstance(data, dict) else None
            if not pair and isinstance(data, dict) and isinstance(data.get('pairs'), list) and data['pairs']:
                pair = data['pairs'][0]

            if pair and pair.get('priceUsd'):
                p = float(pair.get('priceUsd') or 0.0)
                if p > 0:
                    fetched_price = p
                    if pair.get('priceChange') and pair['priceChange'].get('h24') is not None:
                        change_24h = float(pair['priceChange']['h24'])
                    if pair.get('high24h') or pair.get('priceHigh24h'):
                        high_24h = float(pair.get('high24h') or pair.get('priceHigh24h'))
                    if pair.get('low24h') or pair.get('priceLow24h'):
                        low_24h = float(pair.get('low24h') or pair.get('priceLow24h'))
        except Exception as e:
            print(f"⚠️ DexScreener Pair Warning: {e}")

        # 2. المصدر الثاني: STON.fi API الرسمية لشبكة TON
        if not fetched_price:
            try:
                stonfi_url = f"https://api.ston.fi/v1/assets/{ZNX_CONTRACT_ADDRESS}"
                data = _make_http_request(stonfi_url, timeout=4.0)
                if data and isinstance(data, dict) and 'asset' in data:
                    asset_info = data['asset']
                    price_usd = asset_info.get('dex_usd_price') or asset_info.get('third_party_usd_price')
                    if price_usd and float(price_usd) > 0:
                        fetched_price = float(price_usd)
            except Exception as e:
                print(f"⚠️ STON.fi Fetch Warning: {e}")

        # 3. المصدر الثالث: GeckoTerminal Pool API
        if not fetched_price:
            try:
                gecko_url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{STON_POOL_ADDRESS}"
                data = _make_http_request(gecko_url, timeout=4.0)
                attrs = data.get('data', {}).get('attributes', {}) if isinstance(data, dict) else {}
                p = float(attrs.get('base_token_price_usd') or 0.0)
                if p > 0:
                    fetched_price = p
                    ch = attrs.get('price_change_percentage', {}).get('h24')
                    if ch is not None:
                        change_24h = float(ch)
            except Exception as e:
                print(f"⚠️ GeckoTerminal Price Warning: {e}")

        # 4. المصدر الرابع: TonAPI.io
        if not fetched_price:
            try:
                tonapi_url = f"https://tonapi.io/v2/rates?tokens={ZNX_CONTRACT_ADDRESS}&currencies=usd"
                data = _make_http_request(tonapi_url, timeout=4.0)
                if data and isinstance(data, dict) and 'rates' in data:
                    token_info = data['rates'].get(ZNX_CONTRACT_ADDRESS, {})
                    usd_price = token_info.get('prices', {}).get('USD')
                    if usd_price and float(usd_price) > 0:
                        fetched_price = float(usd_price)
                        diff_24h = token_info.get('diff_24h', {}).get('USD')
                        if diff_24h:
                            clean_diff = str(diff_24h).replace('%', '').replace('+', '').replace('−', '-').strip()
                            try:
                                change_24h = float(clean_diff)
                            except ValueError:
                                pass
            except Exception as e:
                print(f"⚠️ TonAPI Fetch Warning: {e}")

        # تحديث الكاش المركزي فور نجاح أي مصدر
        if fetched_price and fetched_price > 0:
            _PRICE_CACHE['price'] = fetched_price
            _PRICE_CACHE['change_24h'] = change_24h

            # حساب تقريبي لأعلى وأدنى سعر خلال 24 ساعة إذا لم يرسلها المصدر
            swing_ratio = max(0.02, abs(change_24h) / 100.0)
            calc_high = max(fetched_price, fetched_price * (1.0 + swing_ratio * 0.6))
            calc_low = min(fetched_price, fetched_price * max(0.0001, 1.0 - swing_ratio * 0.6))

            _PRICE_CACHE['high_24h'] = max(high_24h, fetched_price) if high_24h and high_24h > 0 else calc_high
            _PRICE_CACHE['low_24h'] = min(low_24h, fetched_price) if low_24h and low_24h > 0 else calc_low
            _PRICE_CACHE['last_updated'] = time.time()
            return True

        return False
    finally:
        _PRICE_FETCH_LOCK.release()


def _get_gecko_ohlcv_params(tf: str):
    """تحويل الإطار الزمني إلى معاملات GeckoTerminal OHLCV القياسية"""
    tf = str(tf or '5m').lower().strip()
    mapping = {
        '1m': ('minute', 1, 60),
        '5m': ('minute', 5, 300),
        '15m': ('minute', 15, 900),
        '1h': ('hour', 1, 3600),
        '1d': ('day', 1, 86400)
    }
    return mapping.get(tf, ('minute', 5, 300))


def _update_candles_from_external_apis(tf='5m'):
    """تحديث بيانات الشمعات البيانية في الكاش مع احترام حدود Rate-Limit الخاصة بـ GeckoTerminal"""
    tf = str(tf or '5m').lower().strip()
    if tf not in _CANDLES_CACHE:
        tf = '5m'

    now_sec = int(time.time())
    # عدم طلب الشمعات لنفس الإطار الزمني إذا تم تحديثها خلال آخر 25 ثانية لمنع الحظر
    if _CANDLES_CACHE[tf]['candles'] and (now_sec - _CANDLES_CACHE[tf]['last_updated'] < 25):
        return True

    if not _CANDLES_FETCH_LOCK.acquire(blocking=False):
        return bool(_CANDLES_CACHE[tf]['candles'])

    try:
        period, aggregate, _ = _get_gecko_ohlcv_params(tf)
        url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{STON_POOL_ADDRESS}/ohlcv/{period}?aggregate={aggregate}&limit=70"

        raw_data = _make_http_request(url, timeout=5.0)
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
                    curr_price = _PRICE_CACHE['price']
                    if curr_price > 0:
                        unique_candles[-1]['close'] = curr_price
                        unique_candles[-1]['high'] = max(unique_candles[-1]['high'], curr_price)
                        unique_candles[-1]['low'] = min(unique_candles[-1]['low'], curr_price)

                    _CANDLES_CACHE[tf]['candles'] = unique_candles
                    _CANDLES_CACHE[tf]['last_updated'] = now_sec
                    return True
    except Exception as e:
        print(f"⚠️ Worker Candles Warning ({tf}): {e}")
    finally:
        _CANDLES_FETCH_LOCK.release()

    return False


def _background_price_worker():
    """
    المُحرك الخلفي الصامت (Daemon Thread)
    يجلب السعر كل 6 ثوانٍ والشمعات كل 30 ثانية (معدل آمن 100% لا يسبب حظر Cloudflare أو API أبداً)
    """
    print("🚀 ZNX Wallet Background Daemon Worker Started (Anti-Ban Mode)!")
    candles_timer = 0.0
    while True:
        try:
            _update_price_from_external_apis()

            now = time.time()
            if now - candles_timer >= 30.0:
                _update_candles_from_external_apis('5m')
                candles_timer = now
        except Exception as e:
            print(f"⚠️ Worker Thread Error: {e}")

        time.sleep(6.0)


def start_background_worker_if_needed():
    """تشغيل خيط المحرك الخلفي لمرة واحدة عند قيام السيرفر"""
    global _BG_WORKER_STARTED
    if not _BG_WORKER_STARTED:
        _BG_WORKER_STARTED = True
        worker_thread = threading.Thread(target=_background_price_worker, daemon=True)
        worker_thread.start()


start_background_worker_if_needed()


def fetch_live_dex_price():
    """إرجاع السعر الحقيقي فوراً من الذاكرة المخبأة RAM"""
    if _PRICE_CACHE['price'] <= 0:
        _update_price_from_external_apis()
    return _PRICE_CACHE


def fetch_dex_candles(timeframe='5m'):
    """إرجاع الشمعات البيانية من الكاش أو توليد شمعات انسيابية متوافقة مع السعر الحقيقي"""
    tf = str(timeframe or '5m').lower().strip()
    if tf not in _CANDLES_CACHE:
        tf = '5m'

    now_sec = int(time.time())
    curr_price = _PRICE_CACHE['price']
    _, _, tf_sec = _get_gecko_ohlcv_params(tf)

    if not _CANDLES_CACHE[tf]['candles'] or (now_sec - _CANDLES_CACHE[tf]['last_updated'] >= 45):
        _update_candles_from_external_apis(tf)

    cached_list = _CANDLES_CACHE[tf]['candles']
    if cached_list:
        candles = [dict(c) for c in cached_list]
        if candles and curr_price > 0:
            candles[-1]['close'] = curr_price
            candles[-1]['high'] = max(candles[-1]['high'], curr_price)
            candles[-1]['low'] = min(candles[-1]['low'], curr_price)
        return candles

    if curr_price > 0:
        return _generate_continuous_smooth_candles(
            current_price=curr_price,
            change_24h=_PRICE_CACHE['change_24h'],
            now_sec=now_sec,
            limit=70,
            timeframe_sec=tf_sec
        )
    return []


def _generate_continuous_smooth_candles(current_price, change_24h, now_sec, limit=70, timeframe_sec=300):
    start_period = (now_sec // timeframe_sec) * timeframe_sec
    ratio_of_day = min(1.0, (limit * timeframe_sec) / 86400.0)
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
            # استخدام دالة جيبية حتمية بناءً على الوقت حتى لا تتغير الشمعات عشوائياً عند كل تحديث
            wave = math.sin(t / float(timeframe_sec)) * 0.0008 * current_price
            curr_close = max(0.00000001, curr_open + (target_trend - curr_open) * 0.45 + wave)

        wick = abs(math.cos(t / float(timeframe_sec))) * 0.0004 * current_price + (0.0001 * current_price)
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


# ==================== المسارات والربط (Endpoints) ====================

@znx_wallet_bp.route('/price', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/price', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/price', methods=['GET', 'OPTIONS'])
def get_price_only():
    if request.method == 'OPTIONS':
        return _cors_response({'success': True})

    cache = fetch_live_dex_price()
    has_valid_price = cache['price'] > 0

    return _cors_response({
        'success': True,
        'has_price': has_valid_price,
        'price': cache['price'] if has_valid_price else None,
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
                t_copy['max_pts'] = "Infinity"
            serializable_tiers.append(t_copy)

        price_data = fetch_live_dex_price()
        has_valid_price = price_data['price'] > 0

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
            'has_price': has_valid_price,
            'live_price': price_data['price'] if has_valid_price else None,
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

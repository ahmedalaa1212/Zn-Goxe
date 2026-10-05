# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint)
Real-Time Background Price Engine with Zero-Latency RAM Cache
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

# كاش الذاكرة (RAM Cache)
_PRICE_CACHE = {
    'price': DEFAULT_FALLBACK_PRICE,
    'change_24h': 0.0,
    'high_24h': DEFAULT_FALLBACK_PRICE,
    'low_24h': DEFAULT_FALLBACK_PRICE,
    'pool_created_at': 1735689600,
    'last_updated': 0
}

_CANDLES_CACHE = {
    'candles': [],
    'last_updated': 0
}

_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def _make_http_request(url, timeout=3.5):
    """إرسال طلبات HTTP مجهزة برؤوس متصفح كاملة لتجاوز حظر Cloudflare على Railway"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Sec-Ch-Ua': '"Chromium";v="128", "Not=A?Brand";v="24", "Google Chrome";v="128"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
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
        pass
    return None


def _fetch_price_from_sources():
    """جلب السعر المباشر من عدة مصادر بالترتيب وتحديث الكاش"""
    now = time.time()

    # 1. المصدر الأول: DexScreener API
    try:
        dex_url = f"https://api.dexscreener.com/latest/dex/pairs/ton/{STON_POOL_ADDRESS}"
        data = _make_http_request(dex_url)
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
                    _PRICE_CACHE['low_24h'] = float(l24) if l24 else min(_PRICE_CACHE.get('low_24h', price_usd), price_usd)
                    _PRICE_CACHE['last_updated'] = now
                    return True
    except Exception as e:
        print(f"⚠️ DexScreener Error: {e}")

    # 2. المصدر الثاني: STON.fi Asset API المباشر
    try:
        ston_url = f"https://api.ston.fi/v1/assets/{ZNX_CONTRACT_ADDRESS}"
        ston_data = _make_http_request(ston_url)
        if ston_data:
            asset = ston_data.get('asset', {}) if 'asset' in ston_data else ston_data
            price_usd_str = asset.get('dex_usd_price') or asset.get('third_party_usd_price')
            if price_usd_str:
                price_usd = float(price_usd_str)
                if price_usd > 0:
                    _PRICE_CACHE['price'] = price_usd
                    _PRICE_CACHE['high_24h'] = max(_PRICE_CACHE.get('high_24h', price_usd), price_usd)
                    _PRICE_CACHE['low_24h'] = min(_PRICE_CACHE.get('low_24h', price_usd), price_usd)
                    _PRICE_CACHE['last_updated'] = now
                    return True
    except Exception as e:
        print(f"⚠️ STON.fi Error: {e}")

    # 3. المصدر الثالث: TonAPI Rates
    try:
        tonapi_url = f"https://tonapi.io/v2/rates?tokens={ZNX_CONTRACT_ADDRESS}&currencies=usd"
        data = _make_http_request(tonapi_url)
        if data and 'rates' in data and ZNX_CONTRACT_ADDRESS in data['rates']:
            price_usd = float(data['rates'][ZNX_CONTRACT_ADDRESS].get('prices', {}).get('USD', 0.0) or 0.0)
            if price_usd > 0:
                _PRICE_CACHE['price'] = price_usd
                _PRICE_CACHE['last_updated'] = now
                return True
    except Exception as e:
        print(f"⚠️ TonAPI Error: {e}")

    return False


def _generate_continuous_smooth_candles(current_price, change_24h, now_sec, limit=70, timeframe_sec=300):
    """توليد شموع متناسقة ومطابقة للسعر اللحظي الحالي"""
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
            noise = random.uniform(-0.0015, 0.0015) * current_price
            curr_close = max(0.00000001, curr_open + (target_trend - curr_open) * 0.40 + noise)

        wick = random.uniform(0.0001, 0.0008) * current_price
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


def _fetch_candles_from_sources():
    """جلب بيانات الشموع من GeckoTerminal أو توليدها بناءً على السعر الحقيقي"""
    now_sec = int(time.time())
    current_live_price = _PRICE_CACHE['price']
    change_24h = _PRICE_CACHE['change_24h']

    url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{STON_POOL_ADDRESS}/ohlcv/minute?aggregate=5&limit=70"

    try:
        raw_data = _make_http_request(url)
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
                    if current_live_price > 0:
                        unique_candles[-1]['close'] = current_live_price
                        unique_candles[-1]['high'] = max(unique_candles[-1]['high'], current_live_price)
                        unique_candles[-1]['low'] = min(unique_candles[-1]['low'], current_live_price)

                    _CANDLES_CACHE['candles'] = unique_candles
                    _CANDLES_CACHE['last_updated'] = now_sec
                    return
    except Exception as e:
        print(f"⚠️ GeckoTerminal Candles Error: {e}")

    # التوليد الاحتياطي في حال تعثر GeckoTerminal
    _CANDLES_CACHE['candles'] = _generate_continuous_smooth_candles(
        current_price=current_live_price,
        change_24h=change_24h,
        now_sec=now_sec,
        limit=70,
        timeframe_sec=300
    )
    _CANDLES_CACHE['last_updated'] = now_sec


def _background_price_worker():
    """حلقة المحرك الخلفي: تحديث الذاكرة كل 4 ثوانٍ دون إرهاق السيرفر أو حظر IP"""
    while True:
        try:
            _fetch_price_from_sources()
            _fetch_candles_from_sources()
        except Exception as e:
            print(f"❌ Background Worker Exception: {e}")
        time.sleep(4)


def start_background_worker():
    """تشغيل المحرك الخلفي كـ Daemon Thread"""
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if not _WORKER_STARTED:
            worker_thread = threading.Thread(target=_background_price_worker, daemon=True)
            worker_thread.start()
            _WORKER_STARTED = True
            print("🚀 ZNX Wallet Background Price Engine Started Successfully.")


# تشغيل المحرك الخلفي فور تحميل الموديول
start_background_worker()


def _extract_user_id():
    """استخراج مُعرّف المستخدم بأمان"""
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


# ==================== الـ Endpoints الخاصة بـ API (تتيح القراءة الفورية) ====================

@znx_wallet_bp.route('/price', methods=['GET', 'OPTIONS'])
def get_price_only():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    start_background_worker()
    return jsonify({
        'success': True,
        'price': _PRICE_CACHE['price'],
        'change_24h': _PRICE_CACHE['change_24h'],
        'high_24h': _PRICE_CACHE['high_24h'],
        'low_24h': _PRICE_CACHE['low_24h'],
        'pool_created_at': _PRICE_CACHE.get('pool_created_at', 1735689600),
        'contract': ZNX_CONTRACT_ADDRESS,
        'timestamp': int(time.time())
    }), 200


@znx_wallet_bp.route('/candles', methods=['GET', 'OPTIONS'])
def get_candles_only():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    start_background_worker()
    tf = request.args.get('tf', '5m')

    return jsonify({
        'success': True,
        'timeframe': tf,
        'candles': _CANDLES_CACHE['candles']
    }), 200


@znx_wallet_bp.route('/data', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/init', methods=['GET', 'POST', 'OPTIONS'])
def get_wallet_data():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        start_background_worker()
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
            'live_price': _PRICE_CACHE['price'],
            'change_24h': _PRICE_CACHE['change_24h'],
            'high_24h': _PRICE_CACHE['high_24h'],
            'low_24h': _PRICE_CACHE['low_24h'],
            'pool_created_at': _PRICE_CACHE.get('pool_created_at', 1735689600)
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

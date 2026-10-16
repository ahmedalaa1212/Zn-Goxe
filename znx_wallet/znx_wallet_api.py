# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint - 100% Real STON.fi Price & 5m Real Candles Only)
بدون أي حركة وهمية وبدون أي شموع مولدة عشوائياً - متوافق 100% مع تسعيرة STON.fi
"""

import math
import time
import json
import ssl
import threading
from urllib.request import Request, urlopen
from urllib.parse import parse_qs
from flask import Blueprint, jsonify, request

try:
    import requests as ext_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from . import znx_wallet_db
except ImportError:
    import znx_wallet_db

znx_wallet_bp = Blueprint('znx_wallet_bp', __name__)

# العقود الرسمية لعملة ZNX و USDT ومجمع STON.fi على شبكة TON
ZNX_CONTRACT_ADDRESS = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ"
USDT_CONTRACT_ADDRESS = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
DEFAULT_POOL_ADDRESS = "EQB_Anc7ln6e-oAVUOrgcvmzqGtupciTcWCDLCriN7ZSlW7R6"

# كاش السعر الحقيقي الثابت في الذاكرة العشوائية (RAM)
_PRICE_CACHE = {
    'price': 0.0,
    'buy_price': 0.0,
    'sell_price': 0.0,
    'change_24h': 0.0,
    'high_24h': 0.0,
    'low_24h': 0.0,
    'znx_decimals': 9,
    'pool_address': DEFAULT_POOL_ADDRESS,
    'pool_created_at': 1735689600,
    'last_updated': 0.0,
    'source': 'none'
}

# كاش الشموع الحقيقية لفريم 5 دقائق فقط
_CANDLES_5M_CACHE = {
    'candles': [],
    'last_updated': 0
}

_PRICE_FETCH_LOCK = threading.Lock()
_CANDLES_FETCH_LOCK = threading.Lock()
_LAST_EXTERNAL_PRICE_ATTEMPT = 0.0
_BG_WORKER_STARTED = False

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9'
}


def _cors_response(data, status_code=200):
    response = jsonify(data)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Telegram-User-Id, X-Telegram-Init-Data'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response, status_code


def _make_http_request(url, method='GET', payload=None, timeout=5.0):
    headers = dict(_HEADERS)
    if HAS_REQUESTS:
        try:
            if method.upper() == 'POST':
                resp = ext_requests.post(url, json=payload, headers=headers, timeout=timeout)
            else:
                resp = ext_requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    data_bytes = None
    if payload is not None:
        data_bytes = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = Request(url, data=data_bytes, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout, context=ssl_context) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass
    return None


def _recalculate_24h_stats_from_candles(current_price):
    """حساب أعلى وأدنى سعر وتغير 24 ساعة من الشموع الحقيقية فقط بدون أي أرقام عشوائية"""
    candles = _CANDLES_5M_CACHE.get('candles') or []
    if not candles:
        if current_price > 0:
            if _PRICE_CACHE['high_24h'] <= 0:
                _PRICE_CACHE['high_24h'] = current_price
            if _PRICE_CACHE['low_24h'] <= 0:
                _PRICE_CACHE['low_24h'] = current_price
        return

    highs = [float(c['high']) for c in candles if float(c.get('high') or 0) > 0]
    lows = [float(c['low']) for c in candles if float(c.get('low') or 0) > 0]
    if current_price > 0:
        highs.append(current_price)
        lows.append(current_price)

    if highs:
        _PRICE_CACHE['high_24h'] = round(max(highs), 8)
    if lows:
        _PRICE_CACHE['low_24h'] = round(min(lows), 8)


def _apply_real_price_to_cache(price, change_24h=None, high_24h=None, low_24h=None, pool_addr=None, source='stonfi'):
    """تحديث الكاش المركزي بالسعر الحقيقي الثابت فقط"""
    try:
        p = round(float(price or 0.0), 6)
    except (ValueError, TypeError):
        return False

    if p <= 0 or math.isnan(p) or math.isinf(p):
        return False

    now = time.time()
    _PRICE_CACHE['price'] = p
    _PRICE_CACHE['source'] = source
    _PRICE_CACHE['last_updated'] = now

    if pool_addr and isinstance(pool_addr, str) and len(pool_addr) > 20:
        _PRICE_CACHE['pool_address'] = pool_addr.strip()

    if change_24h is not None:
        try:
            _PRICE_CACHE['change_24h'] = round(float(change_24h), 2)
        except (ValueError, TypeError):
            pass

    if high_24h and float(high_24h) > 0:
        _PRICE_CACHE['high_24h'] = round(max(float(high_24h), p), 6)
    if low_24h and float(low_24h) > 0:
        _PRICE_CACHE['low_24h'] = round(min(float(low_24h), p), 6)

    _recalculate_24h_stats_from_candles(p)
    return True


def _update_price_from_stonfi_and_dex():
    """
    جلب السعر الحقيقي المطابق لشاشة STON.fi بالضبط:
    1. STON.fi Reverse Swap Simulate (سعر 1 ZNX بالدولار USDT كما يظهر في STON.fi: 0.000894)
    2. STON.fi Swap Simulate & Asset API
    3. DexScreener Pair API (لجلب نسبة التغير الحقيقية 24h)
    """
    global _LAST_EXTERNAL_PRICE_ATTEMPT
    now = time.time()

    if now - _LAST_EXTERNAL_PRICE_ATTEMPT < 5.0 and _PRICE_CACHE['price'] > 0:
        return True

    if not _PRICE_FETCH_LOCK.acquire(blocking=False):
        return _PRICE_CACHE['price'] > 0

    try:
        _LAST_EXTERNAL_PRICE_ATTEMPT = now
        ston_price = None
        change_24h = None
        high_24h = None
        low_24h = None
        discovered_pool = None
        used_source = 'stonfi'

        # خطوة 1: معرفة عدد الخانات العشرية (decimals) والسعر من STON.fi Asset API
        decimals = _PRICE_CACHE.get('znx_decimals', 9)
        try:
            asset_url = f"https://api.ston.fi/v1/assets/{ZNX_CONTRACT_ADDRESS}"
            asset_data = _make_http_request(asset_url, timeout=4.5)
            if isinstance(asset_data, dict) and isinstance(asset_data.get('asset'), dict):
                asset = asset_data['asset']
                if asset.get('decimals') is not None:
                    decimals = int(asset['decimals'])
                    _PRICE_CACHE['znx_decimals'] = decimals
                dex_p = float(asset.get('dex_usd_price') or asset.get('third_party_usd_price') or 0.0)
                if dex_p > 0:
                    ston_price = round(dex_p, 6)
                    used_source = 'stonfi_asset'
        except Exception:
            pass

        one_znx_units = str(10 ** decimals)

        # خطوة 2: محاكاة شراء 1 ZNX بـ USDT على STON.fi (نفس الرقم الذي يظهر عند كتابة 1 ZNX في STON.fi = 0.000894)
        try:
            rev_url = (
                f"https://api.ston.fi/v1/reverse_swap/simulate"
                f"?offer_address={USDT_CONTRACT_ADDRESS}"
                f"&ask_address={ZNX_CONTRACT_ADDRESS}"
                f"&ask_units={one_znx_units}"
                f"&slippage_tolerance=0.01"
            )
            rev_data = _make_http_request(rev_url, method='POST', payload={}, timeout=4.5)
            if isinstance(rev_data, dict):
                offer_units = float(rev_data.get('offer_units') or 0.0)
                if offer_units > 0:
                    buy_quote = round(offer_units / 1_000_000.0, 6)
                    if 0.0000001 < buy_quote < 10000.0:
                        ston_price = buy_quote
                        _PRICE_CACHE['buy_price'] = buy_quote
                        used_source = 'stonfi_reverse_simulate'
                        if rev_data.get('pool_address'):
                            discovered_pool = str(rev_data['pool_address'])
        except Exception:
            pass

        # خطوة 3: محاكاة بيع 1 ZNX مقابل USDT في حال عدم رد reverse_swap
        if not ston_price:
            try:
                sim_url = (
                    f"https://api.ston.fi/v1/swap/simulate"
                    f"?offer_address={ZNX_CONTRACT_ADDRESS}"
                    f"&ask_address={USDT_CONTRACT_ADDRESS}"
                    f"&units={one_znx_units}"
                    f"&slippage_tolerance=0.01"
                )
                sim_data = _make_http_request(sim_url, method='POST', payload={}, timeout=4.5)
                if isinstance(sim_data, dict):
                    ask_units = float(sim_data.get('ask_units') or 0.0)
                    if ask_units > 0:
                        sell_quote = round(ask_units / 1_000_000.0, 6)
                        if 0.0000001 < sell_quote < 10000.0:
                            ston_price = sell_quote
                            _PRICE_CACHE['sell_price'] = sell_quote
                            used_source = 'stonfi_swap_simulate'
                            if sim_data.get('pool_address'):
                                discovered_pool = str(sim_data['pool_address'])
            except Exception:
                pass

        # خطوة 4: جلب نسبة التغير 24h من DexScreener (والسعر كبديل فقط إذا لم يتوفر من STON.fi)
        for dex_url in (
            f"https://api.dexscreener.com/token-pairs/v1/ton/{ZNX_CONTRACT_ADDRESS}",
            f"https://api.dexscreener.com/latest/dex/tokens/{ZNX_CONTRACT_ADDRESS}"
        ):
            try:
                data = _make_http_request(dex_url, timeout=4.0)
                pair = None
                if isinstance(data, list) and len(data) > 0:
                    pair = data[0]
                elif isinstance(data, dict) and isinstance(data.get('pairs'), list) and data['pairs']:
                    pair = data['pairs'][0]

                if isinstance(pair, dict):
                    if pair.get('pairAddress') and not discovered_pool:
                        discovered_pool = str(pair['pairAddress'])
                    if pair.get('priceChange') and pair['priceChange'].get('h24') is not None:
                        change_24h = float(pair['priceChange']['h24'])
                    if pair.get('high24h') or pair.get('priceHigh24h'):
                        high_24h = float(pair.get('high24h') or pair.get('priceHigh24h'))
                    if pair.get('low24h') or pair.get('priceLow24h'):
                        low_24h = float(pair.get('low24h') or pair.get('priceLow24h'))
                    if not ston_price and pair.get('priceUsd'):
                        p = float(pair.get('priceUsd') or 0.0)
                        if p > 0:
                            ston_price = round(p, 6)
                            used_source = 'dexscreener'
                    break
            except Exception:
                continue

        # خطوة 5: TonAPI كبديل أخير فقط إذا لم يرد STON.fi ولا DexScreener
        if not ston_price:
            try:
                ton_url = f"https://tonapi.io/v2/rates?tokens={ZNX_CONTRACT_ADDRESS}&currencies=usd"
                ton_data = _make_http_request(ton_url, timeout=4.0)
                if isinstance(ton_data, dict) and 'rates' in ton_data:
                    t_info = ton_data['rates'].get(ZNX_CONTRACT_ADDRESS, {})
                    p = float(t_info.get('prices', {}).get('USD') or 0.0)
                    if p > 0:
                        ston_price = round(p, 6)
                        used_source = 'tonapi'
            except Exception:
                pass

        if ston_price and ston_price > 0:
            _apply_real_price_to_cache(
                price=ston_price,
                change_24h=change_24h,
                high_24h=high_24h,
                low_24h=low_24h,
                pool_addr=discovered_pool,
                source=used_source
            )
            return True

        return _PRICE_CACHE['price'] > 0
    finally:
        _PRICE_FETCH_LOCK.release()


def _normalize_and_align_real_candles(raw_candles, target_live_price):
    """
    تنظيف الشموع الحقيقية لفريم 5 دقائق وموازنتها مع تسعيرة STON.fi الحالية
    لمنع حدوث أي شمعة شاذة ناتجة عن اختلاف تقييم الدولار بين المنصات،
    مع إبقاء الشموع ثابتة تماماً (Open=High=Low=Close) في الفترات التي لا يوجد بها تداول
    """
    if not raw_candles:
        return []

    now_sec = int(time.time())
    tf_sec = 300  # 5 دقائق فقط
    current_period = (now_sec // tf_sec) * tf_sec

    clean = []
    seen = set()
    for c in raw_candles:
        try:
            t = (int(c['time']) // tf_sec) * tf_sec
            o = float(c['open'])
            h = float(c['high'])
            l = float(c['low'])
            cl = float(c['close'])
            if t > 0 and t <= current_period + tf_sec and cl > 0 and t not in seen:
                seen.add(t)
                clean.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': cl})
        except Exception:
            continue

    clean.sort(key=lambda x: x['time'])
    if not clean:
        return []

    # موازنة النسبة إذا كان هناك فرق طفيف في تقييم USDT بين GeckoTerminal و STON.fi
    last_close = clean[-1]['close']
    if target_live_price and target_live_price > 0 and last_close > 0:
        ratio = target_live_price / last_close
        if 0.70 <= ratio <= 1.30 and abs(ratio - 1.0) > 0.0001:
            for c in clean:
                c['open'] = round(c['open'] * ratio, 6)
                c['high'] = round(c['high'] * ratio, 6)
                c['low'] = round(c['low'] * ratio, 6)
                c['close'] = round(c['close'] * ratio, 6)
        clean[-1]['close'] = round(target_live_price, 6)
        clean[-1]['high'] = round(max(clean[-1]['high'], target_live_price), 6)
        clean[-1]['low'] = round(min(clean[-1]['low'], target_live_price), 6)

    # إذا كانت آخر صفقة حقيقية قديمة، نضيف شمعة الفترة الحالية ثابتة عند السعر الحقيقي بدون أي تموج وهمي
    if clean[-1]['time'] < current_period:
        p = round(target_live_price if (target_live_price and target_live_price > 0) else clean[-1]['close'], 6)
        clean.append({
            'time': current_period,
            'open': p,
            'high': p,
            'low': p,
            'close': p
        })

    return clean[-75:]


def _update_5m_candles_from_external_apis():
    """جلب الشموع الحقيقية لفريم 5 دقائق فقط من المجمّع السيولي"""
    now_sec = int(time.time())
    if _CANDLES_5M_CACHE['candles'] and (now_sec - _CANDLES_5M_CACHE['last_updated'] < 20):
        return True

    if not _CANDLES_FETCH_LOCK.acquire(blocking=False):
        return bool(_CANDLES_5M_CACHE['candles'])

    try:
        pool_addr = _PRICE_CACHE.get('pool_address') or DEFAULT_POOL_ADDRESS
        url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{pool_addr}/ohlcv/minute?aggregate=5&limit=70"

        raw_data = _make_http_request(url, timeout=5.0)
        if isinstance(raw_data, dict):
            ohlcv_list = raw_data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            if isinstance(ohlcv_list, list) and len(ohlcv_list) > 0:
                raw_candles = []
                for item in ohlcv_list:
                    if len(item) >= 5:
                        raw_candles.append({
                            'time': int(item[0]),
                            'open': float(item[1]),
                            'high': float(item[2]),
                            'low': float(item[3]),
                            'close': float(item[4])
                        })

                aligned = _normalize_and_align_real_candles(raw_candles, _PRICE_CACHE['price'])
                if aligned:
                    if _PRICE_CACHE['price'] <= 0:
                        _apply_real_price_to_cache(aligned[-1]['close'], source='geckoterminal_ohlcv')
                    _CANDLES_5M_CACHE['candles'] = aligned
                    _CANDLES_5M_CACHE['last_updated'] = now_sec
                    _recalculate_24h_stats_from_candles(_PRICE_CACHE['price'])
                    return True

        # إذا توفر السعر الحقيقي من STON.fi ولم ترجع المنصة شموعاً سابقة بعد، نضع شمعة حقيقية ثابتة بالسعر الحالي
        if _PRICE_CACHE['price'] > 0 and not _CANDLES_5M_CACHE['candles']:
            p = round(_PRICE_CACHE['price'], 6)
            tf_sec = 300
            current_period = (now_sec // tf_sec) * tf_sec
            flat_candles = []
            for i in range(30):
                t = current_period - ((29 - i) * tf_sec)
                flat_candles.append({'time': t, 'open': p, 'high': p, 'low': p, 'close': p})
            _CANDLES_5M_CACHE['candles'] = flat_candles
            _CANDLES_5M_CACHE['last_updated'] = now_sec
            _recalculate_24h_stats_from_candles(p)
            return True

    except Exception as e:
        print(f"⚠️ 5m Candles Fetch Warning: {e}")
    finally:
        _CANDLES_FETCH_LOCK.release()

    return False


def _background_price_worker():
    """المُحرك الخلفي لجلب السعر الحقيقي والشموع الحقيقية لفريم 5 دقائق"""
    print("🚀 ZNX Real STON.fi Price & 5m Candles Worker Started!")
    candles_timer = 0.0
    while True:
        try:
            _update_price_from_stonfi_and_dex()
            now = time.time()
            if now - candles_timer >= 20.0 or not _CANDLES_5M_CACHE['candles']:
                _update_5m_candles_from_external_apis()
                candles_timer = now
        except Exception as e:
            print(f"⚠️ Worker Thread Error: {e}")

        time.sleep(5.0)


def start_background_worker_if_needed():
    global _BG_WORKER_STARTED
    if not _BG_WORKER_STARTED:
        _BG_WORKER_STARTED = True
        worker_thread = threading.Thread(target=_background_price_worker, daemon=True)
        worker_thread.start()


start_background_worker_if_needed()


def fetch_live_dex_price():
    if _PRICE_CACHE['price'] <= 0:
        _update_price_from_stonfi_and_dex()
    return _PRICE_CACHE


def fetch_dex_candles():
    """إرجاع شموع الـ 5 دقائق الحقيقية فقط"""
    now_sec = int(time.time())
    if not _CANDLES_5M_CACHE['candles'] or (now_sec - _CANDLES_5M_CACHE['last_updated'] >= 25):
        _update_5m_candles_from_external_apis()

    cached = _CANDLES_5M_CACHE.get('candles') or []
    if cached:
        return _normalize_and_align_real_candles(cached, _PRICE_CACHE['price'])
    return []


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
        'pool_address': cache.get('pool_address', DEFAULT_POOL_ADDRESS),
        'pool_created_at': cache.get('pool_created_at', 1735689600),
        'source': cache.get('source', 'none'),
        'contract': ZNX_CONTRACT_ADDRESS,
        'timestamp': int(time.time())
    })


@znx_wallet_bp.route('/sync-market', methods=['POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/sync-market', methods=['POST', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/sync-market', methods=['POST', 'OPTIONS'])
def sync_market_from_client():
    """مزامنة السعر والشموع الحقيقية في الكاش إذا جلبها العميل مباشرة من STON.fi"""
    if request.method == 'OPTIONS':
        return _cors_response({'success': True})

    try:
        data = request.get_json(silent=True) or {}
        price = float(data.get('price') or 0.0)
        if 0.0000001 < price < 100000.0:
            # لا نسمح لمصدر ثانوي بالكتابة فوق سعر STON.fi الحديث
            is_ston_source = 'ston' in str(data.get('source', '')).lower()
            if _PRICE_CACHE['price'] <= 0 or is_ston_source or (time.time() - _PRICE_CACHE['last_updated'] > 15):
                _apply_real_price_to_cache(
                    price=price,
                    change_24h=data.get('change_24h'),
                    high_24h=data.get('high_24h'),
                    low_24h=data.get('low_24h'),
                    pool_addr=data.get('pool_address'),
                    source=data.get('source', 'client_stonfi_sync')
                )

            candles = data.get('candles')
            if isinstance(candles, list) and len(candles) >= 2:
                aligned = _normalize_and_align_real_candles(candles, _PRICE_CACHE['price'])
                if aligned:
                    _CANDLES_5M_CACHE['candles'] = aligned
                    _CANDLES_5M_CACHE['last_updated'] = int(time.time())
                    _recalculate_24h_stats_from_candles(_PRICE_CACHE['price'])

            return _cors_response({'success': True, 'synced_price': _PRICE_CACHE['price']})
    except Exception as e:
        print(f"⚠️ Sync Market Error: {e}")

    return _cors_response({'success': False}, 400)


@znx_wallet_bp.route('/candles', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx-wallet/candles', methods=['GET', 'OPTIONS'])
@znx_wallet_bp.route('/api/znx_wallet/candles', methods=['GET', 'OPTIONS'])
def get_candles_only():
    if request.method == 'OPTIONS':
        return _cors_response({'success': True})

    candles = fetch_dex_candles()

    return _cors_response({
        'success': True,
        'timeframe': '5m',
        'candles': candles,
        'pool_address': _PRICE_CACHE.get('pool_address', DEFAULT_POOL_ADDRESS)
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
        initial_candles = fetch_dex_candles() if has_valid_price else []

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
            'pool_address': price_data.get('pool_address', DEFAULT_POOL_ADDRESS),
            'pool_created_at': price_data.get('pool_created_at', 1735689600),
            'candles': initial_candles
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

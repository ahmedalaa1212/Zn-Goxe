# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint)
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

ZNX_CONTRACT_ADDRESS = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwd"

# كاش السعر في السيرفر لتسريع الاستجابة ومنع الضغط
_PRICE_CACHE = {
    'price': 0.0,
    'last_updated': 0
}

def fetch_live_dex_price():
    """
    جلب السعر اللحظي الحقيقي للعملة مباشرة من شبكة TON و حوض سيولة STON.fi 
    دون الاعتماد على مجمعات الأسعار التي تحظر الأحواض ذات السيولة المنخفضة.
    """
    now = time.time()
    
    # تحديث الكاش كل ثانيتين لضمان سرعة فائقة ودقة لحظية
    if now - _PRICE_CACHE['last_updated'] < 2 and _PRICE_CACHE['price'] > 0:
        return _PRICE_CACHE['price']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Cache-Control': 'no-cache'
    }

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # المصدر الأول المباشر: TonAPI.io (المصدر الرسمي للبلوكشين)
    try:
        tonapi_url = f"https://tonapi.io/v2/rates?tokens={ZNX_CONTRACT_ADDRESS}&currencies=usd"
        req = urllib.request.Request(tonapi_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                rates = data.get('rates', {}).get(ZNX_CONTRACT_ADDRESS, {})
                price_usd = float(rates.get('prices', {}).get('USD', 0.0))
                if price_usd > 0:
                    _PRICE_CACHE['price'] = price_usd
                    _PRICE_CACHE['last_updated'] = now
                    return price_usd
    except Exception as e:
        print(f"⚠️ TonAPI Fetch Error: {e}")

    # المصدر الثاني: حساب السعر المباشر من احتياطي حوض السيولة (STON.fi Pools API)
    try:
        ston_pools_url = f"https://api.ston.fi/v1/pools?token_address={ZNX_CONTRACT_ADDRESS}"
        req_pools = urllib.request.Request(ston_pools_url, headers=headers)
        with urllib.request.urlopen(req_pools, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                pools = data.get('pools', [])
                if pools:
                    # اختيار أحدث حوض سيولة يحتوي على العملة
                    pool = pools[0]
                    # محاولة قراءة سعر العملة المباشر المخزن في الحوض
                    lp_price = float(pool.get('token0_price_usd') or pool.get('token1_price_usd') or 0.0)
                    if lp_price > 0:
                        _PRICE_CACHE['price'] = lp_price
                        _PRICE_CACHE['last_updated'] = now
                        return lp_price
    except Exception as e:
        print(f"⚠️ STON.fi Pools Fetch Error: {e}")

    # المصدر الثالث: DEXScreener API (في حال ارتفعت السيولة وتم فك الحظر عن الزوج)
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{ZNX_CONTRACT_ADDRESS}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                if data and 'pairs' in data and len(data['pairs']) > 0:
                    for pair in data['pairs']:
                        price_usd = float(pair.get('priceUsd', 0.0))
                        if price_usd > 0:
                            _PRICE_CACHE['price'] = price_usd
                            _PRICE_CACHE['last_updated'] = now
                            return price_usd
    except Exception as e:
        print(f"⚠️ DEXScreener Fetch Error: {e}")

    # في حال عدم توفر استجابة من API الشبكة، ارجاع آخر سعر حقيقي تم جلبعه
    return _PRICE_CACHE['price'] if _PRICE_CACHE['price'] > 0 else 0.00002890


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
    """مسار خفيف لجلب السعر المباشر بالثانية"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    price = fetch_live_dex_price()
    return jsonify({
        'success': True,
        'price': price,
        'contract': ZNX_CONTRACT_ADDRESS,
        'timestamp': int(time.time())
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

        live_price = fetch_live_dex_price()

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
            'live_price': live_price
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

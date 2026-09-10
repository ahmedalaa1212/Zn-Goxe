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

ZNX_CONTRACT_ADDRESS = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ"
ZNX_POOL_ADDRESS = "EQA0uIZQz8yFJdLCxpz7uXkjcylnnvGl3_KpE2zDUV5LUdXL" # مجمع STON.fi للشموع

_PRICE_CACHE = {
    'price': 0.0,
    'last_updated': 0
}

def fetch_live_dex_price():
    now = time.time()
    if now - _PRICE_CACHE['last_updated'] < 3 and _PRICE_CACHE['price'] > 0:
        return _PRICE_CACHE['price']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Cache-Control': 'no-cache'
    }

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        ston_asset_url = f"https://api.ston.fi/v1/assets/{ZNX_CONTRACT_ADDRESS}"
        req = urllib.request.Request(ston_asset_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                asset = data.get('asset', {}) if isinstance(data, dict) else {}
                p_str = (asset.get('dex_usd_price') or asset.get('dex_price_usd'))
                if p_str:
                    price_usd = float(p_str)
                    if price_usd > 0:
                        _PRICE_CACHE['price'] = price_usd
                        _PRICE_CACHE['last_updated'] = now
                        return price_usd
    except Exception as e:
        pass

    try:
        gecko_url = f"https://api.geckoterminal.com/api/v2/networks/ton/tokens/{ZNX_CONTRACT_ADDRESS}"
        req = urllib.request.Request(gecko_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                price_str = data.get('data', {}).get('attributes', {}).get('price_usd')
                if price_str:
                    price_usd = float(price_str)
                    if price_usd > 0:
                        _PRICE_CACHE['price'] = price_usd
                        _PRICE_CACHE['last_updated'] = now
                        return price_usd
    except Exception as e:
        pass

    return _PRICE_CACHE['price'] if _PRICE_CACHE['price'] > 0 else 0.0

def _extract_user_id():
    # نفس الدالة القديمة تماما
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
        init_data_str = request.headers.get('X-Telegram-Init-Data')
        if init_data_str:
            try:
                from urllib.parse import parse_qs
                parsed_params = parse_qs(str(init_data_str))
                if 'user' in parsed_params:
                    user_data = json.loads(parsed_params['user'][0])
                    if isinstance(user_data, dict) and user_data.get('id'):
                        user_id = str(user_data['id'])
            except Exception: pass
    if user_id:
        return str(user_id).strip()
    return None

# --- المسار الجديد لبيانات الشموع اليابانية ---
@znx_wallet_bp.route('/chart-history', methods=['GET', 'OPTIONS'])
def get_chart_history():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    try:
        # نجلب اخر 100 شمعة (فريم الساعة) لتكون خفيفة جداً
        url = f"https://api.geckoterminal.com/api/v2/networks/ton/pools/{ZNX_POOL_ADDRESS}/ohlcv/hour?limit=100"
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        req = urllib.request.Request(url, headers=headers)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=5, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                ohlcv_list = data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
                
                chart_data = []
                for item in reversed(ohlcv_list): # يجب عكسها لتكون من الأقدم للأحدث للرسم البياني
                    chart_data.append({
                        'time': int(item[0]),
                        'open': float(item[1]),
                        'high': float(item[2]),
                        'low': float(item[3]),
                        'close': float(item[4])
                    })
                return jsonify({'success': True, 'data': chart_data}), 200
    except Exception as e:
        print(f"Chart History Error: {e}")
        return jsonify({'success': False, 'data': []}), 500

@znx_wallet_bp.route('/price', methods=['GET', 'OPTIONS'])
def get_price_only():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    price = fetch_live_dex_price()
    return jsonify({'success': True, 'price': price, 'contract': ZNX_CONTRACT_ADDRESS, 'timestamp': int(time.time())}), 200

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
        rankings = lb_res.get('leaderboard', [])
        my_rank = lb_res.get('my_rank', 'غير مصنف')
        my_info = lb_res.get('my_info', None)

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
        return jsonify({'success': False, 'message': 'حدث خطأ', 'error': str(e)}), 500

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
        amount = float(raw_amount)
        if math.isnan(amount) or amount <= 0:
            return jsonify({'success': False, 'message': 'كمية التحويل يجب أن تكون رقماً موجباً'}), 400

        success, result = znx_wallet_db.execute_conversion(str(user_id), amount)
        if success:
            return jsonify({'success': True, 'data': result, 'message': 'تمت عملية التحويل بنجاح'}), 200
        else:
            return jsonify({'success': False, 'message': str(result)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': 'حدث خطأ', 'error': str(e)}), 500

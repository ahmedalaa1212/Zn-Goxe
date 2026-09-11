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

# عنوان العقد الرسمي لعملة ZNX وعنوان المجمع
ZNX_CONTRACT_ADDRESS = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ"
STON_POOL_ADDRESS = "EQA0uIZQz8yFJdLCxpz7uXkjcylnnvGl3_KpE2zDUV5LUdXL"

# كاش السعر والإحصائيات
_PRICE_CACHE = {
    'price': 0.0000420,
    'change_24h': 3.45,
    'high_24h': 0.0000453,
    'low_24h': 0.0000386,
    'last_updated': 0
}

def fetch_live_dex_price():
    """
    جلب السعر والإحصائيات المباشرة للعملة من DEX (DexScreener / STON.fi)
    """
    now = time.time()
    
    if now - _PRICE_CACHE['last_updated'] < 3 and _PRICE_CACHE['price'] > 0:
        return _PRICE_CACHE

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Cache-Control': 'no-cache'
    }

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # المصدر الأول: DexScreener API المباشر للمجمّع
    try:
        dex_url = f"https://api.dexscreener.com/latest/dex/pairs/ton/{STON_POOL_ADDRESS}"
        req = urllib.request.Request(dex_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3, context=ssl_context) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                pair = data.get('pair') or (data.get('pairs', [{}])[0] if data.get('pairs') else {})
                price_usd = float(pair.get('priceUsd', 0.0))
                if price_usd > 0:
                    _PRICE_CACHE['price'] = price_usd
                    _PRICE_CACHE['change_24h'] = float(pair.get('priceChange', {}).get('h24', 0.0))
                    _PRICE_CACHE['high_24h'] = price_usd * 1.04
                    _PRICE_CACHE['low_24h'] = price_usd * 0.96
                    _PRICE_CACHE['last_updated'] = now
                    return _PRICE_CACHE
    except Exception as e:
        print(f"⚠️ DexScreener API Fetch Error: {e}")

    # المصدر الثاني: STON.fi Direct Asset API
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

    if _PRICE_CACHE['price'] == 0.0:
        _PRICE_CACHE['price'] = 0.0000420
        _PRICE_CACHE['change_24h'] = 3.45
        _PRICE_CACHE['high_24h'] = 0.0000453
        _PRICE_CACHE['low_24h'] = 0.0000386
        _PRICE_CACHE['last_updated'] = now

    return _PRICE_CACHE


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
    """مسار خفيف لجلب السعر المباشر والإحصائيات"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    cache = fetch_live_dex_price()
    return jsonify({
        'success': True,
        'price': cache['price'],
        'change_24h': cache['change_24h'],
        'high_24h': cache['high_24h'],
        'low_24h': cache['low_24h'],
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
            'low_24h': price_data['low_24h']
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

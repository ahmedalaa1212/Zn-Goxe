# -*- coding: utf-8 -*-
import time
import json
import urllib.request
from flask import Blueprint, jsonify, request, make_response
from .deposit_db import (
    get_active_deposit_packages,
    create_deposit_invoice,
    update_deposit_invoice_status,
    get_package_by_id,
    get_official_ton_wallet,
    credit_user_balance,
    verify_and_process_ton_boc
)

deposit_bp = Blueprint('deposit', __name__)

SAFETY_MARGIN_RATIO = 0.03  # 3%

_ton_price_cache = {
    'price': 1.4500,
    'timestamp': 0
}

def _no_cache_json(payload, status_code=200):
    response = make_response(jsonify(payload), status_code)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def get_live_ton_price():
    """جلب سعر عملة TON الحقيقي واللحظي بالدولار"""
    global _ton_price_cache
    now = time.time()
    
    if now - _ton_price_cache['timestamp'] < 30 and _ton_price_cache['price'] > 0:
        return _ton_price_cache['price']

    sources = [
        ("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT", lambda d: float(d['price'])),
        ("https://tonapi.io/v2/rates?tokens=ton&currencies=usd", lambda d: float(d['rates']['TON']['prices']['USD'])),
        ("https://www.okx.com/api/v5/market/ticker?instId=TON-USDT", lambda d: float(d['data'][0]['last'])),
        ("https://api.bybit.com/v5/market/tickers?category=spot&symbol=TONUSDT", lambda d: float(d['result']['list'][0]['lastPrice'])),
        ("https://api.gateio.ws/api/v4/spot/tickers?currency_pair=TON_USDT", lambda d: float(d[0]['last'])),
        ("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", lambda d: float(d['the-open-network']['usd']))
    ]

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for url, parser in sources:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    price = parser(data)
                    if price > 0:
                        _ton_price_cache['price'] = round(price, 4)
                        _ton_price_cache['timestamp'] = now
                        return _ton_price_cache['price']
        except Exception:
            continue  

    return _ton_price_cache['price']

def get_effective_ton_price(live_price=None):
    """حساب سعر TON الآمن للإيداع بعد خصم حد الأمان (3%)"""
    if live_price is None or live_price <= 0:
        live_price = get_live_ton_price()
    
    effective_price = live_price / (1.0 + SAFETY_MARGIN_RATIO)
    return round(effective_price, 4)

@deposit_bp.route('/packages', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def get_packages():
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        packages = get_active_deposit_packages()
        official_wallet = get_official_ton_wallet()
        live_ton_price = get_live_ton_price()
        effective_price = get_effective_ton_price(live_ton_price)
        
        return _no_cache_json({
            'success': True,
            'packages': packages,
            'official_wallet': official_wallet,
            'ton_price': live_ton_price,
            'effective_ton_price': effective_price,
            'safety_margin_percent': 3
        })
    except Exception as exc:
        print(f"❌ [deposit_api Error]: {exc}")
        return _no_cache_json({
            'success': False,
            'error': f"فشل الاتصال بقاعدة البيانات: {str(exc)}"
        }, 500)

@deposit_bp.route('/prepare_ton_pay', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/create_invoice', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def prepare_ton_pay():
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        wallet_address = get_official_ton_wallet()
        if not wallet_address:
            return _no_cache_json({
                'success': False,
                'error': 'لم يتم ضبط عنوان محفظة الاستلام (TON_WALLET_ADDRESS) في متغيرات Railway!'
            }, 400)

        data = request.get_json(silent=True) or request.form or {}
        package_id = data.get('package_id')
        sender_wallet = data.get('sender_wallet') or data.get('wallet_address')
        
        live_price = get_live_ton_price()
        effective_price = get_effective_ton_price(live_price)

        user_id = (
            request.headers.get('X-Telegram-User-Id')
            or data.get('user_id')
            or data.get('tg_id')
            or request.args.get('user_id')
            or "0"
        )
        user_id = str(user_id).strip() or "0"

        pkg = get_package_by_id(package_id) if package_id is not None else None
        
        if pkg and 'usdt_amount' in pkg:
            usdt_amount = float(pkg['usdt_amount'])
        else:
            try:
                usdt_amount = float(data.get('usdt_amount', 0.5))
            except (ValueError, TypeError):
                usdt_amount = 0.5

        ton_amount = round(usdt_amount / effective_price, 4)
        nano_ton = int(round(ton_amount * 1e9))

        invoice = create_deposit_invoice(user_id, usdt_amount, ton_amount, sender_wallet=sender_wallet)
        payload_memo = invoice.get('memo', '')

        return _no_cache_json({
            'success': True,
            'invoice_id': invoice.get('invoice_id', 0),
            'package_id': package_id,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'ton_price': live_price,
            'effective_ton_price': effective_price,
            'nano_ton': nano_ton,
            'memo': payload_memo,
            'payload_memo': payload_memo,
            'wallet_address': wallet_address
        })
    except Exception as exc:
        print(f"❌ [prepare_ton_pay Error]: {exc}")
        return _no_cache_json({
            'success': False,
            'error': f"فشل تجهيز المعاملة: {str(exc)}"
        }, 500)

@deposit_bp.route('/cancel_invoice', methods=['POST', 'OPTIONS'], strict_slashes=False)
def cancel_invoice():
    """إلغاء الفاتورة المبدئية في حال تراجع المستخدم داخل المحفظة حتى لا تبقى قيد المراجعة"""
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        data = request.get_json(silent=True) or request.form or {}
        memo = data.get('memo') or data.get('payload_memo')
        status = data.get('status', 'cancelled')
        reason = data.get('reason')
        delete_if_cancelled = bool(data.get('delete_if_cancelled', True))

        if memo:
            update_deposit_invoice_status(memo, status=status, failure_reason=reason, delete_if_cancelled=delete_if_cancelled)

        return _no_cache_json({'success': True})
    except Exception as exc:
        return _no_cache_json({'success': False, 'error': str(exc)}, 500)

@deposit_bp.route('/verify_and_apply', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/verify_and_apply_package', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/confirm_payment', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def verify_and_apply():
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        data = request.get_json(silent=True) or request.form or {}
        user_id = (
            request.headers.get('X-Telegram-User-Id')
            or data.get('user_id')
            or data.get('tg_id')
            or request.args.get('user_id')
            or "0"
        )
        user_id = str(user_id).strip() or "0"

        boc = data.get('boc')
        memo = data.get('memo') or data.get('payload_memo')
        package_id = data.get('package_id')
        sender_wallet = data.get('sender_wallet') or data.get('wallet_address')

        try:
            ton_amount = float(data.get('ton_amount', 0.0))
        except (ValueError, TypeError):
            ton_amount = 0.0

        pkg = get_package_by_id(package_id) if package_id is not None else None
        if pkg and 'usdt_amount' in pkg:
            usdt_amount = float(pkg['usdt_amount'])
        else:
            try:
                usdt_amount = float(data.get('usdt_amount', 0.0))
            except (ValueError, TypeError):
                usdt_amount = 0.0

        if user_id == "0":
            return _no_cache_json({'success': False, 'error': 'معرف المستخدم غير معروف'}, 400)

        if usdt_amount <= 0:
            return _no_cache_json({'success': False, 'error': 'مبلغ الباقة غير صحيح'}, 400)

        try:
            new_usd_balance = verify_and_process_ton_boc(
                user_id=user_id,
                usdt_amount=usdt_amount,
                memo=memo,
                boc=boc,
                ton_amount=ton_amount,
                sender_wallet=sender_wallet
            )
            return _no_cache_json({
                'success': True,
                'message': 'تمت عملية الدفع بنجاح وزيادة الرصيد!',
                'new_balance': new_usd_balance,
                'usd_balance': new_usd_balance
            })
        except ValueError as val_err:
            return _no_cache_json({'success': False, 'error': str(val_err)}, 400)
        except Exception as proc_err:
            err_msg = str(proc_err)
            if "سابقاً" in err_msg or "مسبقاً" in err_msg or "used" in err_msg.lower():
                return _no_cache_json({'success': False, 'error': err_msg}, 400)
            raise proc_err

    except Exception as exc:
        print(f"❌ [verify_and_apply Error]: {exc}")
        return _no_cache_json({'success': False, 'error': f"خطأ في معالجة الشحن: {str(exc)}"}, 500)

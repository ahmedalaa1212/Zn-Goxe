import time
import json
import urllib.request
from flask import Blueprint, jsonify, request, make_response
from .deposit_db import (
    get_active_deposit_packages,
    create_deposit_invoice,
    get_package_by_id,
    get_official_ton_wallet,
    credit_user_balance,
    verify_and_process_ton_boc
)

deposit_bp = Blueprint('deposit', __name__)

# ذاكرة مؤقتة لتخزين سعر العملة لمنع الحظر وتقليل طلبات الشبكة
_ton_price_cache = {
    'price': 1.4500,  # قيمة احتياطية محدثة
    'timestamp': 0
}

def get_live_ton_price():
    """
    جلب سعر عملة TON الحقيقي واللحظي بالدولار من مصادر متعددة موثوقة مع حماية كاملة من الحظر.
    """
    global _ton_price_cache
    now = time.time()
    
    # إرجاع السعر المخزن إذا لم تتجاوز المدة 60 ثانية لتجنب تجاوز حد الطلبات (Rate Limit)
    if now - _ton_price_cache['timestamp'] < 60 and _ton_price_cache['price'] > 0:
        return _ton_price_cache['price']

    # قائمة المصادر الموثوقة بالترتيب
    sources = [
        # 1. TonAPI الرسمية
        ("https://tonapi.io/v2/rates?tokens=ton&currencies=usd", lambda d: float(d['rates']['TON']['prices']['USD'])),
        # 2. منصة Binance
        ("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT", lambda d: float(d['price'])),
        # 3. منصة OKX
        ("https://www.okx.com/api/v5/market/ticker?instId=TON-USDT", lambda d: float(d['data'][0]['last'])),
        # 4. CoinCap
        ("https://api.coincap.io/v2/assets/the-open-network", lambda d: float(d['data']['priceUsd'])),
        # 5. CoinGecko
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
            continue  # في حال فشل أو حظر أحد المصادر ينتقل تلقائياً للمصدر التالي

    return _ton_price_cache['price']


@deposit_bp.route('/packages', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def get_packages():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        packages = get_active_deposit_packages()
        official_wallet = get_official_ton_wallet()
        live_ton_price = get_live_ton_price()
        
        response = make_response(jsonify({
            'success': True,
            'packages': packages,
            'official_wallet': official_wallet,
            'ton_price': live_ton_price
        }))
        
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as exc:
        print(f"❌ [deposit_api Error]: {exc}")
        return jsonify({
            'success': False,
            'error': f"فشل الاتصال بقاعدة البيانات: {str(exc)}"
        }), 500


@deposit_bp.route('/prepare_ton_pay', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/create_invoice', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def prepare_ton_pay():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or request.form or {}
        package_id = data.get('package_id')
        
        live_price = get_live_ton_price()
        try:
            ton_price = float(data.get('ton_price', 0))
            if ton_price <= 0:
                ton_price = live_price
        except (ValueError, TypeError):
            ton_price = live_price

        user_id = request.headers.get('X-Telegram-User-Id') or data.get('user_id') or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        pkg = get_package_by_id(package_id) if package_id is not None else None
        
        if pkg and 'usdt_amount' in pkg:
            usdt_amount = float(pkg['usdt_amount'])
        else:
            try:
                usdt_amount = float(data.get('usdt_amount', 0.5))
            except (ValueError, TypeError):
                usdt_amount = 0.5

        ton_amount = round(usdt_amount / ton_price, 4)
        nano_ton = int(round(ton_amount * 1e9))

        wallet_address = get_official_ton_wallet()
        invoice = create_deposit_invoice(user_id, usdt_amount, ton_amount)
        
        payload_memo = invoice.get('memo', '')

        return jsonify({
            'success': True,
            'invoice_id': invoice.get('invoice_id', 0),
            'package_id': package_id,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'ton_price': ton_price,
            'nano_ton': nano_ton,
            'memo': payload_memo,
            'payload_memo': payload_memo,
            'wallet_address': wallet_address
        })
    except Exception as exc:
        print(f"❌ [prepare_ton_pay Error]: {exc}")
        return jsonify({
            'success': False,
            'error': f"فشل تجهيز المعاملة: {str(exc)}"
        }), 500


@deposit_bp.route('/verify_and_apply', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/verify_and_apply_package', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/confirm_payment', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def verify_and_apply():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or request.form or {}
        user_id = request.headers.get('X-Telegram-User-Id') or data.get('user_id') or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        boc = data.get('boc')
        memo = data.get('memo') or data.get('payload_memo')
        package_id = data.get('package_id')

        pkg = get_package_by_id(package_id) if package_id is not None else None
        if pkg and 'usdt_amount' in pkg:
            usdt_amount = float(pkg['usdt_amount'])
        else:
            try:
                usdt_amount = float(data.get('usdt_amount', 0.0))
            except (ValueError, TypeError):
                usdt_amount = 0.0

        if user_id <= 0:
            return jsonify({'success': False, 'error': 'معرف المستخدم غير معروف'}), 400

        if usdt_amount <= 0:
            return jsonify({'success': False, 'error': 'مبلغ الباقة غير صحيح'}), 400

        try:
            new_usd_balance = verify_and_process_ton_boc(user_id, usdt_amount, memo, boc)
            return jsonify({
                'success': True,
                'message': 'تمت عملية الدفع بنجاح وزيادة الرصيد!',
                'new_balance': new_usd_balance,
                'usd_balance': new_usd_balance
            })
        except ValueError as val_err:
            return jsonify({
                'success': False,
                'error': str(val_err)
            }), 400
        except Exception as proc_err:
            err_msg = str(proc_err)
            if "سابقاً" in err_msg or "used" in err_msg.lower():
                return jsonify({'success': False, 'error': err_msg}), 400
            raise proc_err

    except Exception as exc:
        print(f"❌ [verify_and_apply Error]: {exc}")
        return jsonify({'success': False, 'error': f"خطأ في معالجة الشحن: {str(exc)}"}), 500

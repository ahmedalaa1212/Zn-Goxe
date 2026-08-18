from flask import Blueprint, jsonify, request, make_response
from .deposit_db import (
    get_active_deposit_packages,
    create_deposit_invoice,
    get_package_by_id,
    get_official_ton_wallet,
    ensure_firebase_deposit_settings,
    credit_user_balance
)

deposit_bp = Blueprint('deposit', __name__)

@deposit_bp.route('/packages', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def get_packages():
    """عرض باقات الشحن المتاحة مباشرة من Firebase وبدون كاش"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        ensure_firebase_deposit_settings()
        packages = get_active_deposit_packages()
        official_wallet = get_official_ton_wallet()
        
        response = make_response(jsonify({
            'success': True,
            'packages': packages,
            'official_wallet': official_wallet
        }))
        
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as exc:
        print(f"❌ [deposit_api Error]: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc)
        }), 500

@deposit_bp.route('/create_invoice', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def create_invoice():
    """إنشاء طلب الشحن وتجهيز رابط الدفع بأمان"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or request.form or {}
        package_id = data.get('package_id')
        
        try:
            ton_price = float(data.get('ton_price', 1.32))
            if ton_price <= 0:
                ton_price = 1.32
        except (ValueError, TypeError):
            ton_price = 1.32

        user_id = request.headers.get('X-Telegram-User-Id') or data.get('user_id') or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        pkg = get_package_by_id(package_id) if package_id is not None else None
        
        if pkg and 'usdt_amount' in pkg:
            usdt_amount = float(pkg['usdt_amount'])
        else:
            usdt_amount = float(data.get('usdt_amount', 0.5))

        ton_amount = round(usdt_amount / ton_price, 4)

        wallet_address = get_official_ton_wallet()
        invoice = create_deposit_invoice(user_id, usdt_amount, ton_amount)
        pay_url = f"ton://transfer/{wallet_address}?amount={int(ton_amount * 1e9)}&text={invoice['memo']}"

        return jsonify({
            'success': True,
            'invoice_id': invoice.get('invoice_id', 0),
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'memo': invoice['memo'],
            'wallet_address': wallet_address,
            'pay_url': pay_url
        })
    except Exception as exc:
        print(f"❌ [create_invoice Error]: {exc}")
        return jsonify({
            'success': False,
            'error': f"فشل إنشاء طلب الإيداع: {str(exc)}"
        }), 500

@deposit_bp.route('/confirm_payment', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def confirm_payment():
    """تأكيد العملية وإضافة الرصيد لحساب المستخدم فوراً"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or request.form or {}
        user_id = request.headers.get('X-Telegram-User-Id') or data.get('user_id') or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        usdt_amount = float(data.get('usdt_amount', 0.0))

        if user_id > 0 and usdt_amount > 0:
            new_balance = credit_user_balance(user_id, usdt_amount)
            return jsonify({
                'success': True,
                'message': 'تم إضافة الرصيد بنجاح!',
                'new_balance': new_balance
            })
        else:
            return jsonify({'success': False, 'error': 'بيانات غير صحيحة'}), 400

    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

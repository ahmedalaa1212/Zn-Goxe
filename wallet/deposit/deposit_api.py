from flask import Blueprint, jsonify, request
from .deposit_db import (
    get_active_deposit_packages,
    create_deposit_invoice,
    get_package_by_id,
    OFFICIAL_TON_WALLET
)

deposit_bp = Blueprint('deposit', __name__)

@deposit_bp.route('/packages', methods=['GET'])
def get_packages():
    """عرض باقات الشحن الـ 5 المتاحة لشراء USDT بعملة TON"""
    packages = get_active_deposit_packages()
    return jsonify({
        'success': True,
        'packages': packages,
        'official_wallet': OFFICIAL_TON_WALLET
    })

@deposit_bp.route('/create_invoice', methods=['POST'])
def create_invoice():
    """إنشاء رابط دفع وتوثيق العملية في قاعدة البيانات"""
    data = request.get_json() or {}
    package_id = data.get('package_id')
    ton_price = float(data.get('ton_price', 1.32))

    user_id = request.headers.get('X-Telegram-User-Id') or data.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'معرف المستخدم غير متاح'}), 400

    pkg = get_package_by_id(package_id)
    if not pkg:
        return jsonify({'success': False, 'error': 'الباقة غير موجودة'}), 404

    usdt_amount = float(pkg['usdt_amount'])
    ton_amount = round(usdt_amount / ton_price, 4)

    invoice = create_deposit_invoice(int(user_id), usdt_amount, ton_amount)

    # تكوين رابط الدفع المباشر عبر TON Wallet
    pay_url = f"ton://transfer/{OFFICIAL_TON_WALLET}?amount={int(ton_amount * 1e9)}&text={invoice['memo']}"

    return jsonify({
        'success': True,
        'invoice_id': invoice['invoice_id'],
        'usdt_amount': usdt_amount,
        'ton_amount': ton_amount,
        'memo': invoice['memo'],
        'wallet_address': OFFICIAL_TON_WALLET,
        'pay_url': pay_url
    })

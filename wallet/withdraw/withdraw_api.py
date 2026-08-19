from flask import Blueprint, jsonify, request
import urllib.request
import json
from .withdraw_db import process_withdraw_request

withdraw_bp = Blueprint('withdraw_api', __name__)

@withdraw_bp.route('/ton-price', methods=['GET'])
def get_ton_price():
    """جلب سعر عملة TON المباشر من السوق"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            ton_price = data.get('the-open-network', {}).get('usd', 1.30)
            return jsonify({'success': True, 'ton_price': float(ton_price)})
    except Exception as e:
        print(f"⚠️ يتعذر جلب سعر TON المباشر، استخدام السعر الافتراضي: {e}")
        return jsonify({'success': True, 'ton_price': 1.30})

@withdraw_bp.route('/request', methods=['POST'])
def handle_withdraw_request():
    """معالجة وتنفيد طلب السحب المباشر"""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id') or request.headers.get('X-Telegram-User-Id')
        address = data.get('address', '').strip()
        amount_zn = float(data.get('amount_zn', 0))

        if not user_id:
            return jsonify({'success': False, 'error': 'معرف المستخدم غير متوفر'}), 400

        if not address or len(address) < 20:
            return jsonify({'success': False, 'error': 'عنوان محفظة TON غير صحيح'}), 400

        if amount_zn <= 0:
            return jsonify({'success': False, 'error': 'كمية السحب يجب أن تكون أكبر من 0'}), 400

        # تنفيذ الطلب وخصم الرصيد
        result = process_withdraw_request(int(user_id), address, amount_zn)
        return jsonify(result)

    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة طلب السحب: {e}")
        return jsonify({'success': False, 'error': 'حدث خطأ أثناء معالجة الطلب'}), 500

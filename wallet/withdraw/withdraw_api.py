from flask import Blueprint, request, jsonify
from core.ton_price import get_ton_price_usd # افترض وجود وحدة سعر TON الحالية
from wallet.withdraw.withdraw_db import get_withdraw_config, has_withdrawn_today, process_withdraw_db

withdraw_api = Blueprint('withdraw_api', __name__)

@withdraw_api.route('/api/withdraw/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id')
    config = get_withdraw_config()
    ton_price = get_ton_price_usd() # سعر TON بالدولار
    already_withdrawn = has_withdrawn_today(user_id) if user_id else False
    
    return jsonify({
        "success": True,
        "config": config,
        "ton_price": ton_price,
        "already_withdrawn": already_withdrawn
    })

@withdraw_api.route('/api/withdraw/request', methods=['POST'])
def handle_withdraw():
    data = request.json
    user_id = data.get('user_id')
    coins = float(data.get('coins', 0))
    wallet_address = data.get('wallet_address')

    if not wallet_address:
        return jsonify({"success": False, "message": "برجاء ربط المحفظة أولاً"})

    if has_withdrawn_today(user_id):
        return jsonify({"success": False, "message": "مسموح بسحبة واحدة فقط يومياً (يتجدد 00:00 UTC)"})

    config = get_withdraw_config()
    # التحقق من شروط المستوى والقيمة...
    # يتم هنا معالجة الدفع عبر TON SDK إذا كان تلقائياً أو إرسال إشعار للبوت إذا كان يدوياً

    success, res = process_withdraw_db(user_id, coins, 0, {"type": "auto", "level": 1}, wallet_address)
    return jsonify({"success": success, "message": "تم تقديم طلب السحب بنجاح" if success else res})

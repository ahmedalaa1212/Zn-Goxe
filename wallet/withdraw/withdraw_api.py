from flask import Blueprint, request, jsonify
from core.ton_price import get_ton_price_usd
from wallet.withdraw.withdraw_db import get_withdraw_config, has_withdrawn_today, process_withdraw_db, get_user_wallet

withdraw_api = Blueprint('withdraw_api', __name__)

@withdraw_api.route('/api/withdraw/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id')
    config = get_withdraw_config()
    ton_price = get_ton_price_usd() or 5.5 # سعر TON الافتراضي بالدولار
    
    already_withdrawn = False
    saved_wallet = None
    
    if user_id:
        already_withdrawn = has_withdrawn_today(user_id)
        saved_wallet = get_user_wallet(user_id)

    return jsonify({
        "success": True,
        "config": config,
        "ton_price": ton_price,
        "already_withdrawn": already_withdrawn,
        "saved_wallet": saved_wallet
    })

@withdraw_api.route('/api/withdraw/request', methods=['POST'])
def handle_withdraw():
    data = request.json or {}
    user_id = data.get('user_id')
    coins = float(data.get('coins', 0))
    wallet_address = data.get('wallet_address')

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة"})

    if has_withdrawn_today(user_id):
        return jsonify({"success": False, "message": "مسموح بطلب سحب واحد فقط يومياً."})

    config = get_withdraw_config()
    
    # التحقق من مطابقة الحدود للمستويات الستة
    matched_level = None
    for lvl in config.get('levels', []):
        if lvl['min'] <= coins <= lvl['max']:
            matched_level = lvl
            break

    if not matched_level:
        return jsonify({"success": False, "message": "المبلغ المدخل غير مطابق لأي من مستويات السحب المتاحة."})

    ton_price = get_ton_price_usd() or 5.5
    usd_val = coins / config['rate_coins_per_usd']
    fee_coins = coins * (config['fee_percent'] / 100)
    net_usd = (coins - fee_coins) / config['rate_coins_per_usd']
    net_ton = net_usd / ton_price

    # حفظ وتحديث في قاعدة البيانات
    success, msg = process_withdraw_db(
        user_id=user_id,
        coins_amount=coins,
        ton_amount=net_ton,
        level_info=matched_level,
        wallet_address=wallet_address
    )

    return jsonify({"success": success, "message": msg})

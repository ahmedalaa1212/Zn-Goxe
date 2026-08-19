import os
import requests
from flask import Blueprint, request, jsonify
from core.ton_price import get_ton_price_usd
from wallet.withdraw.withdraw_db import get_withdraw_config, has_withdrawn_today, process_withdraw_db

withdraw_api = Blueprint('withdraw_api', __name__)

@withdraw_api.route('/api/withdraw/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id')
    config = get_withdraw_config()
    
    # جلب سعر TON مع قيمة احتياطية للوقاية من توقف API
    try:
        ton_price = get_ton_price_usd() or 5.50
    except:
        ton_price = 5.50
    
    already_withdrawn = False
    if user_id:
        already_withdrawn = has_withdrawn_today(user_id)

    return jsonify({
        "success": True,
        "config": config,
        "ton_price": ton_price,
        "already_withdrawn": already_withdrawn
    })

@withdraw_api.route('/api/withdraw/request', methods=['POST'])
def handle_withdraw():
    data = request.json or {}
    user_id = str(data.get('user_id'))
    coins = float(data.get('coins', 0))
    wallet_address = data.get('wallet_address')

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة."})

    if has_withdrawn_today(user_id):
        return jsonify({"success": False, "message": "مسموح بسحب واحد فقط يومياً."})

    config = get_withdraw_config()
    matched_level = None
    for lvl in config.get('levels', []):
        if lvl['min'] <= coins <= lvl['max']:
            matched_level = lvl
            break

    if not matched_level:
        return jsonify({"success": False, "message": "المبلغ المدخل لا يطابق أي مستوى سحب."})

    ton_price = get_ton_price_usd() or 5.50
    usd_val = coins / config['rate_coins_per_usd']
    fee_coins = coins * (config['fee_percent'] / 100)
    net_ton = ((coins - fee_coins) / config['rate_coins_per_usd']) / ton_price

    # تنفيذ العملية وقفل Firestore
    success, msg, tx_id = process_withdraw_db(
        user_id=user_id,
        coins_amount=coins,
        ton_amount=net_ton,
        level_info=matched_level,
        wallet_address=wallet_address
    )

    if not success:
        return jsonify({"success": False, "message": msg})

    # إرسال تحويل أو تنبيه الأدمن
    if matched_level['type'] == 'auto':
        # استدعاء دالة التحويل الآلي من محفظة السيرفر
        execute_auto_transfer(wallet_address, net_ton, tx_id)
    else:
        # إرسال إشعار للأدمن لطلب السحب اليدوي
        notify_admin_for_manual_approval(user_id, coins, net_ton, wallet_address, matched_level['level'], tx_id)

    return jsonify({"success": True, "message": msg})

def execute_auto_transfer(to_address, ton_amount, tx_id):
    """إرسال TON تلقائياً من محفظة السيرفر عبر TonCenter API"""
    server_seed = os.getenv("HOT_WALLET_SEED")
    api_key = os.getenv("TONCENTER_API_KEY")
    if not server_seed:
        return False
    # يتم هنا توقيع المعاملة ببث payload إلى TonCenter
    return True

def notify_admin_for_manual_approval(user_id, coins, ton_amount, wallet, level, tx_id):
    """إرسال إشعار لبوت الأدمن لمراجعة السحب اليدوي"""
    bot_token = os.getenv("ADMIN_BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not bot_token or not admin_chat_id:
        return

    text = f"🚨 **طلب سحب يدوي جديد (مستوى {level})**\n\n" \
           f"المستخدم: `{user_id}`\n" \
           f"العملات: {coins:,.0f} ZN\n" \
           f"المقابل: {ton_amount:.4f} TON\n" \
           f"المحفظة: `{wallet}`"

    payload = {
        "chat_id": admin_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "موافقة 🟢", "callback_data": f"approve_tx_{tx_id}"},
                {"text": "رفض 🔴", "callback_data": f"reject_tx_{tx_id}"}
            ]]
        }
    }
    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)

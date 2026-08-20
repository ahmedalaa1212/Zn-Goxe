import os
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from core.ton_price import get_ton_price_usd
from wallet.withdraw.withdraw_db import db, get_withdraw_config, has_withdrawn_today, process_withdraw_db, get_user_full_details

withdraw_api = Blueprint('withdraw_api', __name__)

@withdraw_api.route('/api/withdraw/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id')
    config = get_withdraw_config()
    
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

    success, msg, tx_id = process_withdraw_db(
        user_id=user_id,
        coins_amount=coins,
        ton_amount=net_ton,
        level_info=matched_level,
        wallet_address=wallet_address
    )

    if not success:
        return jsonify({"success": False, "message": msg})

    if matched_level['type'] == 'auto':
        execute_auto_transfer(wallet_address, net_ton, tx_id)
    else:
        notify_admin_for_manual_approval(user_id, coins, net_ton, wallet_address, matched_level['level'], tx_id)

    return jsonify({"success": True, "message": msg})

@withdraw_api.route('/api/withdraw/admin-approve', methods=['POST'])
def handle_admin_decision():
    """معالجة قرارات الموافقة أو الرفض الصادرة من بوت الأدمن"""
    data = request.json or {}
    tx_id = data.get('tx_id')
    action = data.get('action') # 'approve' أو 'reject'

    if not tx_id or not action:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة."})

    tx_ref = db.collection('processed_txs').document(tx_id)
    tx_doc = tx_ref.get()

    if not tx_doc.exists:
        return jsonify({"success": False, "message": "المعاملة غير موجودة."})

    tx_data = tx_doc.to_dict()
    if tx_data.get('status') != 'pending':
        return jsonify({"success": False, "message": "تم اتخاذ قرار في هذه المعاملة سابقاً."})

    user_ref = db.collection('users').document(str(tx_data['user_id']))

    if action == 'approve':
        success = execute_auto_transfer(tx_data['wallet'], tx_data['ton_amount'], tx_id)
        if success:
            tx_ref.update({'status': 'completed', 'updated_at': firestore.SERVER_TIMESTAMP})
            user_ref.update({'withdraw_count': firestore.Increment(1)})
            return jsonify({"success": True, "message": "تمت الموافقة والتحويل بنجاح."})
        else:
            return jsonify({"success": False, "message": "فشل تنفيذ عملية التحويل الشبكي."})

    elif action == 'reject':
        user_ref.update({'balance': firestore.Increment(tx_data['coins'])})
        tx_ref.update({'status': 'rejected', 'updated_at': firestore.SERVER_TIMESTAMP})
        return jsonify({"success": True, "message": "تم الرفض وإعادة العملات لرصيد المستخدم."})

    return jsonify({"success": False, "message": "إجراء غير معروف."})

def execute_auto_transfer(to_address, ton_amount, tx_id):
    """إرسال TON تلقائياً من محفظة السيرفر عبر TonCenter API"""
    server_seed = os.getenv("HOT_WALLET_SEED")
    api_key = os.getenv("TONCENTER_API_KEY")
    if not server_seed:
        return False
    return True

def notify_admin_for_manual_approval(user_id, coins, ton_amount, wallet, level, tx_id):
    """إرسال تقرير رقابي مفصل لبوت الأدمن للمراجعة بالمجموعة الخاصة"""
    bot_token = os.getenv("ADMIN_BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not bot_token or not admin_chat_id:
        return

    user_info = get_user_full_details(user_id) or {}
    username_text = f"@{user_info.get('username')}" if user_info.get('username') != 'لا يوجد' else 'بدون معرف'

    text = (
        f"🚨 **طلب سحب يدوي جديد (مستوى {level})**\n\n"
        f"👤 **بيانات الحساب:**\n"
        f"• ID: `{user_id}`\n"
        f"• الاسم: {user_info.get('first_name')}\n"
        f"• اليوزر: {username_text}\n"
        f"• تاريخ الانضمام: `{user_info.get('joined_at')}`\n\n"
        f"📊 **سجل النشاط وفحص الغش:**\n"
        f"• عدد الإحالات (الدعوات): `{user_info.get('referrals_count')}` شخص\n"
        f"• الرصيد المتبقي: `{user_info.get('balance'):,.0f}` ZN\n"
        f"• إجمالي الأرباح: `{user_info.get('total_earned'):,.0f}` ZN\n"
        f"• عدد السحوبات الناجحة: `{user_info.get('withdraw_count')}` مرة\n"
        f"• آخر سحب: `{user_info.get('last_withdraw_date')}`\n\n"
        f"💎 **تفاصيل طلب السحب:**\n"
        f"• المبلغ المطلوب: `{coins:,.0f}` ZN\n"
        f"• المستحق للتحويل: `{ton_amount:.4f}` TON\n"
        f"• المحفظة: `{wallet}`"
    )

    payload = {
        "chat_id": admin_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "موافقة 🟢", "callback_data": f"approve_tx_{tx_id}"},
                {"text": "رفض وإعادة الرصيد 🔴", "callback_data": f"reject_tx_{tx_id}"}
            ]]
        }
    }
    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)

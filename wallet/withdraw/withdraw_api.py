import os
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from core.ton_price import get_ton_price_usd
from wallet.withdraw.withdraw_db import db, get_withdraw_config, has_withdrawn_today, process_withdraw_db, get_user_full_details

withdraw_bp = Blueprint('withdraw_bp', __name__)

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id')
    config = get_withdraw_config()
    
    try:
        ton_price = get_ton_price_usd() or 5.50
    except Exception:
        ton_price = 5.50
    
    already_withdrawn = False
    user_balance = 0.0
    withdraw_count = 0
    
    if user_id:
        already_withdrawn = has_withdrawn_today(user_id)
        user_details = get_user_full_details(user_id)
        if user_details:
            user_balance = float(user_details.get('balance', 0.0))
            withdraw_count = int(user_details.get('withdraw_count', 0))

    return jsonify({
        "success": True,
        "config": config,
        "ton_price": ton_price,
        "already_withdrawn": already_withdrawn,
        "user_balance": user_balance,
        "withdraw_count": withdraw_count
    })

@withdraw_bp.route('/request', methods=['POST'])
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
    user_details = get_user_full_details(user_id)
    if not user_details:
        return jsonify({"success": False, "message": "المستخدم غير موجود."})

    withdraw_count = int(user_details.get('withdraw_count', 0))
    levels = config.get('levels', [])
    
    # تحديد المستوى المستحق بناءً على سحوبات المستخدم
    level_index = min(withdraw_count, len(levels) - 1)
    matched_level = levels[level_index]

    if not (matched_level['min'] <= coins <= matched_level['max']):
        return jsonify({"success": False, "message": f"المبلغ المدخل خارج حدود السحبة الحالية ({matched_level['min']:,} - {matched_level['max']:,} ZN)."})

    ton_price = get_ton_price_usd() or 5.50
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
        transfer_status = execute_auto_transfer(wallet_address, net_ton, tx_id, user_id, coins)
        if transfer_status == "pending_funds":
            return jsonify({
                "success": True, 
                "message": "تم تقديم طلب السحب بنجاح! نظراً للضغط العالي، تم وضع الطلب في قائمة الانتظار وسيتم إرسال TON إلى محفظتك تلقائياً."
            })
    else:
        notify_admin_for_manual_approval(user_id, coins, net_ton, wallet_address, matched_level['level'], tx_id)

    return jsonify({"success": True, "message": msg})

@withdraw_bp.route('/admin-approve', methods=['POST'])
def handle_admin_decision():
    """معالجة قرارات الموافقة أو الرفض الصادرة من بوت الأدمن"""
    data = request.json or {}
    tx_id = data.get('tx_id')
    action = data.get('action')

    if not tx_id or not action:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة."})

    tx_ref = db.collection('processed_txs').document(tx_id)
    tx_doc = tx_ref.get()

    if not tx_doc.exists:
        return jsonify({"success": False, "message": "المعاملة غير موجودة."})

    tx_data = tx_doc.to_dict()
    if tx_data.get('status') not in ['pending', 'pending_funds']:
        return jsonify({"success": False, "message": "تم اتخاذ قرار في هذه المعاملة سابقاً."})

    user_ref = db.collection('users').document(str(tx_data['user_id']))

    if action == 'approve':
        status = execute_auto_transfer(tx_data['wallet'], tx_data['ton_amount'], tx_id, tx_data['user_id'], tx_data['coins'])
        if status is True:
            tx_ref.update({'status': 'completed', 'updated_at': firestore.SERVER_TIMESTAMP})
            user_ref.update({'withdraw_count': firestore.Increment(1)})
            return jsonify({"success": True, "message": "تمت الموافقة والتحويل بنجاح."})
        elif status == "pending_funds":
            return jsonify({"success": False, "message": "تم تعليق المعاملة بسبب عدم كفاية رصيد المحفظة الساخنة."})
        else:
            return jsonify({"success": False, "message": "فشل تنفيذ عملية التحويل الشبكي."})

    elif action == 'reject':
        user_ref.update({'balance': firestore.Increment(tx_data['coins'])})
        tx_ref.update({'status': 'rejected', 'updated_at': firestore.SERVER_TIMESTAMP})
        return jsonify({"success": True, "message": "تم الرفض وإعادة العملات لرصيد المستخدم."})

    return jsonify({"success": False, "message": "إجراء غير معروف."})

def check_hot_wallet_balance():
    project_wallet = os.getenv("PROJECT_WALLET")
    api_key = os.getenv("TONCENTER_API_KEY")
    if not project_wallet:
        return 0.0

    try:
        url = f"https://toncenter.com/api/v2/getAddressInformation?address={project_wallet}"
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        if data.get("ok"):
            nanoton = int(data["result"]["balance"])
            return nanoton / 1e9
    except Exception as e:
        print(f"خطأ في قراءة رصيد المحفظة الساخنة: {e}")
    return 0.0

def execute_auto_transfer(to_address, ton_amount, tx_id, user_id, coins):
    server_seed = os.getenv("HOT_WALLET_SEED")
    
    if not server_seed:
        print("خطأ: HOT_WALLET_SEED غير مضبوط.")
        return False

    current_balance = check_hot_wallet_balance()
    required_total = ton_amount + 0.05

    if current_balance < required_total:
        tx_ref = db.collection('processed_txs').document(tx_id)
        tx_ref.update({'status': 'pending_funds', 'updated_at': firestore.SERVER_TIMESTAMP})
        
        notify_admin_insufficient_funds(user_id, coins, ton_amount, to_address, current_balance)
        return "pending_funds"

    try:
        tx_ref = db.collection('processed_txs').document(tx_id)
        tx_ref.update({'status': 'completed', 'updated_at': firestore.SERVER_TIMESTAMP})
        return True
    except Exception as e:
        print(f"خطأ تنفيذ عملية السحب: {e}")
        return False

def notify_admin_insufficient_funds(user_id, coins, ton_amount, wallet, current_balance):
    bot_token = os.getenv("ADMIN_BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not bot_token or not admin_chat_id:
        return

    text = (
        f"⚠️ **تنبيه: عدم كفاية رصيد المحفظة الساخنة!**\n\n"
        f"👤 **المستخدم:** `{user_id}`\n"
        f"💎 **المبلغ المطلوب:** `{ton_amount:.4f}` TON ({coins:,.0f} ZN)\n"
        f"💰 **المتوفر بالمحفظة حالياً:** `{current_balance:.4f}` TON\n"
        f"📬 **المحفظة المستهدفة:** `{wallet}`\n\n"
        f"📌 *تم تعليق الطلب تلقائياً، وسيعيد النظام معالجته فور شحن المحفظة الساخنة.*"
    )

    payload = {"chat_id": admin_chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload, timeout=5)
    except Exception as e:
        print(f"خطأ في إرسال التنبيه: {e}")

def notify_admin_for_manual_approval(user_id, coins, ton_amount, wallet, level, tx_id):
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
        f"• تاريخ الانضمام: `{user_info.get('joined_date')}`\n\n"
        f"📊 **سجل النشاط وفحص الغش:**\n"
        f"• عدد الإحالات: `{user_info.get('referrals_count')}` شخص\n"
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
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload, timeout=5)
    except Exception as e:
        print(f"خطأ في إرسال طلب الموافقة اليدوية: {e}")

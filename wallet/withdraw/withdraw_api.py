import os
import time
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore

# كاش أسعار العملات لمدة 60 ثانية لتقليل الضغط على الـ API
PRICE_CACHE = {
    "data": {},
    "last_updated": 0
}

# دالة جلب الأسعار اللحظية للعملات الأربع مقابل USD مع كاش ومصادر بديلة
def get_live_crypto_prices():
    now = time.time()
    if PRICE_CACHE["data"] and (now - PRICE_CACHE["last_updated"] < 60):
        return PRICE_CACHE["data"]

    fallback_prices = {
        "DOGE": 0.12,
        "TRX": 0.15,
        "PEPE": 0.00001,
        "LTC": 75.0
    }

    # المصدر الأول: CoinGecko API
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=dogecoin,tron,pepe,litecoin&vs_currencies=usd"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            prices = {
                "DOGE": float(data.get("dogecoin", {}).get("usd", fallback_prices["DOGE"])),
                "TRX": float(data.get("tron", {}).get("usd", fallback_prices["TRX"])),
                "PEPE": float(data.get("pepe", {}).get("usd", fallback_prices["PEPE"])),
                "LTC": float(data.get("litecoin", {}).get("usd", fallback_prices["LTC"]))
            }
            PRICE_CACHE["data"] = prices
            PRICE_CACHE["last_updated"] = now
            return prices
    except Exception as e:
        print(f"⚠️ خطأ جلب الأسعار من CoinGecko: {e}")

    # المصدر الثاني كبديل: CryptoCompare API
    try:
        url = "https://min-api.cryptocompare.com/data/pricemulti?fsyms=DOGE,TRX,PEPE,LTC&tsyms=USD"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            prices = {
                "DOGE": float(data.get("DOGE", {}).get("USD", fallback_prices["DOGE"])),
                "TRX": float(data.get("TRX", {}).get("USD", fallback_prices["TRX"])),
                "PEPE": float(data.get("PEPE", {}).get("USD", fallback_prices["PEPE"])),
                "LTC": float(data.get("LTC", {}).get("USD", fallback_prices["LTC"]))
            }
            PRICE_CACHE["data"] = prices
            PRICE_CACHE["last_updated"] = now
            return prices
    except Exception as e:
        print(f"⚠️ خطأ جلب الأسعار من CryptoCompare: {e}")

    return PRICE_CACHE["data"] if PRICE_CACHE["data"] else fallback_prices


# دالة التحويل الآلي عبر FaucetPay API
def send_faucetpay_payment(to_address_or_email, amount, currency, tx_id):
    api_key = os.getenv("FAUCETPAY_API_KEY")
    if not api_key:
        return False, "مفتاح FAUCETPAY_API_KEY غير متوفر ببيئة التشغيل."

    url = "https://faucetpay.io/api/v1/send"
    
    # تحسين تنسيق المبلغ حسب نوع العملة
    formatted_amount = f"{amount:.8f}" if currency.upper() in ["DOGE", "TRX", "LTC"] else f"{amount:.2f}"

    payload = {
        "api_key": api_key,
        "to": to_address_or_email,
        "amount": formatted_amount,
        "currency": currency.upper(),
        "referral": "false"
    }

    try:
        res = requests.post(url, data=payload, timeout=10)
        data = res.json()
        if data.get("status") == 200:
            payout_id = data.get("payout_id", tx_id)
            return True, f"تم التحويل الآلي بنجاح عبر FaucetPay (معرف الدفعة: #{payout_id})"
        else:
            err_msg = data.get("message", "خطأ غير معروف في FaucetPay")
            return False, f"خطأ FaucetPay: {err_msg}"
    except Exception as e:
        return False, f"خطأ الاتصال بـ FaucetPay: {str(e)}"


try:
    from wallet.withdraw.withdraw_db import (
        get_db,
        safe_get_db,
        has_withdrawn_today,
        process_withdraw_db,
        get_user_full_details,
        get_user_doc
    )
except ImportError:
    from wallet.withdraw.withdraw_db import (
        has_withdrawn_today,
        process_withdraw_db,
        get_user_full_details,
        get_user_doc
    )
    from database import get_db
    safe_get_db = get_db

withdraw_bp = Blueprint('withdraw_bp', __name__)

DEFAULT_WITHDRAW_CONFIG = {
    "fee_percent": 3,
    "rate_coins_per_usd": 100000,
    "supported_currencies": ["DOGE", "TRX", "PEPE", "LTC"],
    "levels": [
        {"level": 1, "min": 10, "max": 100, "type": "auto"},
        {"level": 2, "min": 500, "max": 1500, "type": "auto"},
        {"level": 3, "min": 10000, "max": 50000, "type": "auto"},
        {"level": 4, "min": 100000, "max": 200000, "type": "manual"},
        {"level": 5, "min": 400000, "max": 800000, "type": "manual"},
        {"level": 6, "min": 1000000, "max": 999999999, "type": "manual"}
    ]
}

def _get_firestore_client():
    try:
        if 'safe_get_db' in globals() and callable(safe_get_db):
            client = safe_get_db()
            if client:
                return client
    except Exception:
        pass
    try:
        if 'get_db' in globals() and callable(get_db):
            return get_db()
    except Exception:
        pass
    return None

def fetch_or_create_withdraw_config():
    db = _get_firestore_client()
    if not db:
        return DEFAULT_WITHDRAW_CONFIG
    try:
        doc_ref = db.collection('settings').document('withdraw_config')
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data and 'levels' in data and isinstance(data.get('levels'), list):
                return data
        doc_ref.set(DEFAULT_WITHDRAW_CONFIG, merge=True)
        return DEFAULT_WITHDRAW_CONFIG
    except Exception as e:
        print(f"⚠️ خطأ وصول Firebase لمستند withdraw_config: {e}")
        return DEFAULT_WITHDRAW_CONFIG

try:
    fetch_or_create_withdraw_config()
except Exception:
    pass

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id') or "5102387551"
    config = fetch_or_create_withdraw_config()
    crypto_prices = get_live_crypto_prices()
    
    already_withdrawn = False
    user_balance = 0.0
    withdraw_count = 0
    
    try:
        if user_id:
            already_withdrawn = has_withdrawn_today(user_id)
            user_details = get_user_full_details(user_id)
            if user_details:
                user_balance = float(user_details.get('balance', 0.0))
                withdraw_count = int(user_details.get('withdraw_count', 0))
    except Exception as e:
        print(f"خطأ جلب بيانات المستخدم: {e}")

    return jsonify({
        "success": True,
        "config": config,
        "crypto_prices": crypto_prices,
        "already_withdrawn": already_withdrawn,
        "user_balance": user_balance,
        "withdraw_count": withdraw_count
    }), 200

@withdraw_bp.route('/request', methods=['POST'])
def handle_withdraw():
    data = request.json or {}
    user_id = str(data.get('user_id', '')).strip()
    coins = float(data.get('coins', 0))
    currency = str(data.get('currency', 'DOGE')).upper()
    wallet_address = str(data.get('wallet_address', '')).strip()

    supported_currencies = DEFAULT_WITHDRAW_CONFIG.get('supported_currencies', ["DOGE", "TRX", "PEPE", "LTC"])
    if currency not in supported_currencies:
        return jsonify({"success": False, "message": "العملة المختارة غير مدعومة."}), 400

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة."}), 400

    if has_withdrawn_today(user_id):
        return jsonify({"success": False, "message": "مسموح بسحب واحد فقط يومياً (UTC)."}), 400

    config = fetch_or_create_withdraw_config()
    user_details = get_user_full_details(user_id)
    if not user_details:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    user_balance = float(user_details.get('balance', 0.0))
    if coins > user_balance:
        return jsonify({"success": False, "message": "رصيدك الحالي غير كافٍ لإتمام السحب."}), 400

    withdraw_count = int(user_details.get('withdraw_count', 0))
    levels = config.get('levels', DEFAULT_WITHDRAW_CONFIG['levels'])
    
    level_index = min(withdraw_count, len(levels) - 1)
    matched_level = levels[level_index]

    if not (matched_level['min'] <= coins <= matched_level['max']):
        return jsonify({"success": False, "message": f"المبلغ المدخل خارج حدود السحبة الحالية ({matched_level['min']:,} - {matched_level['max']:,} ZN)."}), 400

    # محرك تحويل الأسعار والرسوم
    prices = get_live_crypto_prices()
    selected_price = prices.get(currency, 1.0)
    rate_coins_per_usd = config.get('rate_coins_per_usd', 100000)
    fee_percent = config.get('fee_percent', 3)
    
    fee_coins = coins * (fee_percent / 100)
    net_coins = coins - fee_coins
    net_usd = net_coins / rate_coins_per_usd
    net_crypto = net_usd / selected_price

    # تسجيل السحب بالداتابيز
    success, msg, tx_id = process_withdraw_db(
        user_id=user_id,
        coins_amount=coins,
        crypto_amount=net_crypto,
        currency=currency,
        level_info=matched_level,
        wallet_address=wallet_address
    )

    if not success:
        return jsonify({"success": False, "message": msg}), 400

    # التنفيذ حسب المستوى (آلي أم يدوي)
    if matched_level['type'] == 'auto':
        transfer_success, transfer_msg = send_faucetpay_payment(
            to_address_or_email=wallet_address,
            amount=net_crypto,
            currency=currency,
            tx_id=tx_id
        )
        db = _get_firestore_client()
        if transfer_success:
            if db:
                db.collection('processed_txs').document(tx_id).update({
                    'status': 'completed',
                    'tx_note': transfer_msg,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            notify_group_auto_success(user_id, coins, net_crypto, currency, wallet_address, tx_id)
            return jsonify({"success": True, "message": f"تم تحويل {net_crypto:.6f} {currency} بنجاح إلى حسابك في FaucetPay!"}), 200
        else:
            if db:
                db.collection('processed_txs').document(tx_id).update({
                    'status': 'pending_retry',
                    'error_log': transfer_msg,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            notify_admin_auto_failed(user_id, coins, net_crypto, currency, wallet_address, tx_id, transfer_msg)
            return jsonify({"success": True, "message": "تم تسجيل الطلب ووضعه قيد المعالجة المباشرة."}), 200
    else:
        notify_admin_for_manual_approval(user_id, coins, net_crypto, currency, wallet_address, matched_level['level'], tx_id)

    return jsonify({"success": True, "message": "تم إرسال طلب السحب بنجاح للمراجعة والاعتماد."}), 200

@withdraw_bp.route('/admin-approve', methods=['POST'])
def handle_admin_decision():
    data = request.json or {}
    tx_id = data.get('tx_id')
    action = data.get('action')

    if not tx_id or not action:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة."}), 400

    db = _get_firestore_client()
    if not db:
        return jsonify({"success": False, "message": "خطأ في الاتصال بقاعدة البيانات."}), 500

    tx_ref = db.collection('processed_txs').document(tx_id)
    tx_doc = tx_ref.get()

    if not tx_doc.exists:
        return jsonify({"success": False, "message": "المعاملة غير موجودة."}), 404

    tx_data = tx_doc.to_dict()
    if tx_data.get('status') not in ['pending', 'processing', 'pending_retry']:
        return jsonify({"success": False, "message": "تم اتخاذ قرار في هذه المعاملة سابقاً."}), 400

    user_ref, _ = get_user_doc(tx_data['user_id'])
    if not user_ref:
        user_ref = db.collection('users').document(str(tx_data['user_id']))

    crypto_amount = tx_data.get('crypto_amount', tx_data.get('amount_crypto', 0.0))
    currency = tx_data.get('currency', 'DOGE')

    if action == 'approve':
        transfer_success, transfer_msg = send_faucetpay_payment(
            to_address_or_email=tx_data['wallet'],
            amount=crypto_amount,
            currency=currency,
            tx_id=tx_id
        )
        if transfer_success:
            tx_ref.update({
                'status': 'completed',
                'tx_note': transfer_msg,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            notify_manual_decision(tx_data['user_id'], tx_data['coins'], crypto_amount, currency, tx_data['wallet'], "approve", tx_id)
            return jsonify({"success": True, "message": "تمت الموافقة والتحويل الآلي بنجاح عبر FaucetPay."}), 200
        else:
            return jsonify({"success": False, "message": f"فشل التحويل الشبكي: {transfer_msg}"}), 500

    elif action == 'reject':
        user_ref.update({
            'balance': firestore.Increment(tx_data['coins']),
            'withdraw_count': firestore.Increment(-1)
        })
        tx_ref.update({'status': 'rejected', 'updated_at': firestore.SERVER_TIMESTAMP})
        notify_manual_decision(tx_data['user_id'], tx_data['coins'], crypto_amount, currency, tx_data['wallet'], "reject", tx_id)
        return jsonify({"success": True, "message": "تم الرفض وإعادة العملات لرصيد المستخدم."}), 200

    return jsonify({"success": False, "message": "إجراء غير معروف."}), 400


# ==================== نظام الإشعارات والرسائل للتليجرام ====================

def _send_telegram_msg(text, reply_markup=None):
    bot_token = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not bot_token or not admin_chat_id:
        print("❌ إشعار التليجرام لم يرسل: ADMIN_BOT_TOKEN أو ADMIN_CHAT_ID مفقود.")
        return

    payload = {
        "chat_id": admin_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        res = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload, timeout=5)
        if res.status_code != 200:
            print(f"❌ التليجرام أعاد خطأ عند إرسال الإشعار: {res.text}")
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بالتليجرام: {e}")

def notify_group_auto_success(user_id, coins, crypto_amount, currency, wallet, tx_id):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_crypto = f"{crypto_amount:.6f}"
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    text = (
        "<b>🎉 تم تنفيذ عملية سحب بنجاح (تلقائي)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ المسحوب:</b> <code>{formatted_coins} ZN</code>\n"
        f"<b>💎 الصافي المستلم:</b> <code>{formatted_crypto} {currency}</code>\n"
        f"<b>📥 حساب/عنوان FaucetPay:</b> <code>{short_wallet}</code>\n"
        f"<b>🆔 رقم المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>تم التحويل الآلي بنجاح عبر FaucetPay!</b>"
    )
    _send_telegram_msg(text)

def notify_admin_auto_failed(user_id, coins, crypto_amount, currency, wallet, tx_id, error_msg):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_crypto = f"{crypto_amount:.6f}"
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    text = (
        "<b>🚨 تنبيه: فشل السحب التلقائي (قيد الإعادة)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ:</b> <code>{formatted_coins} ZN</code> (<code>{formatted_crypto} {currency}</code>)\n"
        f"<b>📥 العنوان:</b> <code>{short_wallet}</code>\n"
        f"<b>🆔 المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
        f"<b>❌ سبب الخطأ:</b> <code>{error_msg}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>تم تعليق المعاملة. يمكنك إعادة المحاولة يدوياً بعد معالجة السبب.</b>"
    )
    reply_markup = {
        "inline_keyboard": [[
            {"text": "موافقة وإعادة المحاولة 🟢", "callback_data": f"approve_tx_{tx_id}"},
            {"text": "رفض وإعادة الرصيد 🔴", "callback_data": f"reject_tx_{tx_id}"}
        ]]
    }
    _send_telegram_msg(text, reply_markup=reply_markup)

def notify_admin_for_manual_approval(user_id, coins, crypto_amount, currency, wallet, level, tx_id):
    user_info = get_user_full_details(user_id) or {}
    first_name = user_info.get('first_name', 'غير معروف')
    username = user_info.get('username')
    username_text = f"@{username}" if username and username != 'لا يوجد' else 'بدون معرف'
    joined_date = user_info.get('joined_date', 'غير معروف')
    referrals_count = user_info.get('referrals_count', 0)
    user_bal = float(user_info.get('balance', 0))
    total_earned = float(user_info.get('total_earned', 0))
    withdraw_count = user_info.get('withdraw_count', 0)
    last_withdraw_date = user_info.get('last_withdraw_date', 'لا يوجد')

    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_crypto = f"{crypto_amount:.6f}"
    formatted_user_bal = f"{user_bal:,.0f}" if user_bal == int(user_bal) else f"{user_bal:,}"
    formatted_total_earned = f"{total_earned:,.0f}" if total_earned == int(total_earned) else f"{total_earned:,}"

    text = (
        f"🚨 <b>طلب سحب يدوي جديد (مستوى {level})</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<b>👤 بيانات الحساب:</b>\n"
        f"• <b>ID:</b> <code>{user_id}</code>\n"
        f"• <b>الاسم:</b> {first_name}\n"
        f"• <b>اليوزر:</b> {username_text}\n"
        f"• <b>تاريخ الانضمام:</b> <code>{joined_date}</code>\n\n"
        "<b>📊 سجل النشاط وفحص الغش:</b>\n"
        f"• <b>عدد الإحالات:</b> <code>{referrals_count}</code> شخص\n"
        f"• <b>الرصيد المتبقي:</b> <code>{formatted_user_bal} ZN</code>\n"
        f"• <b>إجمالي الأرباح:</b> <code>{formatted_total_earned} ZN</code>\n"
        f"• <b>عدد السحوبات الناجحة:</b> <code>{withdraw_count}</code> مرة\n"
        f"• <b>آخر سحب:</b> <code>{last_withdraw_date}</code>\n\n"
        "<b>💎 تفاصيل طلب السحب:</b>\n"
        f"• <b>المبلغ المطلوب:</b> <code>{formatted_coins} ZN</code>\n"
        f"• <b>الصافي للتحويل:</b> <code>{formatted_crypto} {currency}</code>\n"
        f"• <b>عنوان/إيميل FaucetPay:</b>\n<code>{wallet}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    reply_markup = {
        "inline_keyboard": [[
            {"text": "موافقة 🟢", "callback_data": f"approve_tx_{tx_id}"},
            {"text": "رفض وإعادة الرصيد 🔴", "callback_data": f"reject_tx_{tx_id}"}
        ]]
    }
    _send_telegram_msg(text, reply_markup=reply_markup)

def notify_manual_decision(user_id, coins, crypto_amount, currency, wallet, action, tx_id):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_crypto = f"{crypto_amount:.6f}"
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    if action == "approve":
        text = (
            "<b>🟢 إشعار حالة سحب يدوي: تم القبول بالموافقة</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
            f"<b>💰 المبلغ:</b> <code>{formatted_coins} ZN</code>\n"
            f"<b>💎 الصافي المحول:</b> <code>{formatted_crypto} {currency}</code>\n"
            f"<b>📥 المحفظة:</b> <code>{short_wallet}</code>\n"
            f"<b>🆔 المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تمت الموافقة وتم تنفيذ التحويل بنجاح إلى FaucetPay!</b>"
        )
    else:
        text = (
            "<b>🔴 إشعار حالة سحب يدوي: تم الرفض</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
            f"<b>💰 المبلغ المرفوض:</b> <code>{formatted_coins} ZN</code>\n"
            f"<b>🆔 المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "❌ <b>تم رفض طلب السحب اليدوي وتمت إعادة العملات كاملة لرصيد المستخدم.</b>"
        )
    _send_telegram_msg(text)

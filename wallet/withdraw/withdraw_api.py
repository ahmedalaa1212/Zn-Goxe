import os
import re
import time
import requests
from flask import Blueprint, request, jsonify, url_for
from firebase_admin import firestore

# كاش أسعار العملات لمدة 60 ثانية لتقليل الضغط على الـ API
PRICE_CACHE = {
    "data": {},
    "last_updated": 0
}

# دالة لتنسيق الأرقام العشرية بشكل نظيف وبدون أصفار أو كسور غريبة
def clean_round(value, decimals=8):
    if not isinstance(value, (int, float)):
        return value
    return round(float(value), decimals)

def format_crypto_display(amount):
    """تنسيق عرض العملة في الرسائل والإشعارات بدون أصفار زائدة"""
    formatted = f"{amount:,.8f}".rstrip('0').rstrip('.')
    return formatted if formatted else "0"

# دالة التحقق من صحة عنوان المحفظة أو البريد الإلكتروني حسب العملة
def validate_wallet_address(address, currency):
    if not address or not isinstance(address, str):
        return False, "يرجى إدخال عنوان المحفظة أو البريد الإلكتروني الخاص بـ FaucetPay."
    
    addr = address.strip()
    if not addr:
        return False, "يرجى إدخال عنوان المحفظة أو البريد الإلكتروني الخاص بـ FaucetPay."

    # 1. التحقق مما إذا كان العنوان بريد إلكتروني (مقبول لجميع عملات FaucetPay)
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(email_regex, addr):
        return True, ""

    curr = currency.upper()

    # 2. التحقق من صيغة عناوين الشبكات للعملات المدعومة
    if curr == "DOGE":
        if re.match(r'^D[1-9A-HJ-NP-Za-km-z]{33}$', addr):
            return True, ""
        return False, "عنوان DOGE غير صحيح! يجب أن يبدأ بحرف D ويتكون من 34 خانة، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."

    elif curr == "TRX":
        if re.match(r'^T[1-9A-HJ-NP-Za-km-z]{33}$', addr):
            return True, ""
        return False, "عنوان TRX غير صحيح! يجب أن يبدأ بحرف T ويتكون من 34 خانة، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."

    elif curr == "LTC":
        if re.match(r'^(L|M)[1-9A-HJ-NP-Za-km-z]{33}$', addr) or re.match(r'^ltc1[a-z0-9]{38,58}$', addr, re.IGNORECASE):
            return True, ""
        return False, "عنوان LTC غير صحيح! يجب أن يبدأ بـ L أو M أو ltc1، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."

    elif curr == "PEPE":
        if re.match(r'^0x[a-fA-F0-9]{40}$', addr):
            return True, ""
        return False, "عنوان PEPE غير صحيح! يجب أن يكون عنوان EVM يبدأ بـ 0x (42 خانة)، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."

    return True, ""


# دالة جلب الأسعار اللحظية للعملات مع دعم Binance أولاً مع تقريب الأرقام العشرية
def get_live_crypto_prices():
    now = time.time()
    if PRICE_CACHE["data"] and (now - PRICE_CACHE["last_updated"] < 60):
        return PRICE_CACHE["data"]

    fallback_prices = {
        "DOGE": 0.11,
        "TRX": 0.16,
        "PEPE": 0.00000386,
        "LTC": 68.0
    }

    try:
        symbols = {"DOGE": "DOGEUSDT", "TRX": "TRXUSDT", "PEPE": "PEPEUSDT", "LTC": "LTCUSDT"}
        binance_prices = {}
        for coin, symbol in symbols.items():
            res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=3)
            if res.status_code == 200:
                val = float(res.json().get("price", 0))
                if val > 0:
                    binance_prices[coin] = clean_round(val, 8)
        if len(binance_prices) == 4:
            PRICE_CACHE["data"] = binance_prices
            PRICE_CACHE["last_updated"] = now
            return binance_prices
    except Exception as e:
        print(f"⚠️ خطأ جلب الأسعار من Binance: {e}")

    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=dogecoin,tron,pepe,litecoin&vs_currencies=usd"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            prices = {
                "DOGE": clean_round(data.get("dogecoin", {}).get("usd", fallback_prices["DOGE"]), 8),
                "TRX": clean_round(data.get("tron", {}).get("usd", fallback_prices["TRX"]), 8),
                "PEPE": clean_round(data.get("pepe", {}).get("usd", fallback_prices["PEPE"]), 8),
                "LTC": clean_round(data.get("litecoin", {}).get("usd", fallback_prices["LTC"]), 8)
            }
            PRICE_CACHE["data"] = prices
            PRICE_CACHE["last_updated"] = now
            return prices
    except Exception as e:
        print(f"⚠️ خطأ جلب الأسعار من CoinGecko: {e}")

    try:
        url = "https://min-api.cryptocompare.com/data/pricemulti?fsyms=DOGE,TRX,PEPE,LTC&tsyms=USD"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            prices = {
                "DOGE": clean_round(data.get("DOGE", {}).get("USD", fallback_prices["DOGE"]), 8),
                "TRX": clean_round(data.get("TRX", {}).get("USD", fallback_prices["TRX"]), 8),
                "PEPE": clean_round(data.get("PEPE", {}).get("USD", fallback_prices["PEPE"]), 8),
                "LTC": clean_round(data.get("LTC", {}).get("USD", fallback_prices["LTC"]), 8)
            }
            PRICE_CACHE["data"] = prices
            PRICE_CACHE["last_updated"] = now
            return prices
    except Exception as e:
        print(f"⚠️ خطأ جلب الأسعار من CryptoCompare: {e}")

    return PRICE_CACHE["data"] if PRICE_CACHE["data"] else fallback_prices


# دالة التحويل الآلي عبر FaucetPay API (بالساتوشي)
def send_faucetpay_payment(to_address_or_email, amount, currency, tx_id):
    api_key = os.getenv("FAUCETPAY_API_KEY")
    if not api_key:
        return False, "مفتاح FAUCETPAY_API_KEY غير متوفر ببيئة التشغيل."

    url = "https://faucetpay.io/api/v1/send"
    satoshis_amount = int(round(amount * 100_000_000))

    payload = {
        "api_key": api_key,
        "to": to_address_or_email,
        "amount": satoshis_amount,
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
    "faucetpay_spread_markup": 1.06,
    "rate_coins_per_usd": 100000,
    "supported_currencies": ["DOGE", "TRX", "PEPE", "LTC"],
    "levels": [
        {"level": 1, "min": 10, "max": 100, "type": "auto"},
        {"level": 2, "min": 500, "max": 1500, "type": "auto"},
        {"level": 3, "min": 10000, "max": 50000, "type": "auto"},
        {"level": 4, "min": 100000, "max": 200000, "type": "manual"},
        {"level": 5, "min": 400000, "max": 800000, "type": "manual"},
        {"level": 6, "min": 1000000, "max": 2000000, "type": "manual"},
        {"level": 7, "min": 3000000, "max": 5000000, "type": "manual"},
        {"level": 8, "min": 6000000, "max": 10000000, "type": "manual"},
        {"level": 9, "min": 15000000, "max": 999999999, "type": "manual"}
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
                if 'faucetpay_spread_markup' not in data or data.get('faucetpay_spread_markup') == 1.0:
                    data['faucetpay_spread_markup'] = 1.06
                    doc_ref.set({'faucetpay_spread_markup': 1.06}, merge=True)
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
    raw_prices = get_live_crypto_prices()
    
    spread_markup = float(config.get('faucetpay_spread_markup', 1.06))
    protected_crypto_prices = {k: clean_round(v * spread_markup, 8) for k, v in raw_prices.items()}
    clean_raw_prices = {k: clean_round(v, 8) for k, v in raw_prices.items()}
    
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
        "crypto_prices": protected_crypto_prices,
        "raw_crypto_prices": clean_raw_prices,
        "already_withdrawn": already_withdrawn,
        "user_balance": user_balance,
        "withdraw_count": withdraw_count
    }), 200

@withdraw_bp.route('/request', methods=['POST'])
def handle_withdraw():
    data = request.json or {}
    user_id = str(data.get('user_id', '')).strip()
    coins = float(data.get('coins', data.get('coins_amount', 0)))
    currency = str(data.get('currency', 'DOGE')).upper()
    wallet_address = str(data.get('wallet_address', '')).strip()

    supported_currencies = DEFAULT_WITHDRAW_CONFIG.get('supported_currencies', ["DOGE", "TRX", "PEPE", "LTC"])
    if currency not in supported_currencies:
        return jsonify({"success": False, "message": "العملة المختارة غير مدعومة."}), 400

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة."}), 400

    is_valid_addr, addr_err_msg = validate_wallet_address(wallet_address, currency)
    if not is_valid_addr:
        return jsonify({"success": False, "message": addr_err_msg}), 400

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
        return jsonify({"success": False, "message": f"المبلغ المدخل خارج حدود السحبة الحالية للمستوى {matched_level['level']} ({matched_level['min']:,} - {matched_level['max']:,} ZN)."}), 400

    raw_prices = get_live_crypto_prices()
    selected_price = raw_prices.get(currency, 1.0)
    
    spread_markup = float(config.get('faucetpay_spread_markup', 1.06))
    protected_price = clean_round(selected_price * spread_markup, 8)

    rate_coins_per_usd = config.get('rate_coins_per_usd', 100000)
    fee_percent = config.get('fee_percent', 3)
    
    fee_coins = coins * (fee_percent / 100)
    net_coins = coins - fee_coins
    net_usd = net_coins / rate_coins_per_usd
    net_crypto = clean_round(net_usd / protected_price, 8)

    success, msg, tx_id = process_withdraw_db(
        user_id=user_id,
        coins_amount=coins,
        crypto_net_amount=net_crypto,
        currency=currency,
        level_info=matched_level,
        wallet_address=wallet_address
    )

    if not success:
        return jsonify({"success": False, "message": msg}), 400

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
            return jsonify({"success": True, "message": f"تم تحويل {format_crypto_display(net_crypto)} {currency} بنجاح إلى حسابك في FaucetPay!"}), 200
        else:
            if db:
                db.collection('processed_txs').document(tx_id).update({
                    'status': 'pending_retry',
                    'error_log': transfer_msg,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            
            error_lower = transfer_msg.lower()
            if "fund" in error_lower or "balance" in error_lower or "sufficient" in error_lower:
                notify_admin_empty_faucetpay(user_id, coins, net_crypto, currency, tx_id)
                return jsonify({"success": True, "message": "طلبك قيد الانتظار حالياً، جاري معالجة الطلب وسيتم التحويل فور توفر سيولة في المحفظة."}), 200
            else:
                notify_admin_auto_failed(user_id, coins, net_crypto, currency, wallet_address, tx_id, transfer_msg)
                return jsonify({"success": True, "message": "تم تسجيل الطلب ووضعه قيد الانتظار لمعالجته يدوياً."}), 200
    else:
        notify_admin_for_manual_approval(user_id, coins, net_crypto, currency, wallet_address, matched_level['level'], tx_id)

    return jsonify({"success": True, "message": "تم إرسال طلب السحب بنجاح للمراجعة والاعتماد."}), 200


def execute_admin_decision(tx_id, action):
    """منطق دالة المعالجة المشترك لقرارات الأدمن مع استخراج مرن للبيانات"""
    if not tx_id or not action:
        return False, "بيانات الطلب غير مكتملة."

    db = _get_firestore_client()
    if not db:
        return False, "خطأ في الاتصال بقاعدة البيانات."

    tx_ref = db.collection('processed_txs').document(str(tx_id))
    tx_doc = tx_ref.get()

    if not tx_doc.exists:
        return False, "المعاملة غير موجودة."

    tx_data = tx_doc.to_dict() or {}
    status = tx_data.get('status')

    if status not in ['pending', 'processing', 'pending_retry']:
        return False, "تم اتخاذ قرار في هذه المعاملة سابقاً."

    # استخراج كافة القيم بأمان لتجنب أخطاء المفاتيح KeyError
    user_id = str(tx_data.get('user_id') or tx_data.get('userId') or '').strip()
    coins = float(tx_data.get('coins') or tx_data.get('coins_amount') or tx_data.get('amount') or 0.0)
    wallet = str(tx_data.get('wallet') or tx_data.get('wallet_address') or tx_data.get('address') or '').strip()
    currency = str(tx_data.get('currency', 'DOGE')).upper()
    crypto_amount = clean_round(
        tx_data.get('crypto_net_amount',
        tx_data.get('crypto_amount',
        tx_data.get('amount_crypto', 0.0))), 8
    )

    if not user_id:
        return False, "بيانات المستخدم مفقودة في المستند."

    # الحصول على مرجع مستند المستخدم بشكل آمن بدون فرض التفكيك الأحادي/الثنائي
    user_ref = None
    try:
        res = get_user_doc(user_id)
        if isinstance(res, tuple):
            user_ref = res[0]
        elif res:
            user_ref = res
    except Exception as e:
        print(f"⚠️ خطأ جلب مرجع المستخدم: {e}")

    if not user_ref:
        user_ref = db.collection('users').document(user_id)

    if action == 'approve':
        # تعيين الحالة فوراً لمنع التنفيذ المكرر عند ضغط الزر عدة مرات
        tx_ref.update({'status': 'processing', 'updated_at': firestore.SERVER_TIMESTAMP})

        transfer_success, transfer_msg = send_faucetpay_payment(
            to_address_or_email=wallet,
            amount=crypto_amount,
            currency=currency,
            tx_id=str(tx_id)
        )
        if transfer_success:
            tx_ref.update({
                'status': 'completed',
                'tx_note': transfer_msg,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            notify_manual_decision(user_id, coins, crypto_amount, currency, wallet, "approve", str(tx_id))
            return True, "تمت الموافقة والتحويل الآلي بنجاح عبر FaucetPay."
        else:
            tx_ref.update({
                'status': 'pending_retry',
                'error_log': transfer_msg,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            return False, f"فشل التحويل الشبكي: {transfer_msg}"

    elif action == 'reject':
        tx_ref.update({'status': 'rejected', 'updated_at': firestore.SERVER_TIMESTAMP})
        try:
            user_ref.update({
                'balance': firestore.Increment(coins),
                'withdraw_count': firestore.Increment(-1)
            })
        except Exception as e:
            print(f"⚠️ خطأ إعادة الرصيد للمستخدم: {e}")

        notify_manual_decision(user_id, coins, crypto_amount, currency, wallet, "reject", str(tx_id))
        return True, "تم الرفض وإعادة العملات لرصيد المستخدم."

    return False, "إجراء غير معروف."


# ==================== استقبال ضغطات أزرار التليجرام (Webhook Handler) ====================

@withdraw_bp.route('/telegram-webhook', methods=['GET', 'POST'])
def telegram_webhook():
    """مسار استقبال الأزرار التفاعلية من التليجرام مباشرة مع رد سريع وحماية من التأخير"""
    if request.method == 'GET':
        return jsonify({"status": "ok", "message": "Telegram Webhook Endpoint active"}), 200

    update = request.json or {}

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb.get("id")
        cb_data = cb.get("data", "")
        msg = cb.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")
        orig_text = msg.get("text", "")

        # الرد المباشر فوراً لإيقاف مؤشر التحميل في تطبيق التليجرام
        _answer_telegram_callback(cb_id, "جاري معالجة الطلب...")

        tx_id = None
        action = None

        if cb_data.startswith("approve_tx_"):
            tx_id = cb_data.replace("approve_tx_", "")
            action = "approve"
        elif cb_data.startswith("reject_tx_"):
            tx_id = cb_data.replace("reject_tx_", "")
            action = "reject"

        if tx_id and action:
            success, result_msg = execute_admin_decision(tx_id, action)
            _answer_telegram_callback(cb_id, result_msg)

            if success:
                decision_badge = "\n\n✅ <b>تمت الموافقة والتحويل بنجاح!</b>" if action == "approve" else "\n\n❌ <b>تم رفض الطلب وإعادة الرصيد.</b>"
                _edit_telegram_message(chat_id, message_id, orig_text + decision_badge)
        else:
            _answer_telegram_callback(cb_id, "إجراء غير معروف.")

    return jsonify({"status": "ok"}), 200


def _answer_telegram_callback(callback_query_id, text):
    bot_token = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token or not callback_query_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    try:
        requests.post(url, json={
            "callback_query_id": callback_query_id,
            "text": text[:180],
            "show_alert": True
        }, timeout=5)
    except Exception as e:
        print(f"❌ خطأ إجابة callback تليجرام: {e}")


def _edit_telegram_message(chat_id, message_id, text, reply_markup=None):
    bot_token = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token or not chat_id or not message_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
    
    # إزالة الأزرار التفاعلية افتراضياً بعد الاعتماد
    markup = reply_markup if reply_markup is not None else {"inline_keyboard": []}

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code != 200:
            # محاولة احتياطية بدون HTML لتفادي توقف الرسالة إن اشتملت على رموز خاصة
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
            payload_fallback = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": clean_text,
                "reply_markup": markup
            }
            requests.post(url, json=payload_fallback, timeout=5)
    except Exception as e:
        print(f"❌ خطأ تعديل رسالة تليجرام: {e}")


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
    formatted_crypto = format_crypto_display(crypto_amount)
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    text = (
        "<b>🎉 تم تنفيذ عملية سحب بنجاح (تلقائي)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ المسحوب:</b> <code>{formatted_coins} ZN</code>\n"
        f"<b>💎 الصافي المستلم:</b> <code>{formatted_crypto} {currency}</code>\n"
        f"<b>📥 حساب/عنوان FaucetPay:</b> <code>{short_wallet}</code>\n"
        f"<b>🆔 رقم المعاملة:</b> <code>#{str(tx_id)[-8:]}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>تم التحويل الآلي بنجاح عبر FaucetPay!</b>"
    )
    _send_telegram_msg(text)

def notify_admin_empty_faucetpay(user_id, coins, crypto_amount, currency, tx_id):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_crypto = format_crypto_display(crypto_amount)
    
    text = (
        "<b>⚠️ تنبيه هام: رصيد الفوست باي غير كافي!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"طلب سحب تلقائي معلق بسبب نفاد رصيد عملة <b>{currency}</b> في حساب الفوست باي الخاص بك.\n\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ:</b> <code>{formatted_coins} ZN</code>\n"
        f"<b>💎 المطلوب تحويله:</b> <code>{formatted_crypto} {currency}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>يرجى شحن حساب FaucetPay الخاص بك، ثم اضغط على (موافقة) أدناه لتنفيذ الطلب المعلق.</b>"
    )
    reply_markup = {
        "inline_keyboard": [[
            {"text": "موافقة وإرسال الآن 🟢", "callback_data": f"approve_tx_{tx_id}"},
            {"text": "رفض وإلغاء 🔴", "callback_data": f"reject_tx_{tx_id}"}
        ]]
    }
    _send_telegram_msg(text, reply_markup=reply_markup)

def notify_admin_auto_failed(user_id, coins, crypto_amount, currency, wallet, tx_id, error_msg):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_crypto = format_crypto_display(crypto_amount)
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    text = (
        "<b>🚨 تنبيه: فشل السحب التلقائي (قيد الإعادة)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ:</b> <code>{formatted_coins} ZN</code> (<code>{formatted_crypto} {currency}</code>)\n"
        f"<b>📥 العنوان:</b> <code>{short_wallet}</code>\n"
        f"<b>🆔 المعاملة:</b> <code>#{str(tx_id)[-8:]}</code>\n"
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
    formatted_crypto = format_crypto_display(crypto_amount)
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
    formatted_crypto = format_crypto_display(crypto_amount)
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    if action == "approve":
        text = (
            "<b>🟢 إشعار حالة سحب يدوي: تم القبول بالموافقة</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
            f"<b>💰 المبلغ:</b> <code>{formatted_coins} ZN</code>\n"
            f"<b>💎 الصافي المحول:</b> <code>{formatted_crypto} {currency}</code>\n"
            f"<b>📥 المحفظة:</b> <code>{short_wallet}</code>\n"
            f"<b>🆔 المعاملة:</b> <code>#{str(tx_id)[-8:]}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تمت الموافقة وتم تنفيذ التحويل بنجاح إلى FaucetPay!</b>"
        )
    else:
        text = (
            "<b>🔴 إشعار حالة سحب يدوي: تم الرفض</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
            f"<b>💰 المبلغ المرفوض:</b> <code>{formatted_coins} ZN</code>\n"
            f"<b>🆔 المعاملة:</b> <code>#{str(tx_id)[-8:]}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "❌ <b>تم رفض طلب السحب اليدوي وتمت إعادة العملات كاملة لرصيد المستخدم.</b>"
        )
    _send_telegram_msg(text)


# ==================== دالة تفعيل الأزرار السحرية ====================
@withdraw_bp.route('/set-webhook', methods=['GET'])
def setup_telegram_webhook():
    """مسار سحري لربط أزرار التليجرام بالسيرفر بضغطة واحدة"""
    bot_token = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return jsonify({"success": False, "message": "لم يتم العثور على توكن البوت في المتغيرات (ADMIN_BOT_TOKEN)."}), 400

    try:
        # استخراج الرابط الكامل للمسار
        webhook_path = url_for('withdraw_bp.telegram_webhook')
        full_webhook_url = request.url_root.rstrip('/') + webhook_path
        
        # تليجرام يتطلب HTTPS إجبارياً
        if full_webhook_url.startswith("http://") and "localhost" not in full_webhook_url and "127.0.0.1" not in full_webhook_url:
            full_webhook_url = full_webhook_url.replace("http://", "https://")

        url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url={full_webhook_url}"
        res = requests.get(url, timeout=5)
        
        return jsonify({
            "success": True, 
            "message": "تم ربط التليجرام بنجاح! الأزرار ستعمل الآن.",
            "webhook_url": full_webhook_url,
            "telegram_response": res.json()
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


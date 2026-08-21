import os
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore

try:
    from core.gram_price import get_gram_price_usd
except ImportError:
    def get_gram_price_usd():
        return 1.46  # السعر الافتراضي التقريبي لعملة GRAM مقابل الدولار

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

NETWORK_FEE_GRAM = 0.0015  # رسم الشبكة التلقائي لكل عملية سحب

# إعدادات خطة السحب الستة بناءً على سعر الصرف (100,000 ZN = 1.00$)
DEFAULT_WITHDRAW_CONFIG = {
    "fee_percent": 3,
    "network_fee_gram": NETWORK_FEE_GRAM,
    "rate_coins_per_usd": 100000,
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
                # فرض تحديث المستويات الثابتة ومعدل التحويل مع الحفاظ على بقية الإعدادات
                data['rate_coins_per_usd'] = 100000
                data['levels'] = DEFAULT_WITHDRAW_CONFIG['levels']
                doc_ref.set(data, merge=True)
                return data
        
        doc_ref.set(DEFAULT_WITHDRAW_CONFIG, merge=True)
        return DEFAULT_WITHDRAW_CONFIG
    except Exception as e:
        print(f"⚠️ خطأ وصول Firebase لمستند withdraw_config: {e}")
        return DEFAULT_WITHDRAW_CONFIG

try:
    fetch_or_create_withdraw_config()
except Exception as e:
    print(f"⚠️ تنبيه إنشاء إعدادات السحب: {e}")

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id') or "5102387551"
    config = fetch_or_create_withdraw_config()

    try:
        gram_price = get_gram_price_usd() or 1.46
    except Exception:
        gram_price = 1.46
    
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

    process_pending_funds_withdrawals()

    return jsonify({
        "success": True,
        "config": config,
        "gram_price": gram_price,
        "already_withdrawn": already_withdrawn,
        "user_balance": user_balance,
        "withdraw_count": withdraw_count
    }), 200

@withdraw_bp.route('/request', methods=['POST'])
def handle_withdraw():
    data = request.json or {}
    user_id = str(data.get('user_id', '')).strip()
    coins = float(data.get('coins', 0))
    wallet_address = data.get('wallet_address')

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة."}), 400

    if has_withdrawn_today(user_id):
        return jsonify({"success": False, "message": "مسموح بسحب واحد فقط يومياً."}), 400

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
        max_str = "مفتوح" if matched_level['max'] >= 999999999 else f"{matched_level['max']:,} ZN"
        return jsonify({"success": False, "message": f"المبلغ المدخل خارج حدود السحبة الحالية ({matched_level['min']:,} - {max_str})."}), 400

    gram_price = get_gram_price_usd() or 1.46
    rate_coins_per_usd = config.get('rate_coins_per_usd', 100000)
    fee_percent = config.get('fee_percent', 3)
    net_fee_gram = config.get('network_fee_gram', NETWORK_FEE_GRAM)
    
    # المعادلة: 100,000 ZN = $1.00 USD -> تحويل الدولار إلى GRAM بسعر السوق
    fee_coins = coins * (fee_percent / 100)
    net_coins = coins - fee_coins
    net_usd = net_coins / rate_coins_per_usd
    gross_gram = net_usd / gram_price
    
    net_gram = max(0.0, gross_gram - net_fee_gram)

    success, msg, tx_id = process_withdraw_db(
        user_id=user_id,
        coins_amount=coins,
        gram_amount=net_gram,
        level_info=matched_level,
        wallet_address=wallet_address
    )

    if not success:
        return jsonify({"success": False, "message": msg}), 400

    if matched_level['type'] == 'auto':
        transfer_status = execute_auto_transfer(wallet_address, net_gram, tx_id, user_id, coins)
        if transfer_status is True:
            notify_group_auto_success(user_id, coins, net_gram, wallet_address, tx_id)
            return jsonify({"success": True, "message": f"تم تحويل {net_gram:.4f} GRAM بنجاح إلى محفظتك!"}), 200
        elif transfer_status == "pending_funds":
            return jsonify({
                "success": True, 
                "message": "تم تقديم طلب السحب بنجاح! المحفظة الساخنة تحتاج شحن بالـ GRAM لتنفيذ التحويل تلقائياً."
            }), 200
        else:
            return jsonify({"success": True, "message": "تم تسجيل طلب السحب ووضعه قيد المعالجة الشبكية."}), 200
    else:
        notify_admin_for_manual_approval(user_id, coins, net_gram, wallet_address, matched_level['level'], tx_id)

    return jsonify({"success": True, "message": "تم إرسال طلب السحب بنجاح وتسجيل العملية في السجلات."}), 200

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
    if tx_data.get('status') not in ['pending', 'pending_funds', 'processing']:
        return jsonify({"success": False, "message": "تم اتخاذ قرار في هذه المعاملة سابقاً."}), 400

    user_ref, _ = get_user_doc(tx_data['user_id'])
    if not user_ref:
        user_ref = db.collection('users').document(str(tx_data['user_id']))

    gram_amount = tx_data.get('gram_amount', tx_data.get('amount_gram', tx_data.get('ton_amount', 0.0)))

    if action == 'approve':
        status = execute_auto_transfer(tx_data['wallet'], gram_amount, tx_id, tx_data['user_id'], tx_data['coins'])
        if status is True:
            notify_manual_decision(tx_data['user_id'], tx_data['coins'], gram_amount, tx_data['wallet'], "approve", tx_id)
            return jsonify({"success": True, "message": "تمت الموافقة والتحويل الشبكي بنجاح."}), 200
        elif status == "pending_funds":
            return jsonify({"success": False, "message": "تم تعليق المعاملة بسبب عدم كفاية رصيد المحفظة الساخنة."}), 400
        else:
            return jsonify({"success": False, "message": "فشل تنفيذ عملية التحويل الشبكي."}), 500

    elif action == 'reject':
        user_ref.update({
            'balance': firestore.Increment(tx_data['coins']),
            'withdraw_count': firestore.Increment(-1)
        })
        tx_ref.update({'status': 'rejected', 'updated_at': firestore.SERVER_TIMESTAMP})
        notify_manual_decision(tx_data['user_id'], tx_data['coins'], gram_amount, tx_data['wallet'], "reject", tx_id)
        return jsonify({"success": True, "message": "تم الرفض وإعادة العملات لرصيد المستخدم."}), 200

    return jsonify({"success": False, "message": "إجراء غير معروف."}), 400

def check_hot_wallet_balance():
    hot_wallet = os.getenv("HOT_WALLET_ADDRESS") or os.getenv("PROJECT_WALLET")
    api_key = os.getenv("TONCENTER_API_KEY")
    if not hot_wallet:
        return 0.0

    try:
        url = f"https://toncenter.com/api/v2/getAddressInformation?address={hot_wallet}"
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        if data.get("ok"):
            gram_bal_str = os.getenv("HOT_WALLET_GRAM_BALANCE")
            if gram_bal_str:
                return float(gram_bal_str)
            nanogram = int(data["result"].get("balance", 0))
            return nanogram / 1e9
    except Exception as e:
        print(f"خطأ في قراءة رصيد محفظة GRAM الساخنة: {e}")
    return 0.0

def send_gram_onchain(server_seed, to_address, gram_amount, comment="ZN Goxe GRAM Withdraw"):
    try:
        import tonsdk
        from tonsdk.contract.wallet import WalletVersionEnum, WalletContract
        from tonsdk.utils import bytes_to_b64str, Address
    except ImportError:
        print("❌ موديول tonsdk غير مثبت.")
        return False, "موديول tonsdk غير متاح في السيرفر."

    api_key = os.getenv("TONCENTER_API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}

    try:
        mnemonics = server_seed.strip().split()
        if len(mnemonics) not in [12, 24]:
            return False, "مفتاح البذور HOT_WALLET_SEED غير صحيح."

        _mnemonics, _pub_k, _priv_k, wallet = WalletContract.create(
            version=WalletVersionEnum.v4r2,
            mnemonics=mnemonics
        )
        
        wallet_addr_str = wallet.address.to_string(True, True, True)

        seqno_url = "https://toncenter.com/api/v2/runGetMethod"
        seqno_payload = {"address": wallet_addr_str, "method": "seqno", "stack": []}
        seqno_res = requests.post(seqno_url, json=seqno_payload, headers=headers, timeout=10)
        seqno_data = seqno_res.json()
        
        seqno = 0
        if seqno_data.get("ok") and seqno_data.get("result", {}).get("exit_code") == 0:
            stack = seqno_data["result"].get("stack", [])
            if stack and len(stack) > 0 and stack[0][0] == "num":
                raw_hex = stack[0][1]
                seqno = int(raw_hex, 16) if isinstance(raw_hex, str) and raw_hex.startswith("0x") else int(raw_hex)

        nano_amount = int(gram_amount * 1e9)
        target_addr = Address(to_address).to_string(True, True, False)

        transfer_query = wallet.create_transfer_message(
            to_addr=target_addr,
            amount=nano_amount,
            seqno=seqno,
            payload=comment
        )

        boc_bytes = transfer_query['message'].to_boc(False)
        boc_b64 = bytes_to_b64str(boc_bytes)

        send_url = "https://toncenter.com/api/v2/sendBoc"
        send_res = requests.post(send_url, json={"boc": boc_b64}, headers=headers, timeout=10)
        send_data = send_res.json()

        if send_data.get("ok"):
            tx_hash = send_data.get("result", {}).get("@type", "success")
            print(f"✅ تم إرسال عملات GRAM بنجاح على الشبكة! Hash: {tx_hash}")
            return True, "تم الإرسال على شبكة GRAM بنجاح."
        else:
            err = send_data.get("error", "فشل إرسال BOC")
            print(f"❌ خطأ إرسال BOC: {err}")
            return False, err

    except Exception as e:
        print(f"❌ خطأ أثناء إرسال GRAM على الشبكة: {e}")
        return False, str(e)

def execute_auto_transfer(to_address, gram_amount, tx_id, user_id, coins):
    server_seed = os.getenv("HOT_WALLET_SEED")
    db = _get_firestore_client()
    
    if not server_seed:
        print("خطأ: HOT_WALLET_SEED غير مضبوط في متغيرات البيئة.")
        if db:
            tx_ref = db.collection('processed_txs').document(tx_id)
            tx_ref.update({'status': 'pending_config', 'updated_at': firestore.SERVER_TIMESTAMP})
        return False

    current_balance = check_hot_wallet_balance()
    required_total = gram_amount + NETWORK_FEE_GRAM

    if current_balance < required_total:
        if db:
            tx_ref = db.collection('processed_txs').document(tx_id)
            tx_ref.update({'status': 'pending_funds', 'updated_at': firestore.SERVER_TIMESTAMP})
        
        notify_admin_insufficient_funds(user_id, coins, gram_amount, to_address, current_balance)
        return "pending_funds"

    success_onchain, msg_onchain = send_gram_onchain(
        server_seed=server_seed,
        to_address=to_address,
        gram_amount=gram_amount,
        comment=f"ZN Goxe GRAM Withdrawal #{tx_id[-6:]}"
    )

    if success_onchain:
        if db:
            tx_ref = db.collection('processed_txs').document(tx_id)
            tx_ref.update({
                'status': 'completed',
                'tx_note': msg_onchain,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
        return True
    else:
        print(f"⚠️ فشل التحويل الشبكي التلقائي: {msg_onchain}")
        if db:
            tx_ref = db.collection('processed_txs').document(tx_id)
            tx_ref.update({
                'status': 'pending_retry',
                'error_log': msg_onchain,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
        return False

def process_pending_funds_withdrawals():
    db = _get_firestore_client()
    if not db:
        return

    try:
        pending_txs = db.collection('processed_txs').where('status', '==', 'pending_funds').get()
        if not pending_txs:
            return

        current_balance = check_hot_wallet_balance()

        for tx_doc in pending_txs:
            tx_data = tx_doc.to_dict()
            tx_id = tx_doc.id
            gram_amount = tx_data.get('gram_amount', tx_data.get('amount_gram', 0.0))
            required = gram_amount + NETWORK_FEE_GRAM

            if current_balance >= required:
                status = execute_auto_transfer(
                    to_address=tx_data['wallet'],
                    gram_amount=gram_amount,
                    tx_id=tx_id,
                    user_id=tx_data['user_id'],
                    coins=tx_data['coins']
                )
                if status is True:
                    notify_group_pending_paid_after_recharge(
                        user_id=tx_data['user_id'],
                        coins=tx_data['coins'],
                        gram_amount=gram_amount,
                        wallet=tx_data['wallet'],
                        tx_id=tx_id
                    )
                    current_balance -= required
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة الطلبات المعلقة: {e}")

# ==================== نظام الإشعارات والرسائل ====================

def _send_telegram_msg(text, reply_markup=None):
    bot_token = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not bot_token or not admin_chat_id:
        print("⚠️ تعذر إرسال الإشعار: BOT_TOKEN أو ADMIN_CHAT_ID غير مضبوط.")
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
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload, timeout=5)
    except Exception as e:
        print(f"خطأ في إرسال إشعار تلجرام: {e}")

def notify_group_auto_success(user_id, coins, gram_amount, wallet, tx_id):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_gram = f"{gram_amount:.4f}"
    usd_val = coins / 100000.0
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    text = (
        "<b>🎉 تم تنفيذ عملية سحب بنجاح (تلقائي)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ المسحوب:</b> <code>{formatted_coins} ZN</code> (<code>${usd_val:.4f}</code>)\n"
        f"<b>💎 الصافي المستلم:</b> <code>{formatted_gram} GRAM</code>\n"
        f"<b>⛽ رسوم الشبكة:</b> <code>{NETWORK_FEE_GRAM} GRAM</code>\n"
        f"<b>📥 المحفظة:</b> <code>{short_wallet}</code>\n"
        f"<b>🆔 رقم المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>تم التحويل الشبكي بنجاح ووصلت التوكنات للمحفظة!</b>"
    )
    _send_telegram_msg(text)

def notify_admin_insufficient_funds(user_id, coins, gram_amount, wallet, current_balance):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_gram = f"{gram_amount:.4f}"
    formatted_bal = f"{current_balance:.4f}"
    usd_val = coins / 100000.0

    text = (
        "<b>⚠️ تنبيه: عدم كفاية رصيد المحفظة الساخنة (GRAM)!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💎 المبلغ المطلوب:</b> <code>{formatted_coins} ZN</code> (<code>${usd_val:.4f}</code> | <code>{formatted_gram} GRAM</code>)\n"
        f"<b>💰 المتوفر بالمحفظة حالياً:</b> <code>{formatted_bal} GRAM</code>\n\n"
        f"<b>📥 المحفظة المستهدفة:</b>\n"
        f"<code>{wallet}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>تم تعليق الطلب تلقائياً (قيد المراجعة). فور شحن رصيد المحفظة بالـ GRAM سيتولى النظام إرسال الدفعة فوراً وإشعاركم.</b>"
    )
    _send_telegram_msg(text)

def notify_group_pending_paid_after_recharge(user_id, coins, gram_amount, wallet, tx_id):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_gram = f"{gram_amount:.4f}"
    usd_val = coins / 100000.0
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    text = (
        "<b>✨ تم دفع طلب سحب معلق بنجاح بعد شحن الرصيد!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ:</b> <code>{formatted_coins} ZN</code> (<code>${usd_val:.4f}</code>)\n"
        f"<b>💎 الصافي المحول:</b> <code>{formatted_gram} GRAM</code>\n"
        f"<b>📥 المحفظة:</b> <code>{short_wallet}</code>\n"
        f"<b>🆔 المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>كان هذا الطلب قيد المراجعة والتأجير بسبب الشحن، وحالياً تم تسديده بالكامل بنجاح.</b>"
    )
    _send_telegram_msg(text)

def notify_admin_for_manual_approval(user_id, coins, gram_amount, wallet, level, tx_id):
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
    formatted_gram = f"{gram_amount:.4f}"
    usd_val = coins / 100000.0
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
        f"• <b>المبلغ المطلوب:</b> <code>{formatted_coins} ZN</code> (<code>${usd_val:.2f}</code>)\n"
        f"• <b>المستحق للتحويل:</b> <code>{formatted_gram} GRAM</code>\n"
        f"• <b>المحفظة المستهدفة:</b>\n<code>{wallet}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    reply_markup = {
        "inline_keyboard": [[
            {"text": "موافقة 🟢", "callback_data": f"approve_tx_{tx_id}"},
            {"text": "رفض وإعادة الرصيد 🔴", "callback_data": f"reject_tx_{tx_id}"}
        ]]
    }
    _send_telegram_msg(text, reply_markup=reply_markup)

def notify_manual_decision(user_id, coins, gram_amount, wallet, action, tx_id):
    formatted_coins = f"{coins:,.0f}" if coins == int(coins) else f"{coins:,}"
    formatted_gram = f"{gram_amount:.4f}"
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    if action == "approve":
        text = (
            "<b>🟢 إشعار حالة سحب يدوي: تم القبول بالموافقة</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
            f"<b>💰 المبلغ:</b> <code>{formatted_coins} ZN</code>\n"
            f"<b>💎 الصافي المحول:</b> <code>{formatted_gram} GRAM</code>\n"
            f"<b>📥 المحفظة:</b> <code>{short_wallet}</code>\n"
            f"<b>🆔 المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تمت الموافقة على طلب السحب اليدوي وتم تنفيذ التحويل إلى المحفظة بنجاح!</b>"
        )
    else:
        text = (
            "<b>🔴 إشعار حالة سحب يدوي: تم الرفض</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
            f"<b>💰 المبلغ المرفوض:</b> <code>{formatted_coins} ZN</code>\n"
            f"<b>🆔 المعاملة:</b> <code>#{tx_id[-8:]}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "❌ <b>تم رفض طلب السحب اليدوي من قبل الأدمن وتمت إعادة العملات كاملة لرصيد المستخدم.</b>"
        )
    _send_telegram_msg(text)

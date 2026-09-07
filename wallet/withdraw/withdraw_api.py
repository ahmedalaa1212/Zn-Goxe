import os
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from .withdraw_db import (
    safe_get_db, 
    get_user_doc, 
    extract_user_balance, 
    extract_usd_balance, 
    get_current_withdraw_tier,
    ZNX_CONTRACT_ADDRESS
)

withdraw_bp = Blueprint('withdraw_bp', __name__)

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id') or "5102387551"
    
    user_balance = 0.0
    usd_balance = 0.0
    wallet_address = ""

    _, user_data = get_user_doc(user_id)
    if user_data:
        user_balance = extract_user_balance(user_data)
        usd_balance = extract_usd_balance(user_data)
        wallets = user_data.get('wallets', {})
        if isinstance(wallets, dict):
            wallet_address = wallets.get('ZNX', '')
        if not wallet_address:
            wallet_address = user_data.get('wallet_address', '') or ''

    tier_info = get_current_withdraw_tier()

    return jsonify({
        "success": True,
        "currency": "ZNX",
        "contract_address": ZNX_CONTRACT_ADDRESS,
        "fixed_fee_usd": tier_info.get("fixed_fee_usd", 0.02),
        "min_withdraw_znx": tier_info.get("min_withdraw_znx", 1000.0),
        "current_tier": tier_info,
        "user_balance": user_balance,
        "znx_balance": user_balance,
        "usd_balance": usd_balance,
        "wallet_address": wallet_address
    }), 200

@withdraw_bp.route('/save-wallet', methods=['POST'])
def handle_save_wallet():
    data = request.json or {}
    user_id = str(data.get('user_id', '')).strip()
    wallet_address = str(data.get('wallet_address', '')).strip()

    if not user_id or not wallet_address:
        return jsonify({"success": False, "message": "يرجى إدخال عنوان المحفظة بشكل صحيح."}), 400

    user_ref, _ = get_user_doc(user_id)
    if not user_ref:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    try:
        user_ref.set({
            'wallets': {'ZNX': wallet_address},
            'wallet_address': wallet_address
        }, merge=True)
        return jsonify({"success": True, "message": "تم حفظ المحفظة بنجاح!"}), 200
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء الحفظ."}), 500

@withdraw_bp.route('/request', methods=['POST'])
def handle_withdraw():
    data = request.json or {}
    user_id = str(data.get('user_id', '')).strip()
    try:
        coins = float(data.get('coins', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "مبلغ السحب غير صالح."}), 400

    wallet_address = str(data.get('wallet_address', '')).strip()

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات طلب السحب غير مكتملة."}), 400

    db = safe_get_db()
    if not db:
        return jsonify({"success": False, "message": "خطأ في الاتصال بقاعدة البيانات."}), 500

    user_ref, user_data = get_user_doc(user_id)

    if not user_ref or not user_data:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    if user_data.get('is_banned', False):
        return jsonify({"success": False, "message": "حسابك معطل ولا يمكنك إجراء عمليات سحب."}), 403

    tier_info = get_current_withdraw_tier()
    min_withdraw = tier_info.get('min_withdraw_znx', 1000.0)
    fixed_fee_usd = tier_info.get('fixed_fee_usd', 0.02)

    current_balance = extract_user_balance(user_data)
    usd_balance = extract_usd_balance(user_data)

    if coins < min_withdraw:
        return jsonify({
            "success": False, 
            "code": "BELOW_MINIMUM",
            "message": f"الحد الأدنى للسحب بالشريحة الحالية هو {min_withdraw:g} ZNX."
        }), 400

    if coins > current_balance:
        return jsonify({
            "success": False, 
            "code": "INSUFFICIENT_ZNX",
            "message": "رصيدك من عملة ZNX غير كافٍ لإتمام عملية السحب."
        }), 400

    if usd_balance < fixed_fee_usd:
        return jsonify({
            "success": False, 
            "code": "INSUFFICIENT_USD",
            "fee_required": fixed_fee_usd,
            "message": f"رسوم السحب لا تكفي! يجب إيداع مبلغ رسوم السحب ${fixed_fee_usd:.2f} USD لإتمام العملية."
        }), 400

    # --- حماية قصوى بـ Transaction لمنع التلاعب بالتزامن (Atomic Transaction) ---
    @firestore.transactional
    def update_balances_in_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("المستخدم غير موجود.")
        
        snap_data = snapshot.to_dict() or {}
        latest_znx = extract_user_balance(snap_data)
        latest_usd = extract_usd_balance(snap_data)

        if coins > latest_znx or latest_usd < fixed_fee_usd:
            raise Exception("رصيدك تغير أثناء المعالجة.")

        updated_znx = round(max(0.0, latest_znx - coins), 6)
        updated_usd = round(max(0.0, latest_usd - fixed_fee_usd), 4)

        transaction.update(ref, {
            'znx_balance': updated_znx,
            'usd_balance': updated_usd
        })
        return updated_znx, updated_usd

    try:
        transaction = db.transaction()
        new_znx_balance, new_usd_balance = update_balances_in_transaction(transaction, user_ref)

        tx_ref = db.collection('processed_txs').document()
        tx_id = tx_ref.id
        tx_ref.set({
            'user_id': user_id,
            'coins': coins,
            'fee_usd': fixed_fee_usd,
            'net_coins': coins,
            'currency': 'ZNX',
            'tier_name': tier_info.get('name', ''),
            'wallet_address': wallet_address,
            'status': 'pending',
            'created_at': firestore.SERVER_TIMESTAMP
        })

        notify_admin_withdraw(user_id, coins, fixed_fee_usd, wallet_address, tx_id, tier_info.get('name', ''))

        return jsonify({
            "success": True,
            "message": f"تم تقديم طلب سحب {coins:,.4f} ZNX بنجاح وهو قيد المراجعة!",
            "new_balance": new_znx_balance,
            "new_usd_balance": new_usd_balance
        }), 200

    except Exception as e:
        print(f"⚠️ خطأ معالجة السحب المالي: {e}")
        return jsonify({"success": False, "message": "تعذر إجراء السحب نظراً لتغير البيانات، يرجى إعادة المحاولة."}), 500

def notify_admin_withdraw(user_id, coins, fee_usd, wallet, tx_id, tier_name):
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return

    text = (
        "🚀 <b>طلب سحب ZNX جديد</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> <code>{user_id}</code>\n"
        f"📊 <b>الشريحة الحالية:</b> {tier_name}\n"
        f"💰 <b>المبلغ المطلوب:</b> <code>{coins:,.4f} ZNX</code>\n"
        f"💵 <b>الرسوم المقتطعة:</b> <code>${fee_usd:.2f} USD</code>\n"
        f"📥 <b>محفظة TON:</b>\n<code>{wallet}</code>\n"
        f"🆔 <b>رقم المعاملة:</b> <code>#{tx_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    reply_markup = {
        "inline_keyboard": [[
            {"text": "موافقة 🟢", "callback_data": f"approve_tx_{tx_id}"},
            {"text": "رفض 🔴", "callback_data": f"reject_tx_{tx_id}"}
        ]]
    }

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup},
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ إرسال إشعار السحب للأدمن: {e}")

def answer_callback_query(callback_query_id, text, show_alert=False):
    """إيقاف عجلة التحميل في التلجرام وإظهار إشعار سريع للمسؤول"""
    if not BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert},
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ في answerCallbackQuery: {e}")

def edit_telegram_message(chat_id, message_id, new_text):
    """تعديل الرسالة وحذف الأزرار لتأكيد الحالة النهائية"""
    if not BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": new_text,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []}  # إزالة الأزرار لمنع الضغط المزدوج
            },
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ في editMessageText: {e}")

@withdraw_bp.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json or {}
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb.get("id")
        cb_data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        if not cb_data.startswith("approve_tx_") and not cb_data.startswith("reject_tx_"):
            return jsonify({"status": "ignored"}), 200

        action = "approve" if cb_data.startswith("approve_tx_") else "reject"
        tx_id = cb_data.replace("approve_tx_", "").replace("reject_tx_", "").strip()

        db = safe_get_db()
        if not db or not tx_id:
            answer_callback_query(cb_id, "⚠️ خطأ في الاتصال بقاعدة البيانات!", show_alert=True)
            return jsonify({"status": "db_error"}), 200

        tx_ref = db.collection('processed_txs').document(tx_id)
        tx_doc = tx_ref.get()

        if not tx_doc.exists:
            answer_callback_query(cb_id, "❌ لم يتم العثور على المعاملة!", show_alert=True)
            return jsonify({"status": "not_found"}), 200

        tx_data = tx_doc.to_dict() or {}
        current_status = tx_data.get('status', 'pending')

        # لمنع المعالجة المزدوجة إذا تم الضغط على الزر سابقاً
        if current_status != 'pending':
            status_txt = "تم قبولها" if current_status == 'completed' else "تم رفضها"
            answer_callback_query(cb_id, f"⚠️ هذه المعاملة تم معالجتها بالفعل ({status_txt})!", show_alert=True)
            return jsonify({"status": "already_processed"}), 200

        user_id = tx_data.get('user_id')
        coins = float(tx_data.get('coins', 0))
        fee_usd = float(tx_data.get('fee_usd', 0.02))
        wallet = tx_data.get('wallet_address', '')
        tier_name = tx_data.get('tier_name', '')

        if action == "approve":
            tx_ref.update({
                'status': 'completed',
                'processed_at': firestore.SERVER_TIMESTAMP
            })
            answer_callback_query(cb_id, "🟢 تم قبول طلب السحب بنجاح!")
            
            final_text = (
                "✅ <b>تمت الموافقة على طلب السحب</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>المستخدم:</b> <code>{user_id}</code>\n"
                f"📊 <b>الشريحة:</b> {tier_name}\n"
                f"💰 <b>المبلغ:</b> <code>{coins:,.4f} ZNX</code>\n"
                f"💵 <b>الرسوم:</b> <code>${fee_usd:.2f} USD</code>\n"
                f"📥 <b>المحفظة:</b> <code>{wallet}</code>\n"
                f"🆔 <b>المعاملة:</b> <code>#{tx_id}</code>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🟢 <i>الحالة: مكتملة ومقبولة</i>"
            )
            edit_telegram_message(chat_id, message_id, final_text)

        else: # Reject Action
            tx_ref.update({
                'status': 'rejected',
                'processed_at': firestore.SERVER_TIMESTAMP
            })

            # إعادة الرصيد للمستخدم فوراً
            user_ref, _ = get_user_doc(user_id)
            if user_ref:
                user_ref.update({
                    'znx_balance': firestore.Increment(coins),
                    'usd_balance': firestore.Increment(fee_usd)
                })

            answer_callback_query(cb_id, "🔴 تم رفض الطلب وإعادة الرصيد للمستخدم!")

            final_text = (
                "❌ <b>تم رفض طلب السحب وإعادة الرصيد</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>المستخدم:</b> <code>{user_id}</code>\n"
                f"📊 <b>الشريحة:</b> {tier_name}\n"
                f"💰 <b>المبلغ المرجع:</b> <code>{coins:,.4f} ZNX</code>\n"
                f"💵 <b>الرسوم المرجعة:</b> <code>${fee_usd:.2f} USD</code>\n"
                f"📥 <b>المحفظة:</b> <code>{wallet}</code>\n"
                f"🆔 <b>المعاملة:</b> <code>#{tx_id}</code>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🔴 <i>الحالة: مرفوضة وتم استرجاع الرصيد</i>"
            )
            edit_telegram_message(chat_id, message_id, final_text)

    return jsonify({"status": "ok"}), 200

import os
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from .withdraw_db import safe_get_db, get_user_doc, extract_user_balance

withdraw_bp = Blueprint('withdraw_bp', __name__)

FEE_PERCENT = 5

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id') or "5102387551"
    
    user_balance = 0.0
    wallet_address = ""

    _, user_data = get_user_doc(user_id)
    if user_data:
        user_balance = extract_user_balance(user_data)
        wallets = user_data.get('wallets', {})
        if isinstance(wallets, dict):
            wallet_address = wallets.get('ZNX', '')
        if not wallet_address:
            wallet_address = user_data.get('wallet_address', '') or ''

    return jsonify({
        "success": True,
        "currency": "ZNX",
        "fee_percent": FEE_PERCENT,
        "user_balance": user_balance,
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
    coins = float(data.get('coins', 0))
    wallet_address = str(data.get('wallet_address', '')).strip()

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات طلب السحب غير مكتملة."}), 400

    db = safe_get_db()
    user_ref, user_data = get_user_doc(user_id)

    if not user_ref or not user_data:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    current_balance = extract_user_balance(user_data)

    if coins > current_balance:
        return jsonify({"success": False, "message": "رصيدك غير كافٍ لإتمام عملية السحب."}), 400

    # خصم الرصيد وحساب الصافي بعد الرسوم (5%)
    fee_coins = coins * (FEE_PERCENT / 100.0)
    net_coins = coins - fee_coins
    new_balance = max(0.0, current_balance - coins)

    try:
        user_ref.update({
            'balance': new_balance,
            'znx_balance': new_balance
        })

        tx_ref = db.collection('processed_txs').document()
        tx_id = tx_ref.id
        tx_ref.set({
            'user_id': user_id,
            'coins': coins,
            'fee_coins': fee_coins,
            'net_coins': net_coins,
            'currency': 'ZNX',
            'wallet_address': wallet_address,
            'status': 'pending',
            'created_at': firestore.SERVER_TIMESTAMP
        })

        notify_admin_withdraw(user_id, coins, net_coins, wallet_address, tx_id)

        return jsonify({
            "success": True,
            "message": f"تم تقديم طلب سحب {net_coins:,.0f} ZNX بنجاح وهو قيد المراجعة!",
            "new_balance": new_balance
        }), 200

    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة السحب: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء معالجة الطلب."}), 500

def notify_admin_withdraw(user_id, gross_coins, net_coins, wallet, tx_id):
    bot_token = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not bot_token or not admin_chat_id:
        return

    text = (
        "<b>🚀 طلب سحب ZNX جديد</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>💰 المبلغ الكلي:</b> <code>{gross_coins:,.0f} ZNX</code>\n"
        f"<b>💎 الصافي بعد الرسوم (5%):</b> <code>{net_coins:,.0f} ZNX</code>\n"
        f"<b>📥 محفظة تلجرام:</b> <code>{wallet}</code>\n"
        f"<b>🆔 رقم المعاملة:</b> <code>#{tx_id}</code>\n"
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
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": admin_chat_id, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup},
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ إرسال إشعار السحب للأدمن: {e}")

@withdraw_bp.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json or {}
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_data = cb.get("data", "")
        tx_id = cb_data.replace("approve_tx_", "").replace("reject_tx_", "")
        action = "approve" if cb_data.startswith("approve_tx_") else "reject"

        db = safe_get_db()
        if db and tx_id:
            tx_ref = db.collection('processed_txs').document(tx_id)
            tx_doc = tx_ref.get()
            if tx_doc.exists:
                tx_data = tx_doc.to_dict() or {}
                if action == "approve":
                    tx_ref.update({'status': 'completed'})
                else:
                    tx_ref.update({'status': 'rejected'})
                    user_id = tx_data.get('user_id')
                    coins = tx_data.get('coins', 0)
                    user_ref, _ = get_user_doc(user_id)
                    if user_ref:
                        user_ref.update({
                            'balance': firestore.Increment(coins),
                            'znx_balance': firestore.Increment(coins)
                        })

    return jsonify({"status": "ok"}), 200

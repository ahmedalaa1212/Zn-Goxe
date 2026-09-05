import os
import time
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore

withdraw_bp = Blueprint('withdraw_bp', __name__)

# سعر العملة اللحظي الافتراضي لـ ZNX
ZNX_PRICE_USD = 0.000010
FEE_PERCENT = 5

def _get_firestore_client():
    try:
        from database import get_db
        return get_db()
    except Exception:
        return None

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id') or "5102387551"
    db = _get_firestore_client()
    
    user_balance = 0.0
    wallet_address = ""

    if db and user_id:
        try:
            doc = db.collection('users').document(str(user_id)).get()
            if doc.exists:
                data = doc.to_dict() or {}
                user_balance = float(data.get('balance', data.get('zn_balance', 0.0)))
                wallets = data.get('wallets', {})
                wallet_address = wallets.get('ZNX', data.get('wallet_address', ''))
        except Exception as e:
            print(f"⚠️ خطأ جلب بيانات المستخدم: {e}")

    return jsonify({
        "success": True,
        "currency": "ZNX",
        "fee_percent": FEE_PERCENT,
        "znx_price": ZNX_PRICE_USD,
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

    db = _get_firestore_client()
    if not db:
        return jsonify({"success": False, "message": "خطأ في الاتصال بقاعدة البيانات."}), 500

    try:
        user_ref = db.collection('users').document(str(user_id))
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

    db = _get_firestore_client()
    if not db:
        return jsonify({"success": False, "message": "خطأ بالاتصال بقاعدة البيانات."}), 500

    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()

    if not user_doc.exists:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    user_data = user_doc.to_dict() or {}
    current_balance = float(user_data.get('balance', user_data.get('zn_balance', 0.0)))

    if coins > current_balance:
        return jsonify({"success": False, "message": "رصيدك غير كافٍ لإتمام عملية السحب."}), 400

    # خصم الرصيد وحساب الصافي بعد الرسوم (5%)
    fee_coins = coins * (FEE_PERCENT / 100.0)
    net_coins = coins - fee_coins
    new_balance = current_balance - coins

    try:
        user_ref.update({
            'balance': firestore.Increment(-coins),
            'zn_balance': firestore.Increment(-coins)
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

        # إرسال إشعار الأدمن في تلجرام للموافقة أو التنفيذ
        notify_admin_withdraw(user_id, coins, net_coins, wallet_address, tx_id)

        return jsonify({
            "success": True,
            "message": f"تم تقديم طلب سحب {net_coins:,.0f} ZNX بنجاح وخضع للمراجعة!",
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

        db = _get_firestore_client()
        if db and tx_id:
            tx_ref = db.collection('processed_txs').document(tx_id)
            tx_doc = tx_ref.get()
            if tx_doc.exists:
                tx_data = tx_doc.to_dict() or {}
                if action == "approve":
                    tx_ref.update({'status': 'completed'})
                else:
                    tx_ref.update({'status': 'rejected'})
                    # إعادة الرصيد للمستخدم
                    user_id = tx_data.get('user_id')
                    coins = tx_data.get('coins', 0)
                    db.collection('users').document(str(user_id)).update({
                        'balance': firestore.Increment(coins),
                        'zn_balance': firestore.Increment(coins)
                    })

    return jsonify({"status": "ok"}), 200

import os
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from .withdraw_db import (
    safe_get_db,
    get_user_doc,
    get_user_full_details,
    FEE_USD_FIXED
)

withdraw_bp = Blueprint('withdraw_bp', __name__)

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id') or "5102387551"
    
    details = get_user_full_details(user_id)
    if not details:
        return jsonify({
            "success": False,
            "message": "المستخدم غير موجود."
        }), 404

    return jsonify({
        "success": True,
        "currency": "ZNX",
        "fee_usd": FEE_USD_FIXED,
        "user_balance": details['znx_balance'],
        "znx_balance": details['znx_balance'],
        "usd_balance": details['usd_balance'],
        "total_converted_znx": details['total_converted_znx'],
        "active_tier": details['active_tier'],
        "wallet_address": details['wallet_address']
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

    details = get_user_full_details(user_id)
    if not details:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    user_ref, user_data = get_user_doc(user_id)
    if not user_ref or not user_data:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    current_znx = details['znx_balance']
    current_usd = details['usd_balance']
    active_tier = details['active_tier']
    min_znx_required = active_tier['min_znx']

    # 1. التحقق من الحد الأدنى للشريحة الحالية
    if coins < min_znx_required:
        return jsonify({
            "success": False,
            "message": f"الحد الأدنى للسحب في {active_tier['name']} هو {min_znx_required:,.2f} ZNX."
        }), 400

    # 2. التحقق من رصيد ZNX
    if coins > current_znx:
        return jsonify({"success": False, "message": "رصيدك من ZNX غير كافٍ لإتمام عملية السحب."}), 400

    # 3. التحقق من رصيد الدولار لسداد الرسوم (0.02$)
    if current_usd < FEE_USD_FIXED:
        return jsonify({
            "success": False,
            "message": f"رصيدك غير كافٍ من الدولار لسداد رسوم السحب (0.02$). رصيدك الحالي: {current_usd:.4f}$"
        }), 400

    # خصم ZNX ورسوم الدولار 0.02$
    new_znx_balance = max(0.0, current_znx - coins)
    new_usd_balance = max(0.0, current_usd - FEE_USD_FIXED)

    db = safe_get_db()
    try:
        user_ref.update({
            'znx_balance': new_znx_balance,
            'usd_balance': new_usd_balance
        })

        tx_ref = db.collection('processed_txs').document()
        tx_id = tx_ref.id
        tx_ref.set({
            'user_id': user_id,
            'coins': coins,
            'fee_usd': FEE_USD_FIXED,
            'tier': active_tier['tier'],
            'tier_name': active_tier['name'],
            'currency': 'ZNX',
            'wallet_address': wallet_address,
            'status': 'pending',
            'created_at': firestore.SERVER_TIMESTAMP
        })

        notify_admin_withdraw(user_id, coins, FEE_USD_FIXED, wallet_address, tx_id, active_tier['name'])

        return jsonify({
            "success": True,
            "message": f"تم تقديم طلب سحب {coins:,.4f} ZNX بنجاح وهو قيد المراجعة!",
            "new_balance": new_znx_balance,
            "new_usd_balance": new_usd_balance
        }), 200

    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة السحب: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء معالجة الطلب."}), 500

def notify_admin_withdraw(user_id, coins, fee_usd, wallet, tx_id, tier_name):
    bot_token = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not bot_token or not admin_chat_id:
        return

    text = (
        "<b>🚀 طلب سحب ZNX جديد</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 المستخدم:</b> <code>{user_id}</code>\n"
        f"<b>📊 الشريحة:</b> <code>{tier_name}</code>\n"
        f"<b>💰 كمية السحب:</b> <code>{coins:,.4f} ZNX</code>\n"
        f"<b>💵 رسوم الدولار المقتطعة:</b> <code>${fee_usd:.2f}</code>\n"
        f"<b>📥 محفظة TON:</b> <code>{wallet}</code>\n"
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
                    fee_usd = tx_data.get('fee_usd', FEE_USD_FIXED)
                    user_ref, _ = get_user_doc(user_id)
                    if user_ref:
                        user_ref.update({
                            'znx_balance': firestore.Increment(coins),
                            'usd_balance': firestore.Increment(fee_usd)
                        })

    return jsonify({"status": "ok"}), 200

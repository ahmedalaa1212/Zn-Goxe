import os
import sys
import html
import asyncio
import requests
import time
import concurrent.futures
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from .withdraw_db import (
    safe_get_db, 
    get_user_doc, 
    get_user_full_details,
    extract_user_balance, 
    extract_usd_balance, 
    get_current_withdraw_tier,
    ZNX_CONTRACT_ADDRESS
)

withdraw_bp = Blueprint('withdraw_bp', __name__)

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
PROOF_CHANNEL_ID = os.getenv("PROOF_CHANNEL_ID", "@zngoxe_Proofs")

def send_proof_to_channel(user_id, coins, wallet_address, tx_id):
    """نشر إثبات السحب في قناة التوثيق الرسمية بدون صورة أو كارت رابط"""
    if not BOT_TOKEN or not PROOF_CHANNEL_ID:
        return

    # إخفاء جزء من معرّف المستخدم للحفاظ على الخصوصية
    uid_str = str(user_id).strip()
    masked_uid = f"{uid_str[:2]}****{uid_str[-3:]}" if len(uid_str) >= 6 else uid_str

    # إخفاء جزء من عنوان المحفظة
    w_str = str(wallet_address).strip()
    masked_wallet = f"{w_str[:5]}...{w_str[-4:]}" if len(w_str) >= 12 else w_str

    # رابط التحقق المباشر للمعاملة/المحفظة على شبكة TON
    verify_url = f"https://tonviewer.com/{wallet_address}"

    proof_text = (
        "🎉 <b>إثبات سحب جديد من تطبيق ZN Goxe!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>المستخدم:</b> <code>{masked_uid}</code>\n"
        f"💰 <b>المبلغ المسحوب:</b> <code>{coins:,.2f} ZNX</code>\n"
        f"💎 <b>الصافي المستلم:</b> <code>{coins:,.2f} ZNX</code>\n"
        f"📫 <b>المحفظة:</b> <code>{masked_wallet}</code>\n"
        f"🆔 <b>رقم المعاملة:</b> <code>#{tx_id[:12]}</code>\n\n"
        "✅ <b>تم التحويل بنجاح عبر شبكة TON</b>\n\n"
        f'🔗 <a href="{verify_url}">اضغط هنا للتحقق من وصول الرصيد في حسابه عبر المستكشف 🔍</a>\n\n'
        f"📢 <b>قناة إثباتات السحب الرسمية:</b>\n{PROOF_CHANNEL_ID}"
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "🔍 التحقق من المعاملة عبر Blockchain", "url": verify_url}
            ]
        ]
    }

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": PROOF_CHANNEL_ID,
                "text": proof_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True,
                "link_preview_options": {"is_disabled": True}
            },
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ أثناء إرسال منشور الإثبات للقناة: {e}")

def execute_admin_decision(tx_id, action, admin_id=None):
    """تنفيذ قرار المشرف وتحديث Firestore ومزامنة السجلات العامة ونشر الإثبات"""
    db = safe_get_db()
    if not db or not tx_id:
        return False, "خطأ في الاتصال بقاعدة البيانات!"

    tx_ref = db.collection('processed_txs').document(tx_id)

    @firestore.transactional
    def lock_and_claim_tx(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False, "لم يتم العثور على طلب السحب في قاعدة البيانات!", None

        data = snapshot.to_dict() or {}
        current_status = data.get('status', 'pending')

        if current_status == 'completed':
            return False, "هذه المعاملة تم قبولها مسبقاً!", None
        elif current_status == 'rejected':
            return False, "هذه المعاملة تم رفضها مسبقاً وإعادة الرصيد للمستخدم!", None
        elif current_status == 'processing':
            p_started = data.get('processing_started_at')
            is_stuck = False
            if p_started:
                try:
                    if hasattr(p_started, 'timestamp'):
                        stuck_seconds = time.time() - p_started.timestamp()
                        if stuck_seconds > 15:
                            is_stuck = True
                except Exception:
                    is_stuck = True
            else:
                is_stuck = True

            if not is_stuck:
                return False, "هذه المعاملة قيد المعالجة حالياً من قِبل المشرف!", None

        transaction.update(ref, {
            'status': 'processing',
            'processing_started_at': firestore.SERVER_TIMESTAMP
        })
        return True, "OK", data

    try:
        transaction = db.transaction()
        claimed, err_msg, tx_data = lock_and_claim_tx(transaction, tx_ref)
        if not claimed:
            return False, err_msg

        user_id = tx_data.get('user_id')
        coins = float(tx_data.get('coins', 0))
        fee_usd = float(tx_data.get('fee_usd', 0.02))
        wallet_address = tx_data.get('wallet_address', '')
        new_status = 'completed' if action == "approve" else 'rejected'
        processed_by = str(admin_id) if admin_id else 'admin'

        update_payload = {
            'status': new_status,
            'processed_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP,
            'processed_by': processed_by
        }

        if action == "approve":
            # تم القبول يدوياً
            tx_ref.update(update_payload)
            res_msg = f"🟢 تم قبول طلب السحب بنجاح! تم اعتماد خصم {coins:,.2f} ZNX ونشر إثبات السحب بنجاح."
            # إرسال منشور الإثبات في القناة
            send_proof_to_channel(user_id, coins, wallet_address, tx_id)
        else:
            # عند الرفض: إرجاع الرصيد
            tx_ref.update(update_payload)
            user_ref, _ = get_user_doc(user_id)
            if user_ref:
                user_ref.update({
                    'znx_balance': firestore.Increment(coins),
                    'usd_balance': firestore.Increment(fee_usd)
                })
            res_msg = "🔴 تم رفض الطلب وإعادة الرصيد بالكامل إلى حساب المستخدم بنجاح!"

        # مزامنة السجلات لجميع المجموعات
        try:
            db.collection('transactions').document(tx_id).update(update_payload)
        except Exception:
            pass

        try:
            if user_id:
                db.collection('users').document(user_id).collection('transactions').document(tx_id).update(update_payload)
        except Exception:
            pass

        try:
            db.collection('admin_logs').add({
                'action': f"withdraw_{action}",
                'tx_id': tx_id,
                'user_id': user_id,
                'admin_id': processed_by,
                'status': new_status,
                'amount': coins,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        except Exception:
            pass

        return True, res_msg

    except Exception as e:
        print(f"⚠️ خطأ أثناء تنفيذ قرار السحب: {e}")
        try:
            tx_ref.update({'status': 'pending'})
        except Exception:
            pass
        return False, f"حدث خطأ أثناء المعالجة: {str(e)}"

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

        tx_record = {
            'id': tx_id,
            'tx_id': tx_id,
            'user_id': user_id,
            'coins': coins,
            'amount': coins,
            'fee_usd': fixed_fee_usd,
            'net_coins': coins,
            'currency': 'ZNX',
            'tier_name': tier_info.get('name', ''),
            'wallet_address': wallet_address,
            'type': 'withdraw',
            'status': 'pending',
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP,
            'timestamp': firestore.SERVER_TIMESTAMP
        }

        # حفظ الطلب في السجل الرئيسي والموازي لضمان المزامنة التامة
        tx_ref.set(tx_record)
        db.collection('transactions').document(tx_id).set(tx_record)
        db.collection('users').document(user_id).collection('transactions').document(tx_id).set(tx_record)

        notify_admin_withdraw(user_id, coins, fixed_fee_usd, wallet_address, tx_id, tier_info.get('name', ''))

        return jsonify({
            "success": True,
            "message": f"تم تقديم طلب سحب {coins:,.4f} ZNX بنجاح وهو قيد المراجعة!",
            "new_balance": new_znx_balance,
            "new_usd_balance": new_usd_balance
        }), 200

    except Exception as e:
        print(f"⚠️ خطأ معالجة السحب المالي: {e}")
        return jsonify({"success": False, "message": "تعذر إجراء السحب، يرجى إعادة المحاولة."}), 500

def notify_admin_withdraw(user_id, coins, fee_usd, wallet, tx_id, tier_name):
    """إرسال إشعار شامل ببيانات المستخدم مع زر نسخ المحفظة المباشر"""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return

    full_details = get_user_full_details(user_id) or {}
    
    first_name = html.escape(str(full_details.get('first_name', 'غير محدد')))
    username = html.escape(str(full_details.get('username', 'لا يوجد')))
    joined_at = html.escape(str(full_details.get('joined_at', 'غير محدد')))
    
    znx_bal = full_details.get('znx_balance', 0.0)
    zn_bal = full_details.get('zn_balance', 0.0)
    
    hourly_rate = full_details.get('hourly_rate', 0.0)
    storage_lvl = full_details.get('storage_level', 1)
    upgrades_cnt = full_details.get('upgrades_count', 0)
    ref_cnt = full_details.get('ref_count', 0)

    text = (
        "🚀 <b>طلب سحب ZNX جديد (تحويل يدوي)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> <code>{html.escape(str(user_id))}</code> ({first_name} | @{username})\n"
        f"📅 <b>تاريخ الانضمام:</b> <code>{joined_at}</code>\n\n"
        f"💰 <b>رصيد ZNX الكلي:</b> <code>{znx_bal:,.4f} ZNX</code>\n"
        f"💎 <b>رصيد ZN الحالي:</b> <code>{zn_bal:,.4f} ZN</code>\n\n"
        f"⚡ <b>سرعة التعدين:</b> <code>{hourly_rate:g} ZN/h</code>\n"
        f"📦 <b>المخزن / الترقيات:</b> level <code>{storage_lvl}</code> (ترقيات: <code>{upgrades_cnt}</code>)\n"
        f"👥 <b>عدد الإحالات:</b> <code>{ref_cnt}</code> صديق\n\n"
        f"📊 <b>الشريحة:</b> {html.escape(str(tier_name))}\n"
        f"💵 <b>المبلغ المطلوب سحبه:</b> <code>{coins:,.4f} ZNX</code>\n"
        f"💸 <b>الرسوم المقتطعة:</b> <code>${fee_usd:.2f} USD</code>\n\n"
        f"📥 <b>عنوان المحفظة المحول عليها:</b>\n<code>{html.escape(str(wallet))}</code>\n\n"
        f"🆔 <b>رقم المعاملة:</b> <code>{html.escape(str(tx_id))}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "قبول 🟢", "callback_data": f"approve_tx_{tx_id}"},
                {"text": "رفض 🔴", "callback_data": f"reject_tx_{tx_id}"}
            ],
            [
                {"text": "📋 نسخ عنوان المحفظة", "copy_text": {"text": str(wallet)}}
            ]
        ]
    }

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup},
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ إرسال إشعار السحب للأدمن: {e}")

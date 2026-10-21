# -*- coding: utf-8 -*-
import os
import html
import math
import time
import uuid
import hmac
import hashlib
import threading
import requests
from urllib.parse import parse_qsl
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from psycopg2.extras import RealDictCursor
from .withdraw_db import (
    get_db_connection,
    _sanitize_id,
    safe_get_db,
    get_user_doc,
    get_user_full_details,
    extract_user_balance,
    extract_usd_balance,
    get_current_withdraw_tier,
    save_user_wallet,
    is_valid_ton_address,
    _parse_json_val,
    ZNX_CONTRACT_ADDRESS
)

withdraw_bp = Blueprint("withdraw_bp", __name__)

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN")
USER_BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
PROOF_CHANNEL_ID = os.getenv("PROOF_CHANNEL_ID", "@zngoxe_Proofs")
STRICT_TG_AUTH = os.getenv("STRICT_TG_AUTH", "false").lower() == "true"

# --- نظام الحماية من التكرار والسبام (Anti-Race Condition & Anti-Spam Locks) ---
_GLOBAL_LOCK = threading.Lock()
_USER_LOCKS: dict[str, threading.Lock] = {}
_TX_LOCKS: dict[str, threading.Lock] = {}
_USER_LAST_REQUEST: dict[str, float] = {}
WITHDRAW_COOLDOWN_SECONDS = 5.0


def _get_user_lock(user_id: str) -> threading.Lock:
    with _GLOBAL_LOCK:
        if user_id not in _USER_LOCKS:
            _USER_LOCKS[user_id] = threading.Lock()
        return _USER_LOCKS[user_id]


def _get_tx_lock(tx_id: str) -> threading.Lock:
    with _GLOBAL_LOCK:
        if tx_id not in _TX_LOCKS:
            _TX_LOCKS[tx_id] = threading.Lock()
        return _TX_LOCKS[tx_id]


def verify_telegram_webapp_data(init_data: str, expected_user_id: str) -> bool:
    """
    التحقق التشفيري من صحة جلسة Telegram WebApp (HMAC-SHA256)
    لمنع أي هكر من تزوير user_id عبر Postman.
    """
    if not init_data:
        return not STRICT_TG_AUTH

    if not USER_BOT_TOKEN:
        return True

    try:
        raw_init = init_data.replace("Bearer ", "").strip()
        parsed_data = dict(parse_qsl(raw_init, keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            return not STRICT_TG_AUTH

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )
        secret_key = hmac.new(
            b"WebAppData", USER_BOT_TOKEN.encode("utf-8"), hashlib.sha256
        ).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return False

        user_json = parsed_data.get("user", "")
        if expected_user_id and f'"{expected_user_id}"' not in user_json and f":{expected_user_id}" not in user_json:
            return False

        return True
    except Exception as e:
        print(f"⚠️ خطأ التحقق من توقيع تيليجرام: {e}")
        return not STRICT_TG_AUTH


def send_proof_to_channel(user_id, coins, wallet_address, tx_id):
    """نشر إثبات السحب في قناة التوثيق الرسمية بدون صورة أو كارت رابط"""
    if not BOT_TOKEN or not PROOF_CHANNEL_ID:
        return

    uid_str = str(user_id).strip()
    masked_uid = f"{uid_str[:2]}****{uid_str[-3:]}" if len(uid_str) >= 6 else uid_str

    w_str = str(wallet_address).strip()
    masked_wallet = f"{w_str[:5]}...{w_str[-4:]}" if len(w_str) >= 12 else w_str

    verify_url = f"https://tonviewer.com/{wallet_address}"

    proof_text = (
        "🎉 <b>إثبات سحب جديد من تطبيق ZN Goxe!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>المستخدم:</b> <code>{html.escape(masked_uid)}</code>\n"
        f"💰 <b>المبلغ المسحوب:</b> <code>{coins:,.2f} ZNX</code>\n"
        f"💎 <b>الصافي المستلم:</b> <code>{coins:,.2f} ZNX</code>\n"
        f"📫 <b>المحفظة:</b> <code>{html.escape(masked_wallet)}</code>\n"
        f"🆔 <b>رقم المعاملة:</b> <code>#{html.escape(str(tx_id)[:12])}</code>\n\n"
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
    """
    تنفيذ قرار المشرف (قبول / رفض) وتحديث Supabase PostgreSQL ذرياً عبر FOR UPDATE
    مع حماية كاملة ضد الضغط المزدوج (Double Click & Race Condition Protection).
    """
    clean_tx_id = str(tx_id or "").strip()
    if not safe_get_db() or not get_db_connection or not clean_tx_id:
        return False, "خطأ في الاتصال بقاعدة البيانات!"

    if action not in ("approve", "reject"):
        return False, "إجراء غير صالح!"

    tx_lock = _get_tx_lock(clean_tx_id)
    if not tx_lock.acquire(blocking=False):
        return False, "هذه المعاملة قيد المعالجة حالياً من قِبل المشرف!"

    conn = None
    try:
        processed_by = str(admin_id) if admin_id else "admin"
        new_status = "completed" if action == "approve" else "rejected"

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. قفل صف المعاملة في قاعدة البيانات ذرياً (FOR UPDATE) لمنع أي تداخل
                cur.execute("""
                    SELECT * FROM processed_txs
                    WHERE tx_id = %s OR id = %s
                    LIMIT 1
                    FOR UPDATE
                """, (clean_tx_id, clean_tx_id))
                tx_data = cur.fetchone()

                if not tx_data:
                    conn.rollback()
                    return False, "لم يتم العثور على طلب السحب في قاعدة البيانات!"

                current_status = str(tx_data.get("status") or "pending").lower()
                if current_status == "completed":
                    conn.rollback()
                    return False, "هذه المعاملة تم قبولها مسبقاً!"
                elif current_status == "rejected":
                    conn.rollback()
                    return False, "هذه المعاملة تم رفضها مسبقاً وإعادة الرصيد للمستخدم!"

                user_id = _sanitize_id(tx_data.get("user_id"))
                coins = float(tx_data.get("coins", 0.0) or 0.0)
                fee_usd = float(tx_data.get("fee_usd", 0.02) or 0.02)
                wallet_address = str(tx_data.get("wallet_address") or "")

                # 2. في حالة الرفض: إرجاع الرصيد للمستخدم داخل نفس الـ Transaction الذرية
                if action == "reject" and user_id:
                    cur.execute("""
                        UPDATE users
                        SET znx_balance = ROUND(CAST(GREATEST(0.0, COALESCE(znx_balance, 0.0)) + %s AS NUMERIC), 6),
                            usd_balance = ROUND(CAST(GREATEST(0.0, COALESCE(usd_balance, 0.0)) + %s AS NUMERIC), 4),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE CAST(tg_id AS TEXT) = %s
                           OR CAST(user_id AS TEXT) = %s
                           OR CAST(telegram_id AS TEXT) = %s
                    """, (coins, fee_usd, user_id, user_id, user_id))

                # 3. تحديث حالة الطلب في جدول processed_txs
                cur.execute("""
                    UPDATE processed_txs
                    SET status = %s,
                        processed_by = %s,
                        processed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tx_id = %s OR id = %s
                """, (new_status, processed_by, clean_tx_id, clean_tx_id))

                # 4. مزامنة حالة الطلب في جدول المعاملات العام transactions
                cur.execute("""
                    UPDATE transactions
                    SET status = %s,
                        processed_by = %s,
                        processed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tx_id = %s OR id = %s
                """, (new_status, processed_by, clean_tx_id, clean_tx_id))

                # 5. توثيق قرار المشرف في جدول admin_logs
                cur.execute("""
                    INSERT INTO admin_logs (action, tx_id, user_id, admin_id, status, amount, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (f"withdraw_{action}", clean_tx_id, user_id, processed_by, new_status, coins))

            conn.commit()

        if action == "approve":
            send_proof_to_channel(user_id, coins, wallet_address, clean_tx_id)
            res_msg = f"🟢 تم قبول طلب السحب بنجاح! تم اعتماد خصم {coins:,.2f} ZNX ونشر إثبات السحب بنجاح."
        else:
            res_msg = "🔴 تم رفض الطلب وإعادة الرصيد بالكامل إلى حساب المستخدم بنجاح!"

        return True, res_msg

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"⚠️ خطأ أثناء تنفيذ قرار السحب في Supabase PostgreSQL: {e}")
        return False, f"حدث خطأ أثناء المعالجة: {str(e)}"
    finally:
        tx_lock.release()


@withdraw_bp.route("/config", methods=["GET"])
def get_config():
    user_id = _sanitize_id(request.args.get("user_id"))

    user_balance = 0.0
    usd_balance = 0.0
    wallet_address = ""

    if user_id:
        _, user_data = get_user_doc(user_id)
        if user_data:
            user_balance = extract_user_balance(user_data)
            usd_balance = extract_usd_balance(user_data)
            wallets = _parse_json_val(user_data.get("wallets"), {})
            if isinstance(wallets, dict):
                wallet_address = wallets.get("ZNX", "")
            if not wallet_address:
                wallet_address = user_data.get("wallet_address", "") or ""

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


@withdraw_bp.route("/save-wallet", methods=["POST"])
def handle_save_wallet():
    data = request.get_json(silent=True) or {}
    user_id = _sanitize_id(data.get("user_id"))
    wallet_address = str(data.get("wallet_address", "")).strip()
    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.headers.get("X-Init-Data")
        or data.get("init_data", "")
    )

    if not user_id or not wallet_address:
        return jsonify({"success": False, "message": "يرجى إدخال عنوان المحفظة بشكل صحيح."}), 400

    if not verify_telegram_webapp_data(init_data, user_id):
        return jsonify({"success": False, "message": "فشل التحقق من جلسة الأمان الخاصة بك."}), 403

    if not is_valid_ton_address(wallet_address):
        return jsonify({
            "success": False,
            "message": "عنوان المحفظة غير صالح! يجب أن يكون عنوان TON يبدأ بـ EQ أو UQ."
        }), 400

    ok, msg = save_user_wallet(user_id, "ZNX", wallet_address)
    if ok:
        return jsonify({"success": True, "message": "تم حفظ المحفظة بنجاح!"}), 200
    return jsonify({"success": False, "message": msg}), 400


@withdraw_bp.route("/request", methods=["POST"])
def handle_withdraw():
    data = request.get_json(silent=True) or {}
    user_id = _sanitize_id(data.get("user_id"))
    wallet_address = str(data.get("wallet_address", "")).strip()
    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.headers.get("X-Init-Data")
        or data.get("init_data", "")
    )

    if not user_id or not wallet_address:
        return jsonify({"success": False, "message": "بيانات طلب السحب غير مكتملة."}), 400

    # 1. التحقق من صحة الجلسة والأرقام المدخلة لمنع التلاعب
    if not verify_telegram_webapp_data(init_data, user_id):
        return jsonify({"success": False, "message": "جلسة غير مصرح بها، يرجى إعادة فتح التطبيق من تيليجرام."}), 403

    try:
        coins = float(data.get("coins", 0))
        if math.isnan(coins) or math.isinf(coins) or coins <= 0:
            raise ValueError("Invalid float")
        coins = round(coins, 4)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "مبلغ السحب غير صالح."}), 400

    if not is_valid_ton_address(wallet_address):
        return jsonify({"success": False, "message": "عنوان محفظة TON غير صالح!"}), 400

    if not safe_get_db() or not get_db_connection:
        return jsonify({"success": False, "message": "خطأ في الاتصال بقاعدة البيانات."}), 500

    tier_info = get_current_withdraw_tier()
    min_withdraw = float(tier_info.get("min_withdraw_znx", 1000.0))
    fixed_fee_usd = float(tier_info.get("fixed_fee_usd", 0.02))
    tier_name = str(tier_info.get("name", ""))

    if coins < min_withdraw:
        return jsonify({
            "success": False,
            "code": "BELOW_MINIMUM",
            "message": f"الحد الأدنى للسحب بالشريحة الحالية هو {min_withdraw:g} ZNX."
        }), 400

    # 2. قفل المستخدم برمجياً لمنع الهجمات المتزامنة (Thread Lock)
    user_lock = _get_user_lock(user_id)
    if not user_lock.acquire(blocking=False):
        return jsonify({
            "success": False,
            "message": "لديك عملية قيد التنفيذ حالياً، يرجى الانتظار لحظات."
        }), 429

    conn = None
    try:
        now_ts = time.time()
        last_req = _USER_LAST_REQUEST.get(user_id, 0)
        if now_ts - last_req < WITHDRAW_COOLDOWN_SECONDS:
            return jsonify({
                "success": False,
                "message": "يرجى الانتظار بضع ثوانٍ قبل إرسال طلب سحب آخر."
            }), 429

        tx_id = uuid.uuid4().hex[:20]

        # 3. معاملة قاعدة بيانات ذرية مع قفل صف المستخدم (SELECT ... FOR UPDATE)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # قفل صف المستخدم حتى تنتهي المعاملة بالكامل لمنع Double Spending
                cur.execute("""
                    SELECT * FROM users
                    WHERE CAST(tg_id AS TEXT) = %s
                       OR CAST(user_id AS TEXT) = %s
                       OR CAST(telegram_id AS TEXT) = %s
                    LIMIT 1
                    FOR UPDATE
                """, (user_id, user_id, user_id))
                user_data = cur.fetchone()

                if not user_data:
                    conn.rollback()
                    return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

                if bool(user_data.get("is_banned", False)):
                    conn.rollback()
                    return jsonify({"success": False, "message": "حسابك معطل ولا يمكنك إجراء عمليات سحب."}), 403

                # التحقق من عدم وجود طلب سحب معلق لنفس المستخدم لمنع إغراق الأدمن بالطلبات
                cur.execute("""
                    SELECT tx_id FROM processed_txs
                    WHERE user_id = %s AND status IN ('pending', 'processing')
                    LIMIT 1
                """, (user_id,))
                if cur.fetchone():
                    conn.rollback()
                    return jsonify({
                        "success": False,
                        "message": "لديك طلب سحب قيد المراجعة بالفعل! يرجى انتظار مراجعة طلبك الحالي أولاً."
                    }), 400

                current_balance = extract_user_balance(user_data)
                usd_balance = extract_usd_balance(user_data)

                if coins > current_balance:
                    conn.rollback()
                    return jsonify({
                        "success": False,
                        "code": "INSUFFICIENT_ZNX",
                        "message": "رصيدك من عملة ZNX غير كافٍ لإتمام عملية السحب."
                    }), 400

                if usd_balance < fixed_fee_usd:
                    conn.rollback()
                    return jsonify({
                        "success": False,
                        "code": "INSUFFICIENT_USD",
                        "fee_required": fixed_fee_usd,
                        "message": f"رسوم السحب لا تكفي! يجب إيداع مبلغ رسوم السحب ${fixed_fee_usd:.2f} USD لإتمام العملية."
                    }), 400

                # 4. خصم الرصيد ذرياً بشرط توفر الرصيد الكافي في اللحظة نفسها
                cur.execute("""
                    UPDATE users
                    SET znx_balance = ROUND(CAST(COALESCE(znx_balance, 0.0) - %s AS NUMERIC), 6),
                        usd_balance = ROUND(CAST(COALESCE(usd_balance, 0.0) - %s AS NUMERIC), 4),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE (CAST(tg_id AS TEXT) = %s OR CAST(user_id AS TEXT) = %s OR CAST(telegram_id AS TEXT) = %s)
                      AND COALESCE(znx_balance, 0.0) >= %s
                      AND COALESCE(usd_balance, 0.0) >= %s
                    RETURNING znx_balance, usd_balance
                """, (coins, fixed_fee_usd, user_id, user_id, user_id, coins, fixed_fee_usd))
                updated_row = cur.fetchone()

                if not updated_row:
                    conn.rollback()
                    return jsonify({
                        "success": False,
                        "message": "تغير رصيدك أثناء المعالجة، يرجى المحاولة مرة أخرى."
                    }), 409

                new_znx_balance = float(updated_row.get("znx_balance", 0.0) or 0.0)
                new_usd_balance = float(updated_row.get("usd_balance", 0.0) or 0.0)

                # 5. إدراج سجل السحب في processed_txs
                cur.execute("""
                    INSERT INTO processed_txs (
                        id, tx_id, user_id, coins, amount, fee_usd, net_coins,
                        currency, tier_name, wallet_address, type, status,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        'ZNX', %s, %s, 'withdraw', 'pending',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """, (
                    tx_id, tx_id, user_id, coins, coins, fixed_fee_usd, coins,
                    tier_name, wallet_address
                ))

                # 6. إدراج السجل الموازي في جدول المعاملات العام transactions
                cur.execute("""
                    INSERT INTO transactions (
                        id, tx_id, user_id, coins, amount, fee_usd, net_coins,
                        currency, tier_name, wallet_address, type, status,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        'ZNX', %s, %s, 'withdraw', 'pending',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (id) DO NOTHING
                """, (
                    tx_id, tx_id, user_id, coins, coins, fixed_fee_usd, coins,
                    tier_name, wallet_address
                ))

            conn.commit()

        _USER_LAST_REQUEST[user_id] = time.time()

        notify_admin_withdraw(
            user_id, coins, fixed_fee_usd, wallet_address, tx_id, tier_name
        )

        return jsonify({
            "success": True,
            "tx_id": tx_id,
            "message": f"تم تقديم طلب سحب {coins:,.4f} ZNX بنجاح وهو قيد المراجعة!",
            "new_balance": new_znx_balance,
            "new_usd_balance": new_usd_balance
        }), 200

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"⚠️ خطأ معالجة السحب المالي في Supabase: {e}")
        return jsonify({"success": False, "message": "تعذر إجراء السحب، يرجى إعادة المحاولة."}), 500
    finally:
        user_lock.release()


def notify_admin_withdraw(user_id, coins, fee_usd, wallet, tx_id, tier_name):
    """إرسال إشعار شامل ببيانات المستخدم للأدمن مع أزرار القبول والرفض ونسخ المحفظة"""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return

    full_details = get_user_full_details(user_id) or {}

    first_name = html.escape(str(full_details.get("first_name", "غير محدد")))
    username = html.escape(str(full_details.get("username", "لا يوجد")))
    joined_at = html.escape(str(full_details.get("joined_at", "غير محدد")))

    znx_bal = full_details.get("znx_balance", 0.0)
    zn_bal = full_details.get("zn_balance", 0.0)

    hourly_rate = full_details.get("hourly_rate", 0.0)
    storage_lvl = full_details.get("storage_level", 1)
    upgrades_cnt = full_details.get("upgrades_count", 0)
    ref_cnt = full_details.get("ref_count", 0)

    text = (
        "🚀 <b>طلب سحب ZNX جديد (تحويل يدوي)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> <code>{html.escape(str(user_id))}</code> ({first_name} | @{username})\n"
        f"📅 <b>تاريخ الانضمام:</b> <code>{joined_at}</code>\n\n"
        f"💰 <b>رصيد ZNX المتبقي:</b> <code>{znx_bal:,.4f} ZNX</code>\n"
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
            json={
                "chat_id": ADMIN_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup
            },
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ إرسال إشعار السحب للأدمن: {e}")

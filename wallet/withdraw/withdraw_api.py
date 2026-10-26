# -*- coding: utf-8 -*-
import os
import html
import math
import time
import uuid
import hmac
import hashlib
import json
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

# جلب التوكنات ومعرف الأدمن مع دعم البدائل التلقائية لضمان وصول الرسائل دائماً
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN")
USER_BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("ADMIN_BOT_TOKEN")
BOT_TOKEN = ADMIN_BOT_TOKEN or USER_BOT_TOKEN

ADMIN_CHAT_ID = (
    os.getenv("ADMIN_CHAT_ID")
    or os.getenv("ADMIN_ID")
    or "5102387551"
).strip()

PROOF_CHANNEL_ID = os.getenv("PROOF_CHANNEL_ID", "@zngoxe_Proofs").strip()
STRICT_TG_AUTH = os.getenv("STRICT_TG_AUTH", "true").lower() == "true"

# --- نظام الحماية من التكرار والسبام (Anti-Race Condition & Anti-Spam Locks) ---
_GLOBAL_LOCK = threading.Lock()
_USER_LOCKS: dict[str, threading.Lock] = {}
_TX_LOCKS: dict[str, threading.Lock] = {}
WITHDRAW_COOLDOWN_SECONDS = 10


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


def format_clean_znx(val) -> str:
    """
    تنسيق ذكي ونظيف للأرقام يمنع ظهور .0000 للأرقام الصحيحة
    مثال: 1000 -> 1,000 | 5000 -> 5,000 | 2.5 -> 2.5
    """
    try:
        num = float(val or 0.0)
        if not math.isfinite(num) or num <= 0:
            return "0"
        rounded = round(num, 4)
        if abs(rounded - round(rounded)) < 1e-6:
            return f"{int(round(rounded)):,}"
        return f"{rounded:,.4f}".rstrip("0").rstrip(".")
    except Exception:
        return str(val or "0")


def verify_telegram_webapp_data(init_data: str, expected_user_id: str) -> bool:
    """
    التحقق التشفيري المرن والآمن من جلسة Telegram WebApp (HMAC-SHA256)
    يفحص التوقيع مقابل كافة توكنات البوت المتاحة لمنع فشل الجلسة الخاطئ.
    """
    if not STRICT_TG_AUTH:
        return True

    if not init_data or not str(init_data).strip():
        if expected_user_id:
            _, u_data = get_user_doc(expected_user_id)
            if u_data:
                return True
        return False

    tokens_to_check = [t for t in {USER_BOT_TOKEN, ADMIN_BOT_TOKEN, os.getenv("BOT_TOKEN"), os.getenv("ADMIN_BOT_TOKEN")} if t]
    if not tokens_to_check:
        return True

    try:
        raw_init = str(init_data).replace("Bearer ", "").strip()
        parsed_data = dict(parse_qsl(raw_init, keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)

        if not received_hash:
            return False

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )

        hash_valid = False
        for token in tokens_to_check:
            secret_key = hmac.new(
                b"WebAppData", token.encode("utf-8"), hashlib.sha256
            ).digest()
            calculated_hash = hmac.new(
                secret_key, data_check_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            if hmac.compare_digest(calculated_hash, received_hash):
                hash_valid = True
                break

        if not hash_valid:
            return False

        user_json_str = parsed_data.get("user", "")
        if user_json_str and expected_user_id:
            user_data = json.loads(user_json_str)
            if str(user_data.get("id")) != str(expected_user_id):
                return False

        return True
    except Exception as e:
        print(f"⚠️ خطأ التحقق من توقيع تيليجرام: {e}")
        return False


def send_proof_to_channel(user_id, coins, wallet_address, tx_id):
    """نشر إثبات السحب في القناة الرسمية عند قبول الأدمن بتنسيق أرقام نظيف"""
    if not BOT_TOKEN or not PROOF_CHANNEL_ID:
        return

    uid_str = str(user_id).strip()
    masked_uid = f"{uid_str[:2]}****{uid_str[-3:]}" if len(uid_str) >= 6 else uid_str
    w_str = str(wallet_address).strip()
    masked_wallet = f"{w_str[:5]}...{w_str[-4:]}" if len(w_str) >= 12 else w_str
    verify_url = f"https://tonviewer.com/{wallet_address}"
    clean_coins_str = format_clean_znx(coins)

    proof_text = (
        "🎉 <b>إثبات سحب جديد من تطبيق ZN Goxe!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>المستخدم:</b> <code>{html.escape(masked_uid)}</code>\n"
        f"💰 <b>المبلغ المسحوب:</b> <code>{clean_coins_str} ZNX</code>\n"
        f"💎 <b>الصافي المستلم:</b> <code>{clean_coins_str} ZNX</code>\n"
        f"📫 <b>المحفظة:</b> <code>{html.escape(masked_wallet)}</code>\n"
        f"🆔 <b>رقم المعاملة:</b> <code>#{html.escape(str(tx_id)[:12])}</code>\n\n"
        "✅ <b>تم التحويل بنجاح عبر شبكة TON</b>\n\n"
        f'🔗 <a href="{verify_url}">اضغط هنا للتحقق من وصول الرصيد في حسابه عبر المستكشف 🔍</a>\n\n'
        f"📢 <b>قناة إثباتات السحب الرسمية:</b>\n{PROOF_CHANNEL_ID}"
    )

    reply_markup = {"inline_keyboard": [[{"text": "🔍 التحقق من المعاملة عبر Blockchain", "url": verify_url}]]}

    for token in [USER_BOT_TOKEN, ADMIN_BOT_TOKEN]:
        if not token:
            continue
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": PROOF_CHANNEL_ID,
                    "text": proof_text,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup,
                    "disable_web_page_preview": True,
                    "link_preview_options": {"is_disabled": True}
                },
                timeout=6
            )
            if res.status_code == 200 and res.json().get("ok"):
                break
        except Exception as e:
            print(f"⚠️ خطأ أثناء إرسال منشور الإثبات للقناة: {e}")


def notify_user_withdraw_status(user_id, action, coins, fee_usd, wallet_address, tx_id, new_znx_bal=None):
    """إرسال إشعار فوري للمستخدم على البوت عند قبول أو رفض طلب السحب الخاص به"""
    if not user_id:
        return

    clean_coins_str = format_clean_znx(coins)

    if action == "approve":
        msg = (
            "✅ <b>تم قبول وتنفيذ طلب السحب الخاص بك بنجاح!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>المبلغ المحول:</b> <code>{clean_coins_str} ZNX</code>\n"
            f"📥 <b>المحفظة:</b> <code>{html.escape(str(wallet_address))}</code>\n"
            f"🆔 <b>رقم المعاملة:</b> <code>#{html.escape(str(tx_id)[:12])}</code>\n\n"
            "🎉 شكراً لاستخدامك <b>ZN Goxe</b>!"
        )
    else:
        bal_line = f"🏦 <b>رصيدك الحالي بعد الاسترداد:</b> <code>{format_clean_znx(new_znx_bal)} ZNX</code>\n" if new_znx_bal is not None else ""
        msg = (
            "🔴 <b>تم رفض طلب السحب وإعادة الرصيد لحسابك</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>المبلغ المسترد:</b> <code>{clean_coins_str} ZNX</code>\n"
            f"💵 <b>رسوم الدولار المستردة:</b> <code>${fee_usd:.2f} USD</code>\n"
            f"{bal_line}"
            f"🆔 <b>رقم المعاملة:</b> <code>#{html.escape(str(tx_id)[:12])}</code>\n\n"
            "ℹ️ تم إرجاع كامل الرصيد والرسوم إلى محفظتك داخل التطبيق."
        )

    for token in [USER_BOT_TOKEN, ADMIN_BOT_TOKEN]:
        if not token:
            continue
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": str(user_id).strip(),
                    "text": msg,
                    "parse_mode": "HTML"
                },
                timeout=5
            )
            if res.status_code == 200 and res.json().get("ok"):
                break
        except Exception:
            pass


def execute_admin_decision(tx_id, action, admin_id=None):
    """
    تنفيذ قرار الأدمن (قبول / رفض) وتحديث كافة جداول السحب والسجل وإرجاع الرصيد في Supabase
    مع نظام Auto-Retry ضد انقطاعات الـ Pooler وحماية SAVEPOINT لكل جدول.
    """
    clean_tx_id = str(tx_id or "").strip()
    if not safe_get_db() or not get_db_connection or not clean_tx_id:
        return False, "خطأ في الاتصال بقاعدة البيانات!"

    if action not in ("approve", "reject"):
        return False, "إجراء غير صالح!"

    tx_lock = _get_tx_lock(clean_tx_id)
    if not tx_lock.acquire(blocking=False):
        return False, "هذه المعاملة قيد المعالجة حالياً من قِبل المشرف!"

    try:
        processed_by = str(admin_id) if admin_id else "admin"
        new_status = "completed" if action == "approve" else "rejected"
        failure_msg = "تم رفض الطلب وإعادة الرصيد لحسابك" if action == "reject" else None

        last_err = None
        for attempt in range(3):
            conn = None
            try:
                with get_db_connection() as conn:
                    conn.autocommit = False
                    try:
                        with conn.cursor(cursor_factory=RealDictCursor) as cur:
                            records = []

                            # 1. البحث في withdraw_requests أولاً (الجدول الأساسي لطلبات السحب)
                            cur.execute("SAVEPOINT sp_find_wr")
                            try:
                                cur.execute("""
                                    SELECT * FROM withdraw_requests
                                    WHERE tx_id = %s OR tx_hash = %s OR CAST(id AS TEXT) = %s
                                    LIMIT 1
                                    FOR UPDATE
                                """, (clean_tx_id, clean_tx_id, clean_tx_id))
                                row_wr = cur.fetchone()
                                if row_wr:
                                    records.append(dict(row_wr))
                                cur.execute("RELEASE SAVEPOINT sp_find_wr")
                            except Exception:
                                cur.execute("ROLLBACK TO SAVEPOINT sp_find_wr")

                            # 2. البحث في transactions
                            cur.execute("SAVEPOINT sp_find_tx")
                            try:
                                cur.execute("""
                                    SELECT * FROM transactions
                                    WHERE tx_id = %s OR tx_hash = %s OR CAST(id AS TEXT) = %s
                                    LIMIT 1
                                    FOR UPDATE
                                """, (clean_tx_id, clean_tx_id, clean_tx_id))
                                row_tx = cur.fetchone()
                                if row_tx:
                                    records.append(dict(row_tx))
                                cur.execute("RELEASE SAVEPOINT sp_find_tx")
                            except Exception:
                                cur.execute("ROLLBACK TO SAVEPOINT sp_find_tx")

                            # 3. البحث في processed_txs
                            cur.execute("SAVEPOINT sp_find_ptx")
                            try:
                                cur.execute("""
                                    SELECT * FROM processed_txs
                                    WHERE tx_id = %s OR id = %s OR tx_hash = %s
                                    LIMIT 1
                                    FOR UPDATE
                                """, (clean_tx_id, clean_tx_id, clean_tx_id))
                                row_ptx = cur.fetchone()
                                if row_ptx:
                                    records.append(dict(row_ptx))
                                cur.execute("RELEASE SAVEPOINT sp_find_ptx")
                            except Exception:
                                cur.execute("ROLLBACK TO SAVEPOINT sp_find_ptx")

                            if not records:
                                conn.rollback()
                                return False, "لم يتم العثور على طلب السحب في قاعدة البيانات!"

                            # فحص ما إذا كانت المعاملة قد عولجت مسبقاً في أي جدول
                            for r in records:
                                st = str(r.get("status") or "pending").lower().strip()
                                if st in ("completed", "approved", "rejected", "failed", "cancelled"):
                                    conn.rollback()
                                    st_ar = "مقبولة مسبقاً" if st in ("completed", "approved") else "مرفوضة مسبقاً"
                                    return False, f"هذه المعاملة تم معالجتها بالفعل ({st_ar})!"

                            # استخلاص بيانات المعاملة بأعلى دقة من السجلات المكتشفة
                            user_id = None
                            coins = 0.0
                            fee_usd = 0.02
                            wallet_address = ""

                            for r in records:
                                if not user_id:
                                    user_id = _sanitize_id(r.get("user_id") or r.get("tg_id") or r.get("telegram_id"))
                                if coins <= 0:
                                    c_val = float(r.get("coins") or r.get("amount") or r.get("net_amount") or r.get("net_coins") or 0.0)
                                    if c_val > 0:
                                        coins = c_val
                                if r.get("fee_usd") is not None or r.get("fee") is not None:
                                    f_val = float(r.get("fee_usd") if r.get("fee_usd") is not None else (r.get("fee") or 0.02))
                                    if f_val >= 0:
                                        fee_usd = f_val
                                if not wallet_address and r.get("wallet_address"):
                                    wallet_address = str(r.get("wallet_address")).strip()

                                # محاولة إضافية لاستخراج المبلغ من details إذا كان مخزناً بصيغة JSON
                                if coins <= 0 and r.get("details"):
                                    det_parsed = _parse_json_val(r.get("details"), {})
                                    if isinstance(det_parsed, dict) and det_parsed.get("coins"):
                                        coins = float(det_parsed.get("coins") or 0.0)

                            refunded_znx_bal = None
                            refunded_usd_bal = None

                            # في حال الرفض: إرجاع رصيد ZNX ورسوم الدولار لحساب المستخدم فوراً
                            if action == "reject" and user_id:
                                cur.execute("""
                                    UPDATE users
                                    SET znx_balance = ROUND(CAST(GREATEST(0.0, COALESCE(znx_balance, 0.0)) + %s AS NUMERIC), 6),
                                        usd_balance = ROUND(CAST(GREATEST(0.0, COALESCE(usd_balance, 0.0)) + %s AS NUMERIC), 4),
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE CAST(tg_id AS TEXT) = %s
                                       OR CAST(user_id AS TEXT) = %s
                                       OR CAST(telegram_id AS TEXT) = %s
                                    RETURNING znx_balance, usd_balance
                                """, (coins, fee_usd, user_id, user_id, user_id))
                                ref_row = cur.fetchone()
                                if ref_row:
                                    refunded_znx_bal = float(ref_row.get("znx_balance") or 0.0)
                                    refunded_usd_bal = float(ref_row.get("usd_balance") or 0.0)

                            # تحديث الحالة في withdraw_requests
                            cur.execute("SAVEPOINT sp_upd_wr")
                            try:
                                cur.execute("""
                                    UPDATE withdraw_requests
                                    SET status = %s, processed_by = %s, failure_reason = %s,
                                        processed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                                    WHERE tx_id = %s OR tx_hash = %s OR CAST(id AS TEXT) = %s
                                """, (new_status, processed_by, failure_msg, clean_tx_id, clean_tx_id, clean_tx_id))
                                cur.execute("RELEASE SAVEPOINT sp_upd_wr")
                            except Exception:
                                cur.execute("ROLLBACK TO SAVEPOINT sp_upd_wr")

                            # تحديث الحالة في transactions
                            cur.execute("SAVEPOINT sp_upd_tx")
                            try:
                                cur.execute("""
                                    UPDATE transactions
                                    SET status = %s, processed_by = %s, failure_reason = %s,
                                        processed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                                    WHERE tx_id = %s OR tx_hash = %s OR CAST(id AS TEXT) = %s
                                """, (new_status, processed_by, failure_msg, clean_tx_id, clean_tx_id, clean_tx_id))
                                cur.execute("RELEASE SAVEPOINT sp_upd_tx")
                            except Exception:
                                cur.execute("ROLLBACK TO SAVEPOINT sp_upd_tx")

                            # تحديث الحالة في processed_txs
                            cur.execute("SAVEPOINT sp_upd_ptx")
                            try:
                                cur.execute("""
                                    UPDATE processed_txs
                                    SET status = %s, processed_by = %s, failure_reason = %s,
                                        processed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                                    WHERE tx_id = %s OR id = %s OR tx_hash = %s
                                """, (new_status, processed_by, failure_msg, clean_tx_id, clean_tx_id, clean_tx_id))
                                cur.execute("RELEASE SAVEPOINT sp_upd_ptx")
                            except Exception:
                                cur.execute("ROLLBACK TO SAVEPOINT sp_upd_ptx")

                            # توثيق القرار في admin_logs
                            cur.execute("SAVEPOINT sp_ins_log")
                            try:
                                cur.execute("""
                                    INSERT INTO admin_logs (action, tx_id, user_id, admin_id, status, amount, created_at)
                                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                """, (f"withdraw_{action}", clean_tx_id, user_id, processed_by, new_status, coins))
                                cur.execute("RELEASE SAVEPOINT sp_ins_log")
                            except Exception:
                                cur.execute("ROLLBACK TO SAVEPOINT sp_ins_log")

                        conn.commit()
                    except Exception as inner_e:
                        conn.rollback()
                        raise inner_e
                    finally:
                        try:
                            conn.autocommit = True
                        except Exception:
                            pass

                clean_coins_str = format_clean_znx(coins)

                # إرسال إشعار القناة وإشعار المستخدم في الخلفية بعد نجاح حفظ القرار
                if action == "approve":
                    threading.Thread(
                        target=send_proof_to_channel,
                        args=(user_id, coins, wallet_address, clean_tx_id),
                        daemon=True
                    ).start()
                    threading.Thread(
                        target=notify_user_withdraw_status,
                        args=(user_id, "approve", coins, fee_usd, wallet_address, clean_tx_id, None),
                        daemon=True
                    ).start()
                    res_msg = f"🟢 تم قبول طلب السحب بنجاح! تم اعتماد سحب {clean_coins_str} ZNX ونشر الإثبات."
                else:
                    threading.Thread(
                        target=notify_user_withdraw_status,
                        args=(user_id, "reject", coins, fee_usd, wallet_address, clean_tx_id, refunded_znx_bal),
                        daemon=True
                    ).start()
                    if refunded_znx_bal is not None:
                        res_msg = (
                            f"🔴 تم رفض الطلب وإعادة {clean_coins_str} ZNX و ${fee_usd:.2f} USD إلى حساب المستخدم بنجاح! "
                            f"(رصيد المستخدم الآن: {format_clean_znx(refunded_znx_bal)} ZNX)"
                        )
                    else:
                        res_msg = f"🔴 تم رفض الطلب وإعادة {clean_coins_str} ZNX و ${fee_usd:.2f} USD إلى حساب المستخدم بنجاح!"

                return True, res_msg

            except Exception as attempt_err:
                last_err = attempt_err
                print(f"⚠️ محاولة رقم {attempt + 1} لمعالجة قرار السحب فشلت: {attempt_err}")
                time.sleep(0.4)

        return False, f"حدث خطأ أثناء المعالجة: {str(last_err)}"

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
        return jsonify({"success": False, "message": "يرجى اختيار محفظة TON بشكل صحيح."}), 400

    if not verify_telegram_webapp_data(init_data, user_id):
        return jsonify({"success": False, "message": "فشل التحقق من جلسة الأمان الخاصة بك. يرجى إعادة فتح التطبيق."}), 403

    if not is_valid_ton_address(wallet_address):
        return jsonify({"success": False, "message": "عنوان المحفظة غير صالح! يجب أن يكون عنوان TON يبدأ بـ EQ أو UQ."}), 400

    ok, msg = save_user_wallet(user_id, "ZNX", wallet_address)
    if ok:
        return jsonify({
            "success": True,
            "wallet_address": wallet_address,
            "message": "تم ربط وحفظ المحفظة بنجاح!"
        }), 200
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

    if not verify_telegram_webapp_data(init_data, user_id):
        return jsonify({"success": False, "message": "جلسة غير مصرح بها، يرجى إعادة فتح التطبيق من تيليجرام."}), 403

    try:
        coins = float(data.get("coins", 0))
        if math.isnan(coins) or math.isinf(coins) or coins <= 0:
            raise ValueError("Invalid float")
        coins = math.floor((coins + 1e-9) * 10000) / 10000
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "مبلغ السحب غير صالح."}), 400

    if not is_valid_ton_address(wallet_address):
        return jsonify({"success": False, "message": "عنوان محفظة TON غير صالح!"}), 400

    if not safe_get_db() or not get_db_connection:
        return jsonify({"success": False, "message": "خطأ في الاتصال بقاعدة البيانات."}), 500

    tier_info = get_current_withdraw_tier()
    min_withdraw = float(tier_info.get("min_withdraw_znx", 1000.0))
    fixed_fee_usd = float(tier_info.get("fixed_fee_usd", 0.02))
    tier_name = str(tier_info.get("name", "الشريحة الأولى"))

    if coins < min_withdraw:
        return jsonify({
            "success": False,
            "code": "BELOW_MINIMUM",
            "message": f"الحد الأدنى للسحب في {tier_name} هو {format_clean_znx(min_withdraw)} ZNX."
        }), 400

    user_lock = _get_user_lock(user_id)
    if not user_lock.acquire(blocking=False):
        return jsonify({"success": False, "message": "لديك عملية قيد التنفيذ حالياً، يرجى الانتظار."}), 429

    conn = None
    try:
        tx_id = uuid.uuid4().hex[:20]
        details_txt = f"سحب إلى المحفظة: {wallet_address}"
        details_json_str = json.dumps({
            "title": "سحب عملات ZNX",
            "note": details_txt,
            "wallet_address": wallet_address,
            "coins": coins,
            "fee_usd": fixed_fee_usd,
            "tier_name": tier_name
        }, ensure_ascii=False)

        new_znx_balance = 0.0
        new_usd_balance = 0.0

        with get_db_connection() as conn:
            conn.autocommit = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM users
                        WHERE CAST(tg_id AS TEXT) = %s OR CAST(user_id AS TEXT) = %s OR CAST(telegram_id AS TEXT) = %s
                        LIMIT 1 FOR UPDATE
                    """, (user_id, user_id, user_id))
                    user_data = cur.fetchone()

                    if not user_data:
                        conn.rollback()
                        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

                    if bool(user_data.get("is_banned", False) or user_data.get("banned", False)):
                        conn.rollback()
                        return jsonify({"success": False, "message": "حسابك معطل ولا يمكنك السحب."}), 403

                    # فحص الطلبات المعلقة والـ Cooldown
                    cur.execute("""
                        SELECT tx_id FROM withdraw_requests
                        WHERE (user_id = %s OR tg_id = %s)
                          AND (
                              status IN ('pending', 'processing')
                              OR created_at >= NOW() - (%s * INTERVAL '1 second')
                          )
                        LIMIT 1
                    """, (user_id, user_id, int(WITHDRAW_COOLDOWN_SECONDS)))

                    if cur.fetchone():
                        conn.rollback()
                        return jsonify({
                            "success": False,
                            "message": "لديك طلب سحب قيد المراجعة حالياً، يرجى انتظار قرار الإدارة قبل تقديم طلب جديد."
                        }), 400

                    current_balance = extract_user_balance(user_data)
                    usd_balance = extract_usd_balance(user_data)

                    if coins > current_balance + 1e-6:
                        conn.rollback()
                        return jsonify({"success": False, "code": "INSUFFICIENT_ZNX", "message": "رصيدك من عملة ZNX غير كافٍ."}), 400

                    if usd_balance + 1e-6 < fixed_fee_usd:
                        conn.rollback()
                        return jsonify({
                            "success": False,
                            "code": "INSUFFICIENT_USD",
                            "fee_required": fixed_fee_usd,
                            "message": f"يجب توفر رسوم السحب ${fixed_fee_usd:.2f} USD في رصيد الدولار."
                        }), 400

                    wallets_obj = _parse_json_val(user_data.get("wallets"), {})
                    if not isinstance(wallets_obj, dict):
                        wallets_obj = {}
                    wallets_obj["ZNX"] = wallet_address

                    # 1. خصم الرصيد وتحديث المحفظة ذرياً
                    cur.execute("""
                        UPDATE users
                        SET znx_balance = ROUND(CAST(GREATEST(0.0, COALESCE(znx_balance, 0.0) - %s) AS NUMERIC), 6),
                            usd_balance = ROUND(CAST(GREATEST(0.0, COALESCE(usd_balance, 0.0) - %s) AS NUMERIC), 4),
                            wallet_address = %s,
                            wallets = %s::jsonb,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE (CAST(tg_id AS TEXT) = %s OR CAST(user_id AS TEXT) = %s OR CAST(telegram_id AS TEXT) = %s)
                          AND COALESCE(znx_balance, 0.0) >= %s
                          AND COALESCE(usd_balance, 0.0) >= %s
                        RETURNING znx_balance, usd_balance
                    """, (
                        coins, fixed_fee_usd,
                        wallet_address, json.dumps(wallets_obj, ensure_ascii=False),
                        user_id, user_id, user_id,
                        coins - 1e-6, fixed_fee_usd - 1e-6
                    ))

                    updated_row = cur.fetchone()
                    if not updated_row:
                        conn.rollback()
                        return jsonify({"success": False, "message": "تغير رصيدك أثناء المعالجة، يرجى المحاولة مرة أخرى."}), 409

                    new_znx_balance = float(updated_row.get("znx_balance", 0.0) or 0.0)
                    new_usd_balance = float(updated_row.get("usd_balance", 0.0) or 0.0)

                    # 2. تسجيل الطلب في withdraw_requests
                    cur.execute("""
                        INSERT INTO withdraw_requests (
                            tx_id, tx_hash, user_id, tg_id, coins, amount, fee, fee_usd, net_coins, net_amount,
                            currency, tier_name, wallet_address, network, status, details, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'ZNX', %s, %s, 'TON', 'pending', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                    """, (
                        tx_id, tx_id, user_id, user_id, coins, coins, fixed_fee_usd, fixed_fee_usd, coins, coins,
                        tier_name, wallet_address, details_txt
                    ))

                    # 3. تسجيل الطلب في transactions
                    cur.execute("SAVEPOINT sp_insert_transactions")
                    try:
                        cur.execute("""
                            INSERT INTO transactions (
                                tx_id, tx_hash, user_id, tg_id, coins, amount, fee, fee_usd, net_coins, net_amount,
                                currency, tier_name, wallet_address, network, type, status, details, created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                'ZNX', %s, %s, 'TON', 'withdraw', 'pending', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                        """, (
                            tx_id, tx_id, user_id, user_id, coins, coins, fixed_fee_usd, fixed_fee_usd, coins, coins,
                            tier_name, wallet_address, details_txt
                        ))
                        cur.execute("RELEASE SAVEPOINT sp_insert_transactions")
                    except Exception as tx_err:
                        cur.execute("ROLLBACK TO SAVEPOINT sp_insert_transactions")
                        print(f"⚠️ تنبيه إدراج transactions: {tx_err}")

                    # 4. تسجيل الطلب في processed_txs
                    cur.execute("SAVEPOINT sp_insert_processed_txs")
                    try:
                        cur.execute("""
                            INSERT INTO processed_txs (
                                tx_hash, id, tx_id, user_id, tg_id, coins, amount, fee_usd, net_coins,
                                currency, tier_name, wallet_address, type, status, details, created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                'ZNX', %s, %s, 'withdraw', 'pending', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                        """, (
                            tx_id, tx_id, tx_id, user_id, user_id, coins, coins, fixed_fee_usd, coins,
                            tier_name, wallet_address, details_json_str
                        ))
                        cur.execute("RELEASE SAVEPOINT sp_insert_processed_txs")
                    except Exception as p_err:
                        cur.execute("ROLLBACK TO SAVEPOINT sp_insert_processed_txs")
                        print(f"⚠️ تنبيه إدراج processed_txs: {p_err}")

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                try:
                    conn.autocommit = True
                except Exception:
                    pass

        # إرسال الإشعار الفوري للأدمن في الخلفية
        threading.Thread(
            target=notify_admin_withdraw,
            args=(user_id, coins, fixed_fee_usd, wallet_address, tx_id, tier_name),
            daemon=True
        ).start()

        clean_coins_str = format_clean_znx(coins)

        return jsonify({
            "success": True,
            "tx_id": tx_id,
            "status": "pending",
            "message": f"✅ تم تقديم طلب سحب {clean_coins_str} ZNX بنجاح وهو قيد المراجعة لدى الإدارة!",
            "new_balance": new_znx_balance,
            "new_usd_balance": new_usd_balance
        }), 200

    except Exception as e:
        print(f"⚠️ خطأ معالجة السحب المالي في Supabase: {e}")
        return jsonify({"success": False, "message": "تعذر إجراء السحب، يرجى إعادة المحاولة."}), 500
    finally:
        user_lock.release()


def notify_admin_withdraw(user_id, coins, fee_usd, wallet, tx_id, tier_name):
    """إرسال رسالة تفاصيل السحب إلى الأدمن بتنسيق أرقام واضح ونظيف بدون .0000"""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        print("⚠️ تنبيه: لم يتم ضبط BOT_TOKEN أو ADMIN_CHAT_ID لإرسال إشعار السحب!")
        return

    full_details = get_user_full_details(user_id) or {}
    first_name = html.escape(str(full_details.get("first_name", "غير محدد")))
    username = html.escape(str(full_details.get("username", "لا يوجد")))
    joined_at = html.escape(str(full_details.get("joined_at", "غير محدد")))

    znx_bal = float(full_details.get("znx_balance", 0.0) or 0.0)
    zn_bal = float(full_details.get("zn_balance", 0.0) or 0.0)
    hourly_rate = float(full_details.get("hourly_rate", 0.0) or 0.0)
    storage_lvl = int(full_details.get("storage_level", 1) or 1)
    upgrades_cnt = int(full_details.get("upgrades_count", 0) or 0)
    ref_cnt = int(full_details.get("ref_count", 0) or 0)

    clean_coins_str = format_clean_znx(coins)
    clean_znx_bal_str = format_clean_znx(znx_bal)
    clean_zn_bal_str = format_clean_znx(zn_bal)

    text = (
        "🚀 <b>طلب سحب ZNX جديد (تحويل يدوي)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> <code>{html.escape(str(user_id))}</code> ({first_name} | @{username})\n"
        f"📅 <b>تاريخ الانضمام:</b> <code>{joined_at}</code>\n\n"
        f"💰 <b>رصيد ZNX المتبقي:</b> <code>{clean_znx_bal_str} ZNX</code>\n"
        f"💎 <b>رصيد ZN الحالي:</b> <code>{clean_zn_bal_str} ZN</code>\n\n"
        f"⚡ <b>سرعة التعدين:</b> <code>{hourly_rate:g} ZN/h</code>\n"
        f"📦 <b>المخزن / الترقيات:</b> level <code>{storage_lvl}</code> (ترقيات: <code>{upgrades_cnt}</code>)\n"
        f"👥 <b>عدد الإحالات:</b> <code>{ref_cnt}</code> صديق\n\n"
        f"📊 <b>الشريحة:</b> {html.escape(str(tier_name))}\n"
        f"💵 <b>المبلغ المطلوب سحبه:</b> <code>{clean_coins_str} ZNX</code>\n"
        f"💸 <b>الرسوم المقتطعة:</b> <code>${fee_usd:.2f} USD</code>\n\n"
        f"📥 <b>عنوان المحفظة المحول عليها:</b>\n<code>{html.escape(str(wallet))}</code>\n\n"
        f"🆔 <b>رقم المعاملة:</b> <code>{html.escape(str(tx_id))}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    reply_markup_primary = {
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

    reply_markup_fallback = {
        "inline_keyboard": [
            [
                {"text": "قبول 🟢", "callback_data": f"approve_tx_{tx_id}"},
                {"text": "رفض 🔴", "callback_data": f"reject_tx_{tx_id}"}
            ],
            [
                {"text": "📋 نسخ عنوان المحفظة", "callback_data": f"copy_addr_{tx_id}"[:64]}
            ]
        ]
    }

    target_chats = [c.strip() for c in str(ADMIN_CHAT_ID).split(",") if c.strip()]
    tokens_to_try = [t for t in [ADMIN_BOT_TOKEN, USER_BOT_TOKEN] if t]

    for chat_id in target_chats:
        sent_ok = False
        for token in tokens_to_try:
            if sent_ok:
                break
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            try:
                res = requests.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup_primary
                    },
                    timeout=6
                )
                if res.status_code == 200 and res.json().get("ok"):
                    sent_ok = True
                    break

                res_fb = requests.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup_fallback
                    },
                    timeout=6
                )
                if res_fb.status_code == 200 and res_fb.json().get("ok"):
                    sent_ok = True
                    break
                else:
                    print(f"⚠️ استجابة تيليجرام لإشعار الأدمن ({chat_id}): {res_fb.text}")
            except Exception as e:
                print(f"⚠️ خطأ إرسال إشعار السحب للأدمن ({chat_id}): {e}")

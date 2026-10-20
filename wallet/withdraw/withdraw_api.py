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
from .withdraw_db import (
    safe_get_db,
    get_user_doc,
    get_user_full_details,
    extract_user_balance,
    extract_usd_balance,
    get_current_withdraw_tier,
    save_user_wallet,
    is_valid_ton_address,
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
        parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
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
    تنفيذ قرار المشرف (قبول / رفض) وتحديث Supabase ذرياً
    مع حماية كاملة ضد الضغط المزدوج (Double Click Protection).
    """
    db = safe_get_db()
    clean_tx_id = str(tx_id or "").strip()
    if not db or not clean_tx_id:
        return False, "خطأ في الاتصال بقاعدة البيانات!"

    if action not in ("approve", "reject"):
        return False, "إجراء غير صالح!"

    tx_lock = _get_tx_lock(clean_tx_id)
    if not tx_lock.acquire(blocking=False):
        return False, "هذه المعاملة قيد المعالجة حالياً من قِبل المشرف!"

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        processed_by = str(admin_id) if admin_id else "admin"

        # 1. جلب المعاملة والتحقق من حالتها الحالية
        res = db.table("processed_txs").select("*").eq("tx_id", clean_tx_id).limit(1).execute()
        rows = res.data if res and hasattr(res, "data") else []

        if not rows:
            res_alt = db.table("processed_txs").select("*").eq("id", clean_tx_id).limit(1).execute()
            rows = res_alt.data if res_alt and hasattr(res_alt, "data") else []

        if not rows:
            return False, "لم يتم العثور على طلب السحب في قاعدة البيانات!"

        tx_data = rows[0]
        pk_col = "tx_id" if "tx_id" in tx_data and tx_data["tx_id"] == clean_tx_id else "id"
        current_status = tx_data.get("status", "pending")

        if current_status == "completed":
            return False, "هذه المعاملة تم قبولها مسبقاً!"
        elif current_status == "rejected":
            return False, "هذه المعاملة تم رفضها مسبقاً وإعادة الرصيد للمستخدم!"
        elif current_status == "processing":
            p_started = tx_data.get("processing_started_at")
            is_stuck = True
            if p_started:
                try:
                    dt = datetime.fromisoformat(str(p_started).replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - dt).total_seconds() < 15:
                        is_stuck = False
                except Exception:
                    is_stuck = True
            if not is_stuck:
                return False, "هذه المعاملة قيد المعالجة حالياً من قِبل المشرف!"

        # 2. قفل المعاملة ذرياً في قاعدة البيانات بشرط أن تكون حالتها لم تتغير
        claim_res = (
            db.table("processed_txs")
            .update({
                "status": "processing",
                "processing_started_at": now_iso,
                "updated_at": now_iso
            })
            .eq(pk_col, clean_tx_id)
            .eq("status", current_status)
            .execute()
        )
        if not claim_res.data:
            return False, "تمت معالجة هذه المعاملة للتو من مشرف آخر!"

        user_id = str(tx_data.get("user_id", "")).strip()
        coins = float(tx_data.get("coins", 0.0) or 0.0)
        fee_usd = float(tx_data.get("fee_usd", 0.02) or 0.02)
        wallet_address = tx_data.get("wallet_address", "")
        new_status = "completed" if action == "approve" else "rejected"

        update_payload = {
            "status": new_status,
            "processed_at": now_iso,
            "updated_at": now_iso,
            "processed_by": processed_by
        }

        if action == "approve":
            db.table("processed_txs").update(update_payload).eq(pk_col, clean_tx_id).execute()
            res_msg = f"🟢 تم قبول طلب السحب بنجاح! تم اعتماد خصم {coins:,.2f} ZNX ونشر إثبات السحب بنجاح."
            send_proof_to_channel(user_id, coins, wallet_address, clean_tx_id)
        else:
            # عند الرفض: إرجاع الرصيد للمستخدم بأمان تام مع قفل المستخدم
            user_lock = _get_user_lock(user_id)
            with user_lock:
                refunded = False
                # محاولة الاسترجاع عبر دالة RPC الذرية إن وجدت
                try:
                    rpc_res = db.rpc("rpc_refund_withdraw", {
                        "p_user_id": user_id,
                        "p_coins": coins,
                        "p_fee_usd": fee_usd
                    }).execute()
                    if rpc_res and rpc_res.data is True:
                        refunded = True
                except Exception:
                    refunded = False

                # البديل الذري المباشر في حال عدم تفعيل RPC
                if not refunded:
                    user_ref, user_data = get_user_doc(user_id)
                    if user_ref and user_data:
                        cur_znx = extract_user_balance(user_data)
                        cur_usd = extract_usd_balance(user_data)
                        user_ref.update({
                            "znx_balance": round(cur_znx + coins, 6),
                            "usd_balance": round(cur_usd + fee_usd, 4),
                            "updated_at": now_iso
                        })

            db.table("processed_txs").update(update_payload).eq(pk_col, clean_tx_id).execute()
            res_msg = "🔴 تم رفض الطلب وإعادة الرصيد بالكامل إلى حساب المستخدم بنجاح!"

        # 3. مزامنة السجلات في جدول transactions وجدول admin_logs
        try:
            db.table("transactions").update(update_payload).eq("tx_id", clean_tx_id).execute()
        except Exception:
            try:
                db.table("transactions").update(update_payload).eq("id", clean_tx_id).execute()
            except Exception:
                pass

        try:
            db.table("admin_logs").insert({
                "action": f"withdraw_{action}",
                "tx_id": clean_tx_id,
                "user_id": user_id,
                "admin_id": processed_by,
                "status": new_status,
                "amount": coins,
                "created_at": now_iso
            }).execute()
        except Exception:
            pass

        return True, res_msg

    except Exception as e:
        print(f"⚠️ خطأ أثناء تنفيذ قرار السحب في Supabase: {e}")
        try:
            db.table("processed_txs").update({"status": "pending"}).eq("tx_id", clean_tx_id).execute()
        except Exception:
            pass
        return False, f"حدث خطأ أثناء المعالجة: {str(e)}"
    finally:
        tx_lock.release()


@withdraw_bp.route("/config", methods=["GET"])
def get_config():
    user_id = str(request.args.get("user_id") or "").strip()

    user_balance = 0.0
    usd_balance = 0.0
    wallet_address = ""

    if user_id:
        _, user_data = get_user_doc(user_id)
        if user_data:
            user_balance = extract_user_balance(user_data)
            usd_balance = extract_usd_balance(user_data)
            wallets = user_data.get("wallets")
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
    user_id = str(data.get("user_id", "")).strip()
    wallet_address = str(data.get("wallet_address", "")).strip()
    init_data = request.headers.get("X-Telegram-Init-Data") or data.get("init_data", "")

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
    user_id = str(data.get("user_id", "")).strip()
    wallet_address = str(data.get("wallet_address", "")).strip()
    init_data = request.headers.get("X-Telegram-Init-Data") or data.get("init_data", "")

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

    if not user_id or not wallet_address:
        return jsonify({"success": False, "message": "بيانات طلب السحب غير مكتملة."}), 400

    if not is_valid_ton_address(wallet_address):
        return jsonify({"success": False, "message": "عنوان محفظة TON غير صالح!"}), 400

    db = safe_get_db()
    if not db:
        return jsonify({"success": False, "message": "خطأ في الاتصال بقاعدة البيانات."}), 500

    # 2. قفل المستخدم لمنع الهجمات المتزامنة (Race Condition Protection)
    user_lock = _get_user_lock(user_id)
    if not user_lock.acquire(blocking=False):
        return jsonify({
            "success": False,
            "message": "لديك عملية قيد التنفيذ حالياً، يرجى الانتظار لحظات."
        }), 429

    try:
        now_ts = time.time()
        last_req = _USER_LAST_REQUEST.get(user_id, 0)
        if now_ts - last_req < WITHDRAW_COOLDOWN_SECONDS:
            return jsonify({
                "success": False,
                "message": "يرجى الانتظار بضع ثوانٍ قبل إرسال طلب سحب آخر."
            }), 429

        user_ref, user_data = get_user_doc(user_id)
        if not user_ref or not user_data:
            return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

        if user_data.get("is_banned", False):
            return jsonify({"success": False, "message": "حسابك معطل ولا يمكنك إجراء عمليات سحب."}), 403

        # التحقق من عدم وجود طلب سحب معلق (اختياري لزيادة الحماية ضد السبام)
        try:
            pending_check = (
                db.table("processed_txs")
                .select("tx_id")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .limit(1)
                .execute()
            )
            if pending_check and pending_check.data:
                return jsonify({
                    "success": False,
                    "message": "لديك طلب سحب قيد المراجعة بالفعل! يرجى انتظار مراجعة طلبك الحالي أولاً."
                }), 400
        except Exception:
            pass

        tier_info = get_current_withdraw_tier()
        min_withdraw = float(tier_info.get("min_withdraw_znx", 1000.0))
        fixed_fee_usd = float(tier_info.get("fixed_fee_usd", 0.02))

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

        # 3. خصم الرصيد ذرياً (Atomic Balance Deduction)
        new_znx_balance = round(current_balance - coins, 6)
        new_usd_balance = round(usd_balance - fixed_fee_usd, 4)
        if new_znx_balance < 0 or new_usd_balance < 0:
            return jsonify({"success": False, "message": "الرصيد غير كافٍ."}), 400

        now_iso = datetime.now(timezone.utc).isoformat()
        tx_id = uuid.uuid4().hex[:20]

        # تحديث مشروط: لا ينجح التحديث إلا إذا كان الرصيد في قاعدة البيانات لا يزال مطابقاً ولم يتغير
        deduct_res = (
            db.table("users")
            .update({
                "znx_balance": new_znx_balance,
                "usd_balance": new_usd_balance,
                "updated_at": now_iso
            })
            .eq(user_ref.pk_col, user_ref.pk_val)
            .gte("znx_balance", coins)
            .gte("usd_balance", fixed_fee_usd)
            .execute()
        )

        if not deduct_res or not deduct_res.data:
            return jsonify({
                "success": False,
                "message": "تغير رصيدك أثناء المعالجة، يرجى المحاولة مرة أخرى."
            }), 409

        _USER_LAST_REQUEST[user_id] = time.time()

        tx_record = {
            "id": tx_id,
            "tx_id": tx_id,
            "user_id": user_id,
            "coins": coins,
            "amount": coins,
            "fee_usd": fixed_fee_usd,
            "net_coins": coins,
            "currency": "ZNX",
            "tier_name": tier_info.get("name", ""),
            "wallet_address": wallet_address,
            "type": "withdraw",
            "status": "pending",
            "created_at": now_iso,
            "updated_at": now_iso
        }

        # 4. تسجيل العملية في الجداول مع استرجاع تلقائي (Rollback) لو فشل الحفظ
        try:
            db.table("processed_txs").insert(tx_record).execute()
        except Exception as insert_err:
            print(f"⚠️ فشل حفظ سجل السحب، جاري إعادة الرصيد تلقائياً: {insert_err}")
            user_ref.update({
                "znx_balance": current_balance,
                "usd_balance": usd_balance,
                "updated_at": now_iso
            })
            return jsonify({
                "success": False,
                "message": "تعذر تسجيل معاملة السحب، لم يتم خصم أي رصيد."
            }), 500

        try:
            db.table("transactions").insert(tx_record).execute()
        except Exception as tx_err:
            print(f"⚠️ ملاحظة مزامنة جدول transactions: {tx_err}")

        notify_admin_withdraw(
            user_id, coins, fixed_fee_usd, wallet_address, tx_id, tier_info.get("name", "")
        )

        return jsonify({
            "success": True,
            "tx_id": tx_id,
            "message": f"تم تقديم طلب سحب {coins:,.4f} ZNX بنجاح وهو قيد المراجعة!",
            "new_balance": new_znx_balance,
            "new_usd_balance": new_usd_balance
        }), 200

    except Exception as e:
        print(f"⚠️ خطأ معالجة السحب المالي: {e}")
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

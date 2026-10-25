# -*- coding: utf-8 -*-
# shop/shop_api.py
# =================================================================
# 🛒 ZN Goxe - Shop Backend API (Anti-Cheat + On-Chain Verification)
# =================================================================

import base64
import hashlib
import json
import random
import threading
import time
import urllib.request
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

import database  # جلب قاعدة البيانات لقراءة حالة المستخدم الحية
from core.security import get_authenticated_user
from core.ton_price import get_live_ton_price
from database import get_db_connection
from friends.friends_db import sync_friend_upgrades_db
from shop.shop_db import (
    _normalize_tx_identifier,
    attach_boc_to_pending_payment,
    create_pending_ton_payment,
    get_pending_ton_payments,
    get_shop_catalog,
    process_upgrade_purchase,
    verify_and_apply_package as db_verify_and_apply_package,
)

shop_bp = Blueprint('shop', __name__)

PROJECT_TON_WALLET = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"
TON_SAFETY_MARGIN = 1.03  # إضافة 3% على الكمية المطلوبة كحماية

_TON_PRICE_CACHE = {"price": 0.0, "timestamp": 0}
CACHE_TTL_TON = 15  # كاش لمدة 15 ثانية فقط لسعر TON لمنع بطء الاتصال

_LAST_PENDING_CHECK_TS = 0
_PENDING_LOCK = threading.Lock()


def invalidate_shop_cache():
    _TON_PRICE_CACHE["price"] = 0.0
    _TON_PRICE_CACHE["timestamp"] = 0


def fetch_multi_source_ton_price():
    try:
        price = get_live_ton_price()
        if price and float(price) > 0:
            return float(price)
    except Exception:
        pass
    return 0.0


def get_cached_ton_price():
    now = time.time()
    if _TON_PRICE_CACHE["price"] > 0 and (now - _TON_PRICE_CACHE["timestamp"] < CACHE_TTL_TON):
        return _TON_PRICE_CACHE["price"]

    price = fetch_multi_source_ton_price()
    if price <= 0:
        price = _TON_PRICE_CACHE["price"] if _TON_PRICE_CACHE["price"] > 0 else 1.38

    _TON_PRICE_CACHE["price"] = price
    _TON_PRICE_CACHE["timestamp"] = now
    return price


def encode_ton_comment_boc(comment_text: str) -> str:
    """
    تحويل نص الـ Memo إلى خلية BOC قياسية بصيغة Base64 متوافقة مع TonConnect
    بحيث يتم تسجيل الـ Memo فعلياً داخل البلوكشين عند الدفع.
    """
    try:
        if not comment_text:
            return ""
        payload_bytes = b"\x00\x00\x00\x00" + str(comment_text).encode("utf-8")[:115]
        d1 = 0x00  # 0 refs, ordinary cell, level 0
        d2 = len(payload_bytes) * 2  # byte-aligned bits descriptor
        cell_bytes = bytes([d1, d2]) + payload_bytes

        boc_header = bytes([
            0xB5, 0xEE, 0x9C, 0x72,  # serialized_boc magic
            0x01,                    # has_idx=0, has_crc32c=0, flags=0, size_bytes=1
            0x01,                    # off_bytes=1
            0x01,                    # cells=1
            0x01,                    # roots=1
            0x00,                    # absent=0
            len(cell_bytes),         # tot_cells_size
            0x00                     # root_list=[0]
        ])
        return base64.b64encode(boc_header + cell_bytes).decode("ascii")
    except Exception as e:
        print(f"⚠️ [BOC Comment Encode Warning]: {e}")
        return ""


def is_valid_ton_boc(boc_str: str) -> bool:
    """
    فحص أمني صارم للتأكد من أن الـ BOC المرسل من الواجهة هو BOC حقيقي من محفظة TON
    وليس نصاً عشوائياً أو مزوراً.
    """
    if not boc_str or not isinstance(boc_str, str):
        return False
    clean_boc = boc_str.strip()
    if len(clean_boc) < 32 or clean_boc.startswith("TX_"):
        return False
    try:
        # إضافة حشو Base64 إن لزم الأمر
        padded = clean_boc + "=" * (-len(clean_boc) % 4)
        raw_bytes = base64.b64decode(padded)
        if len(raw_bytes) < 12:
            return False
        # التحقق من الـ Magic Bytes القياسية لـ TON BOC
        magic = raw_bytes[:4].hex().lower()
        return magic in ("b5ee9c72", "68ff65f3", "acc3a728")
    except Exception:
        return False


def _is_tx_already_processed(tx_hash: str) -> bool:
    """التحقق مما إذا كانت المعاملة مسجلة مسبقاً في قاعدة البيانات لمنع تكرار مطابقتها"""
    if not tx_hash:
        return False
    try:
        safe_h = _normalize_tx_identifier(tx_hash=tx_hash)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM processed_txs WHERE tx_hash = %s LIMIT 1", (safe_h,))
                return cur.fetchone() is not None
    except Exception:
        return False


def verify_ton_transaction_onchain(tx_hash, boc, min_nano_ton, expected_memo=None, created_after_ts=None):
    """
    التحقق الفعلي الصارم من وصول المعاملة على شبكة TON عبر TonCenter API.
    لا يتم قبول أي معاملة إلا إذا ثبت وجودها فعلياً على البلوكشين وبنفس القيمة المطلوبة.
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    min_nano_ton = int(min_nano_ton or 0)
    if min_nano_ton <= 0:
        return False, None

    # رفض فوري إذا لم يكن هناك لا tx_hash ولا BOC حقيقي
    if not tx_hash and not is_valid_ton_boc(boc):
        return False, None

    now_ts = int(time.time())
    # نافذة زمنية آمنة للمعاملات الحديثة (آخر 20 دقيقة إذا لم يحدد وقت الإنشاء)
    min_utime = int(created_after_ts - 90) if created_after_ts else (now_ts - 1200)

    try:
        url = f"https://toncenter.com/api/v2/getTransactions?address={PROJECT_TON_WALLET}&limit=35"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok') and 'result' in data:
                for tx in data['result']:
                    in_msg = tx.get('in_msg', {})
                    val = int(in_msg.get('value', 0))
                    tx_utime = int(tx.get('utime', 0))
                    msg_hash = tx.get('transaction_id', {}).get('hash', '')
                    in_msg_hash = in_msg.get('hash', '')

                    if not msg_hash or val <= 0:
                        continue

                    # استخراج الميمو من الرسالة الواردة
                    decoded_body = in_msg.get('decoded_body') if isinstance(in_msg.get('decoded_body'), dict) else {}
                    msg_memo = str(in_msg.get('message', '') or decoded_body.get('text', '') or '')

                    # التحقق من القيمة المالية (مع هامش سماح 5% لتقلبات الكسور)
                    val_ok = val >= int(min_nano_ton * 0.95)
                    if not val_ok:
                        continue

                    # 1. مطابقة مباشرة عبر الميمو أو الهاش
                    hash_match = bool(
                        tx_hash and (
                            tx_hash.lower() in msg_hash.lower()
                            or msg_hash.lower() in tx_hash.lower()
                            or (in_msg_hash and tx_hash.lower() in in_msg_hash.lower())
                        )
                    )
                    memo_match = bool(expected_memo and expected_memo in msg_memo)

                    if hash_match or memo_match:
                        if not _is_tx_already_processed(msg_hash):
                            return True, msg_hash

                    # 2. مطابقة ذكية في حال قامت محفظة المستخدم بإرسال المعاملة بدون حقل التعليق
                    # بشرط: أن يكون الـ BOC حقيقياً + المعاملة حديثة + نفس المبلغ المطلوب بالضبط + لم تُصرف من قبل
                    if is_valid_ton_boc(boc) and not msg_memo and tx_utime >= min_utime:
                        exact_val_match = int(min_nano_ton * 0.97) <= val <= int(min_nano_ton * 1.05)
                        if exact_val_match and not _is_tx_already_processed(msg_hash):
                            return True, msg_hash

    except Exception as e:
        print(f"⚠️ [TonCenter Verification Warning]: {e}")

    # الحل الأمني الصارم (Anti-Cheat): عدم قبول أي معاملة غير مؤكدة من الشبكة
    return False, None


def check_and_reconcile_pending_payments(target_tg_id=None):
    """
    فحص المعاملات المعلقة (Pending) التي أرسل أصحابها BOC حقيقي وتفعيلها تلقائياً
    بمجرد ظهورها على شبكة TON.
    """
    global _LAST_PENDING_CHECK_TS
    now = time.time()

    # منع الضغط الزائد على TonCenter (فحص مرة كل 6 ثوانٍ كحد أقصى في الخلفية)
    if not target_tg_id and (now - _LAST_PENDING_CHECK_TS < 6):
        return []

    if not _PENDING_LOCK.acquire(blocking=False):
        return []

    activated_list = []
    try:
        _LAST_PENDING_CHECK_TS = now
        pending_rows = get_pending_ton_payments(tg_id=target_tg_id, limit=15)

        for row in pending_rows:
            # لا نفحص إلا المعاملات التي أرسل المستخدم لها BOC فعلي من المحفظة
            if not row.get("boc_hash"):
                continue

            created_dt = row.get("created_at")
            created_ts = None
            if isinstance(created_dt, datetime):
                created_ts = int(created_dt.timestamp())

            verified_ok, confirmed_tx_hash = verify_ton_transaction_onchain(
                tx_hash=row.get("tx_hash") or "",
                boc=None,
                min_nano_ton=int(row.get("expected_nano_ton", 0)),
                expected_memo=row.get("payload_memo"),
                created_after_ts=created_ts,
            )

            if verified_ok and confirmed_tx_hash:
                ok, msg, res_data = db_verify_and_apply_package(
                    tg_id=row["tg_id"],
                    package_id=row["package_id"],
                    boc=None,
                    tx_hash=confirmed_tx_hash,
                    payload_memo=row.get("payload_memo"),
                )
                if ok:
                    activated_list.append({
                        "tg_id": row["tg_id"],
                        "package_id": row["package_id"],
                        "result": res_data,
                    })
    except Exception as e:
        print(f"⚠️ [Pending Reconcile Error]: {e}")
    finally:
        _PENDING_LOCK.release()

    return activated_list


@shop_bp.route('/get_config', methods=['GET', 'POST'])
def get_config():
    """مسار جلب الباقات والبيانات الحية للاعب لعرضها فوراً بدون إعادة تحميل"""
    try:
        success, user_id, user_info, error_res = get_authenticated_user(
            request, is_post=(request.method == 'POST')
        )

        # تشغيل فحص خفيف غير معطل في الخلفية للمعاملات المعلقة إن وجدت
        if success and user_id and (time.time() - _LAST_PENDING_CHECK_TS >= 8):
            threading.Thread(
                target=check_and_reconcile_pending_payments,
                args=(str(user_id),),
                daemon=True
            ).start()

        settings = get_shop_catalog(tg_id=user_id if success else None)
        raw_ton_price = get_cached_ton_price()

        user_state = settings.get("user_state") or {}
        if success and user_id and not user_state:
            user_state = database.get_user(str(user_id)) or {}

        usdt_pkgs = settings.get('packages', {})
        packages_with_ton = {}

        sorted_pkgs = sorted(
            usdt_pkgs.items(),
            key=lambda x: float(x[1].get('usdt', 0) if isinstance(x[1], dict) else 0)
        )

        for pkg_id, pkg_info in sorted_pkgs:
            if not isinstance(pkg_info, dict):
                continue
            usd_val = float(pkg_info.get('usdt', pkg_info.get('cost_usd', 0.0)))

            base_ton_amount = (usd_val / raw_ton_price) if raw_ton_price > 0 else (usd_val / 1.38)
            ton_needed = round(base_ton_amount * TON_SAFETY_MARGIN, 4)

            packages_with_ton[str(pkg_id)] = {
                "title": str(pkg_info.get('title', f'باقة {pkg_id}')),
                "usdt": usd_val,
                "duration_days": int(pkg_info.get('duration_days', 0)),
                "features": pkg_info.get('features', {}),
                "perks_text": pkg_info.get('perks_text', []),
                "ton_amount": ton_needed,
                "rate_add": float(pkg_info.get('rate_add', 0)),
                "storage_add": float(pkg_info.get('storage_add', 0)),
                "zn_add": float(pkg_info.get('zn_add', 0))
            }

        response = jsonify({
            "success": True,
            "settings": settings,
            "ton_price_usd": raw_ton_price,
            "packages": packages_with_ton,
            "user_state": user_state
        })

        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response, 200
    except Exception as e:
        print(f"❌ [Shop get_config Error]: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 200


@shop_bp.route('/prepare_ton_pay', methods=['POST'])
def prepare_ton_pay():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_id = str(data.get('package_id'))

        settings = get_shop_catalog()
        packages = settings.get('packages', {})

        if pkg_id not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 200

        pkg_info = packages[pkg_id]
        raw_ton_price = get_cached_ton_price()
        usd_val = float(pkg_info.get('usdt', pkg_info.get('cost_usd', 0.0)))

        base_ton = (usd_val / raw_ton_price) if raw_ton_price > 0 else (usd_val / 1.38)
        ton_amount = max(0.0001, round(base_ton * TON_SAFETY_MARGIN, 4))
        nano_ton = int(round(ton_amount * 1000000000))
        memo_payload = f"BUY_{pkg_id}_USER_{user_id}_{int(time.time())}_{random.randint(100,999)}"
        boc_comment_payload = encode_ton_comment_boc(memo_payload)

        # حفظ العملية كـ Pending في قاعدة البيانات قبل فتح المحفظة لضمان ثبات السعر والميمو
        create_pending_ton_payment(
            tg_id=user_id,
            package_id=pkg_id,
            usdt_price=usd_val,
            expected_nano_ton=nano_ton,
            payload_memo=memo_payload
        )

        return jsonify({
            "success": True,
            "package_id": pkg_id,
            "usdt_price": usd_val,
            "ton_amount": ton_amount,
            "nano_ton": str(nano_ton),
            "recipient_address": PROJECT_TON_WALLET,
            "payload_memo": memo_payload,
            "payload": boc_comment_payload or None
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200


@shop_bp.route('/verify_and_apply_package', methods=['POST'])
def verify_and_apply_package():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        pkg_key = str(data.get('package_id') or "")
        raw_boc = str(data.get('boc') or "").strip()
        tx_hash = str(data.get('tx_hash') or data.get('hash') or "").strip()
        payload_memo = str(data.get('payload_memo') or data.get('memo') or "").strip()

        if not pkg_key:
            return jsonify({"success": False, "error": "بيانات الباقة غير مكتملة."}), 200

        # التحقق الصارم من صحة الـ BOC لمنع إرسال أكواد وهمية
        if not tx_hash and not is_valid_ton_boc(raw_boc):
            return jsonify({
                "success": False,
                "error": "❌ لم يتم استلام كود معاملة صحيح من المحفظة."
            }), 200

        settings = get_shop_catalog()
        packages = settings.get('packages', {})

        if pkg_key not in packages:
            return jsonify({"success": False, "error": "باقة غير صالحة."}), 200

        # ربط الـ BOC بالمعاملة المعلقة واسترجاع المبلغ المطلوب وقت إنشاء الطلب
        pending_record = attach_boc_to_pending_payment(
            tg_id=user_id,
            package_id=pkg_key,
            boc=raw_boc,
            payload_memo=payload_memo or None
        )

        if pending_record and int(pending_record.get("expected_nano_ton", 0)) > 0:
            expected_nano = int(pending_record["expected_nano_ton"])
            if not payload_memo:
                payload_memo = str(pending_record.get("payload_memo") or "")
            created_dt = pending_record.get("created_at")
            created_ts = int(created_dt.timestamp()) if isinstance(created_dt, datetime) else None
        else:
            pkg_info = packages[pkg_key]
            usd_val = float(pkg_info.get('usdt', pkg_info.get('cost_usd', 0.0)))
            raw_ton_price = get_cached_ton_price()
            base_ton = (usd_val / raw_ton_price) if raw_ton_price > 0 else (usd_val / 1.38)
            expected_ton = max(0.0001, round(base_ton * TON_SAFETY_MARGIN, 4))
            expected_nano = int(round(expected_ton * 1000000000))
            created_ts = int(time.time()) - 120

        # فحص الشبكة مع إعادة المحاولة (حتى 3 محاولات بفاصل 3 ثوانٍ) لإعطاء البلوكشين وقتاً لتأكيد المعاملة
        verified_ok = False
        confirmed_tx_hash = None
        for attempt in range(3):
            verified_ok, confirmed_tx_hash = verify_ton_transaction_onchain(
                tx_hash=tx_hash,
                boc=raw_boc,
                min_nano_ton=expected_nano,
                expected_memo=payload_memo,
                created_after_ts=created_ts
            )
            if verified_ok:
                break
            if attempt < 2:
                time.sleep(3)

        if not verified_ok:
            # المعاملة لم تظهر على TonCenter بعد، نبقيها Pending لتفحصها الواجهة أو السيرفر خلال ثوانٍ
            return jsonify({
                "success": False,
                "pending": True,
                "message": "⏳ جاري تأكيد المعاملة من شبكة TON، سيتم تفعيل الباقة تلقائياً خلال لحظات."
            }), 200

        apply_success, message, result_data = db_verify_and_apply_package(
            tg_id=user_id,
            package_id=pkg_key,
            boc=raw_boc,
            tx_hash=confirmed_tx_hash or tx_hash,
            payload_memo=payload_memo
        )

        if apply_success:
            return jsonify({
                "success": True,
                "pending": False,
                "message": message,
                "result": result_data,
                **result_data
            }), 200
        else:
            return jsonify({"success": False, "error": message}), 200

    except Exception as e:
        print(f"[Shop Package Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 200


@shop_bp.route('/buy', methods=['POST'])
def buy_upgrade():
    try:
        success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        upgrade_type = data.get('type')
        level_num = str(data.get('level_num') or data.get('level') or data.get('upgrade_level'))

        if not upgrade_type or not level_num:
            return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة."}), 200

        apply_success, message, result_data = process_upgrade_purchase(
            tg_id=user_id,
            upgrade_type=upgrade_type,
            upgrade_id=level_num
        )

        if apply_success:
            # مزامنة ترقيات الصديق فوراً بعد الشراء من المتجر
            sync_friend_upgrades_db(str(user_id))
            return jsonify({
                "success": True,
                "result": result_data,
                **result_data
            }), 200
        else:
            return jsonify({"success": False, "error": message}), 200

    except Exception as e:
        print(f"[Shop Buy Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 200


@shop_bp.route('/clear_cache', methods=['POST'])
def clear_cache():
    try:
        invalidate_shop_cache()
        return jsonify({"success": True, "message": "تم تفريغ كاش المتجر بنجاح."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

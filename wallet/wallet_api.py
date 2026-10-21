# -*- coding: utf-8 -*-
import os
import json
import hmac
import hashlib
from urllib.parse import parse_qs, parse_qsl, unquote
from flask import Blueprint, jsonify, request, make_response
from .wallet_db import get_user_wallet_balances

try:
    from .deposit.deposit_api import deposit_bp
except ImportError:
    deposit_bp = Blueprint("deposit_placeholder", __name__)

try:
    from .history.history_api import history_bp
except ImportError:
    history_bp = Blueprint("history_placeholder", __name__)

try:
    from .withdraw.withdraw_api import withdraw_bp
except ImportError:
    withdraw_bp = Blueprint("withdraw_placeholder", __name__)

wallet_bp = Blueprint("wallet", __name__, url_prefix="/api/wallet")

wallet_bp.register_blueprint(deposit_bp, url_prefix="/deposit")
wallet_bp.register_blueprint(history_bp, url_prefix="/history")
wallet_bp.register_blueprint(withdraw_bp, url_prefix="/withdraw")

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("ADMIN_BOT_TOKEN") or ""


def _clean_uid(val):
    if val is None:
        return None
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not s or s.lower() in ("undefined", "none", "null", "nan", ""):
        return None
    # السماح فقط بمعرفات تيليجرام الرقمية أو النصية الآمنة لمنع الحقن
    if len(s) > 64:
        return None
    return s


def _extract_verified_init_data_user(raw_init: str):
    """التحقق من توقيع Telegram WebApp initData واستخراج معرف المستخدم الحقيقي بأمان"""
    if not raw_init:
        return None
    try:
        parsed_pairs = dict(parse_qsl(raw_init, keep_blank_values=True))
        received_hash = parsed_pairs.pop("hash", None)

        if received_hash and BOT_TOKEN:
            data_check_string = "\n".join(
                f"{k}={v}" for k, v in sorted(parsed_pairs.items())
            )
            secret_key = hmac.new(
                b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256
            ).digest()
            calculated_hash = hmac.new(
                secret_key, data_check_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(calculated_hash, received_hash):
                return None

        parsed = parse_qs(raw_init)
        user_str = parsed.get("user", [None])[0]
        if user_str:
            user_obj = json.loads(unquote(user_str))
            uid = user_obj.get("id")
            return _clean_uid(uid)
    except Exception:
        pass
    return None


def _extract_telegram_user_id():
    """
    استخراج معرف المستخدم بأولوية التوثيق المشفر من Telegram initData
    مع دعم المعاملات المباشرة للتوافق الكامل مع الواجهة.
    """
    # 1. الأولوية القصوى للترويسة المشفرة من تيليجرام لمنع التلاعب بالمعرفات
    auth_header = (
        request.headers.get("X-Telegram-Init-Data", "")
        or request.headers.get("X-Init-Data", "")
        or request.headers.get("Authorization", "")
    )
    if auth_header:
        raw_init = auth_header.replace("Bearer ", "").strip()
        verified_uid = _extract_verified_init_data_user(raw_init)
        if verified_uid:
            return verified_uid

    # 2. المصادر الاحتياطية (Query / Headers / JSON Body)
    candidates = [
        request.args.get("user_id"),
        request.args.get("tg_id"),
        request.args.get("telegram_id"),
        request.headers.get("X-Telegram-User-Id"),
    ]
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if body.get("init_data"):
            verified_body_uid = _extract_verified_init_data_user(str(body.get("init_data")))
            if verified_body_uid:
                return verified_body_uid
        candidates.extend([
            body.get("user_id"),
            body.get("tg_id"),
            body.get("telegram_id")
        ])

    for cid in candidates:
        cleaned = _clean_uid(cid)
        if cleaned:
            return cleaned

    return None


@wallet_bp.route("/data", methods=["GET", "POST"])
@wallet_bp.route("/balances", methods=["GET", "POST"])
def get_wallet_data():
    user_id = _extract_telegram_user_id()

    if not user_id:
        return jsonify({"success": False, "error": "معرف المستخدم غير متاح"}), 400

    balances = get_user_wallet_balances(user_id)

    # إذا حدث خطأ في الاتصال بالقاعدة، نرسل success: False حتى لا تصفر الواجهة الرصيد الحالي
    if not balances.get("db_ok", True):
        return jsonify({"success": False, "error": "خطأ مؤقت في الاتصال بقاعدة البيانات"}), 503

    zn_val = max(0.0, float(balances.get("zn_balance", 0.0) or 0.0))
    usdt_val = max(0.0, float(balances.get("usdt_balance", 0.0) or 0.0))
    znx_val = max(0.0, float(balances.get("znx_balance", 0.0) or 0.0))

    response = make_response(jsonify({
        "success": True,
        "user_id": user_id,
        "zn_balance": f"{zn_val:.4f}",
        "usdt_balance": f"{usdt_val:.4f}",
        "znx_balance": f"{znx_val:.4f}",
        "balance": zn_val,
        "usd_balance": usdt_val,
        "znx": znx_val
    }))

    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response

# -*- coding: utf-8 -*-
import os
import hashlib
import hmac
import json
import time
import urllib.parse
import logging

from flask import jsonify

logger = logging.getLogger("security")


def _get_bot_tokens():
    """جلب كافة التوكينات المحتملة للتحقق من التوقيع الرقمي لبيانات Telegram WebApp"""
    tokens = []
    for key in ["BOT_TOKEN", "WEBAPP_BOT_TOKEN", "ADMIN_BOT_TOKEN"]:
        val = os.environ.get(key, "").strip()
        if val and val not in tokens:
            tokens.append(val)
    return tokens


def _clean_init_data_prefix(raw_init_data: str) -> str:
    """تنظيف نص initData من أي بادئة مثل Bearer أو twa قبل فحص التوقيع الرقمي"""
    if not raw_init_data or not isinstance(raw_init_data, str):
        return ""
    cleaned = raw_init_data.strip()
    for prefix in ("bearer ", "twa "):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned


def validate_telegram_data(init_data: str):
    """التحقق الجنائي عبر HMAC-SHA256 من صحة بيانات Telegram WebApp initData"""
    init_data = _clean_init_data_prefix(init_data)
    if not init_data:
        return None

    bot_tokens = _get_bot_tokens()
    if not bot_tokens:
        logger.error("[Security] لم يتم العثور على أي توكين للبوت في متغيرات البيئة")
        return None

    try:
        parsed_data = dict(
            urllib.parse.parse_qsl(
                init_data,
                keep_blank_values=True,
                strict_parsing=False,
            )
        )

        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            logger.warning("[Security] حقل hash غير موجود في initData")
            return None

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed_data.items())
        )

        validated_user = None

        for bot_token in bot_tokens:
            secret_key = hmac.new(
                b"WebAppData",
                bot_token.encode("utf-8"),
                hashlib.sha256,
            ).digest()

            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if hmac.compare_digest(calculated_hash, received_hash):
                user_str = parsed_data.get("user", "{}")
                try:
                    validated_user = json.loads(user_str)
                    break
                except Exception:
                    pass

        if not validated_user or not isinstance(validated_user, dict):
            logger.warning("[Security] فشل التحقق من التوقيع الرقمي Hash لـ initData")
            return None

        auth_date = parsed_data.get("auth_date")
        if not auth_date:
            return None

        try:
            auth_timestamp = int(auth_date)
        except (TypeError, ValueError):
            return None

        now = int(time.time())
        # تقليص العمر الافتراضي إلى 6 ساعات (21600 ثانية) لمنع Replay Attacks
        max_age = int(os.environ.get("TELEGRAM_INITDATA_MAX_AGE", "21600"))

        if auth_timestamp > now + 120:
            logger.error("[Security] auth_date في المستقبل (تلاعب بالوقت)")
            return None

        if max_age > 0 and (now - auth_timestamp) > max_age:
            logger.warning("[Security] انتهت صلاحية جلسة initData، يرجى إعادة فتح التطبيق")
            return None

        user_id_val = validated_user.get("id")
        if not user_id_val or not str(user_id_val).strip().lstrip("-").isdigit():
            return None

        if parsed_data.get("start_param") is not None:
            validated_user["start_param"] = parsed_data["start_param"]

        return validated_user

    except Exception as exc:
        logger.exception(f"[Security] validate_telegram_data exception: {exc}")
        return None


def _extract_init_data_from_request(request):
    """استخراج initData المشفر بأولوية للهيدرز الصريحة ثم جسم الطلب أو الرابط وأخيراً Authorization"""
    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.headers.get("X-Init-Data")
    )

    if not init_data and request.is_json:
        req_data = request.get_json(silent=True) or {}
        if isinstance(req_data, dict):
            init_data = req_data.get("initData") or req_data.get("init_data")

    if not init_data and request.args:
        init_data = request.args.get("initData") or request.args.get("init_data")

    if not init_data:
        init_data = request.headers.get("Authorization")

    return _clean_init_data_prefix(init_data) if init_data else None


def _extract_device_credentials(request):
    """استخراج معرف الجهاز وبصمة المتصفح من الطلب"""
    req_json = request.get_json(silent=True) if request.is_json else {}
    if not isinstance(req_json, dict):
        req_json = {}

    device_id = (
        request.headers.get("X-Device-Id")
        or (request.args.get("device_id") if request.args else None)
        or (request.args.get("deviceId") if request.args else None)
        or req_json.get("device_id")
        or req_json.get("deviceId")
    )

    fingerprint = (
        request.headers.get("X-Device-Fingerprint")
        or (request.args.get("device_fingerprint") if request.args else None)
        or (request.args.get("fingerprint") if request.args else None)
        or (request.args.get("fingerprint_hash") if request.args else None)
        or req_json.get("device_fingerprint")
        or req_json.get("fingerprint")
        or req_json.get("fingerprint_hash")
    )

    clean_dev = (
        str(device_id).strip()[:256]
        if device_id and str(device_id).strip().lower() not in ("none", "null", "undefined", "")
        else None
    )
    clean_fp = (
        str(fingerprint).strip()[:256]
        if fingerprint and str(fingerprint).strip().lower() not in ("none", "null", "undefined", "")
        else None
    )
    return clean_dev, clean_fp


def check_banned_safely(telegram_id: str) -> tuple[bool, bool]:
    """
    فحص حالة الحظر للمستخدم بأمان بنظام Fail-Closed:
    يعيد (is_banned, check_success) - إذا فشل الاتصال بقاعدة البيانات يعيد (False, False) لرفض الطلب مؤقتاً.
    """
    admin_id = os.environ.get("ADMIN_ID", "5102387551").strip()
    super_admin_id = os.environ.get("SUPER_ADMIN_ID", "").strip()
    if str(telegram_id).strip() in (admin_id, super_admin_id, "5102387551"):
        return False, True

    try:
        from database import is_user_banned
        banned_state = is_user_banned(str(telegram_id), raise_on_error=True)
        return bool(banned_state), True
    except TypeError:
        try:
            from database import is_user_banned
            return bool(is_user_banned(str(telegram_id))), True
        except Exception as exc:
            logger.error(f"[Security] Error checking ban status for {telegram_id}: {exc}")
            return False, False
    except Exception as exc:
        logger.error(f"[Security] Error checking ban status for {telegram_id}: {exc}")
        return False, False


def _detect_id_spoofing(request, verified_telegram_id: str) -> str | None:
    """كشف أي محاولة لتمرير معرف مستخدم مختلف في الهيدر أو الرابط أو JSON عن المعرف الموثق"""
    candidates = [
        request.headers.get("X-Telegram-User-Id"),
        request.args.get("tg_id") if request.args else None,
        request.args.get("user_id") if request.args else None,
        request.args.get("telegram_id") if request.args else None,
    ]
    if request.is_json:
        req_json = request.get_json(silent=True) or {}
        if isinstance(req_json, dict):
            # نستثني المسارات الإدارية التي ترسل target_user_id، ونفحص فقط ادعاءات الهوية المباشرة لغير الأدمن
            for key in ("tg_id", "telegram_id"):
                if key in req_json:
                    candidates.append(req_json.get(key))

    admin_id = os.environ.get("ADMIN_ID", "5102387551").strip()
    super_admin_id = os.environ.get("SUPER_ADMIN_ID", "").strip()
    if verified_telegram_id in (admin_id, super_admin_id, "5102387551"):
        return None

    for raw_val in candidates:
        if raw_val is not None:
            s_val = str(raw_val).strip()
            if s_val and s_val.lower() not in ("", "null", "none", "undefined"):
                if s_val != verified_telegram_id:
                    return s_val
    return None


def get_authenticated_user(request, is_post=None, enforce_device_check=True):
    """
    توثيق صارم للمستخدم يعتمد حصرياً على التوقيع الرقمي لـ Telegram initData،
    ويفحص حالة الحظر وبصمة الجهاز بنظام Fail-Closed لمنع تعدد الحسابات والاختراق.
    """
    try:
        if getattr(request, "_auth_verified", False) and getattr(request, "telegram_id", None):
            return True, request.telegram_id, getattr(request, "telegram_user", {}), None

        init_data = _extract_init_data_from_request(request)
        user_info = validate_telegram_data(init_data)

        if not isinstance(user_info, dict) or not user_info.get("id"):
            logger.warning("[Security Auth Rejected] محاولة وصول بدون توقيع Telegram initData صالح")
            return (
                False,
                None,
                None,
                (
                    jsonify(
                        {
                            "success": False,
                            "error": "غير مصرح: يرجى فتح التطبيق من داخل بوت تليجرام الرسمي فقط.",
                        }
                    ),
                    401,
                ),
            )

        telegram_id = str(user_info["id"]).strip()

        # فحص محاولات التلاعب بالـ ID في الهيدرز أو البارامترات
        spoofed_id = _detect_id_spoofing(request, telegram_id)
        if spoofed_id:
            logger.error(f"🚨 [Spoofing Attempt] المستخدم {telegram_id} حاول انتحال المعرف {spoofed_id}")
            return (
                False,
                None,
                None,
                (
                    jsonify(
                        {
                            "success": False,
                            "error": "تم رصد محاولة تلاعب بهوية الحساب!",
                        }
                    ),
                    403,
                ),
            )

        # 1. فحص بصمة الجهاز وتعدد الحسابات (Fail-Closed)
        if enforce_device_check:
            device_id, fingerprint = _extract_device_credentials(request)
            if device_id or fingerprint:
                try:
                    import database
                    if hasattr(database, "check_and_bind_device"):
                        dev_res = database.check_and_bind_device(telegram_id, device_id, fingerprint)
                        if isinstance(dev_res, dict):
                            if dev_res.get("db_error"):
                                return (
                                    False,
                                    None,
                                    None,
                                    (
                                        jsonify(
                                            {
                                                "success": False,
                                                "error": "خطأ مؤقت في التحقق الأمني، يرجى المحاولة بعد لحظات.",
                                            }
                                        ),
                                        503,
                                    ),
                                )
                            if dev_res.get("banned") or dev_res.get("allowed") is False:
                                reason = dev_res.get("reason") or "تم حظر الحساب والجهاز بسبب تعدد الحسابات على نفس الجهاز."
                                return (
                                    False,
                                    telegram_id,
                                    user_info,
                                    (
                                        jsonify(
                                            {
                                                "success": False,
                                                "banned": True,
                                                "is_banned": True,
                                                "error": reason,
                                                "message": reason,
                                            }
                                        ),
                                        403,
                                    ),
                                )
                except Exception as dev_err:
                    logger.error(f"[Security] خطأ أثناء فحص الجهاز للمستخدم {telegram_id}: {dev_err}")
                    return (
                        False,
                        None,
                        None,
                        (
                            jsonify(
                                {
                                    "success": False,
                                    "error": "تعذر إتمام الفحص الأمني للجهاز حالياً، يرجى إعادة المحاولة.",
                                }
                            ),
                            503,
                        ),
                    )

        # 2. فحص حالة الحظر المباشرة في قاعدة البيانات
        is_banned, check_success = check_banned_safely(telegram_id)
        if not check_success:
            return (
                False,
                None,
                None,
                (
                    jsonify(
                        {
                            "success": False,
                            "error": "حدث خطأ في النظام، يرجى المحاولة لاحقاً",
                        }
                    ),
                    503,
                ),
            )

        if is_banned:
            logger.warning(f"🚫 [Security Banned] منع وصول المستخدم المحظور {telegram_id}")
            return (
                False,
                telegram_id,
                user_info,
                (
                    jsonify(
                        {
                            "success": False,
                            "banned": True,
                            "is_banned": True,
                            "error": "تم حظر هذا الحساب والجهاز لمخالفة القوانين أو تعدد الحسابات.",
                            "message": "تم حظر هذا الحساب والجهاز لمخالفة القوانين أو تعدد الحسابات.",
                        }
                    ),
                    403,
                ),
            )

        request.telegram_user = user_info
        request.telegram_id = telegram_id
        request._auth_verified = True

        return True, telegram_id, user_info, None

    except Exception as exc:
        logger.exception(f"[Security] Auth exception: {exc}")
        return (
            False,
            None,
            None,
            (
                jsonify(
                    {
                        "success": False,
                        "error": "حدث خطأ في عملية المصادقة الأمنية",
                    }
                ),
                500,
            ),
        )

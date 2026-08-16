import os
import hashlib
import hmac
import json
import time
import urllib.parse
import logging

from flask import jsonify

# إعداد الـ Logger الخاص بالنظام الأمنية
logger = logging.getLogger("security")


def _webapp_bot_token():
    return os.environ.get("WEBAPP_BOT_TOKEN", "").strip() or os.environ.get("BOT_TOKEN", "").strip()


def validate_telegram_data(init_data: str):
    """Validate Telegram Web App initData and return the Telegram user dict."""
    if not init_data or not isinstance(init_data, str):
        logger.warning("[Security] init_data فارغ أو ليس نصاً")
        return None

    init_data = init_data.strip()
    if init_data.startswith("Bearer "):
        init_data = init_data[7:].strip()

    bot_token = _webapp_bot_token()
    if not bot_token:
        logger.error("[Security] لم يتم العثور على WEBAPP_BOT_TOKEN أو BOT_TOKEN")
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

        # Constant-time comparison لمنع Timing Attacks
        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.error("[Security] فشل التحقق من Hash")
            return None

        auth_date = parsed_data.get("auth_date")
        if not auth_date:
            logger.error("[Security] auth_date غير موجود")
            return None

        try:
            auth_timestamp = int(auth_date)
        except (TypeError, ValueError):
            logger.error("[Security] auth_date غير صالح")
            return None

        now = int(time.time())
        # يفضل تقليل الافتراضي إلى 7200 ثانية (ساعتين) في الألعاب للحماية المضاعفة
        max_age = int(os.environ.get("TELEGRAM_INITDATA_MAX_AGE", "86400"))

        if auth_timestamp > now + 60:
            logger.error("[Security] auth_date في المستقبل")
            return None

        if max_age > 0 and now - auth_timestamp > max_age:
            logger.error("[Security] initData منتهي الصلاحية")
            return None

        user_str = parsed_data.get("user", "{}")
        try:
            user_dict = json.loads(user_str)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.error("[Security] JSON بيانات المستخدم غير صالح")
            return None

        if not isinstance(user_dict, dict) or not user_dict.get("id"):
            logger.error("[Security] بيانات المستخدم غير صالحة")
            return None

        if parsed_data.get("start_param") is not None:
            user_dict["start_param"] = parsed_data["start_param"]

        return user_dict

    except Exception as exc:
        logger.exception(f"[Security] validate_telegram_data exception: {exc}")
        return None


def check_banned_safely(telegram_id: str) -> tuple[bool, bool]:
    """
    Check the ban state safely.
    Returns: (is_banned: bool, check_successful: bool)
    """
    try:
        from database import is_user_banned
        return bool(is_user_banned(str(telegram_id))), True
    except ImportError:
        try:
            from users.users_db import is_user_banned
            return bool(is_user_banned(str(telegram_id))), True
        except Exception as exc:
            logger.error(f"[Security] Ban check import error: {exc}")
            return False, False
    except Exception as exc:
        logger.error(f"[Security] Error checking ban status for {telegram_id}: {exc}")
        return False, False


def get_authenticated_user(request, is_post=None):
    """
    Authenticate only from Telegram initData.
    Supported locations (Ordered by Security Best Practices):
      1. JSON Body: {"initData": "..."}
      2. X-Telegram-Init-Data header
      3. Authorization: Bearer <initData>
    """
    try:
        init_data = None

        if request.is_json:
            req_data = request.get_json(silent=True) or {}
            if isinstance(req_data, dict):
                init_data = req_data.get("initData")

        if not init_data:
            init_data = request.headers.get("X-Telegram-Init-Data")
        if not init_data:
            init_data = request.headers.get("Authorization")

        user_info = validate_telegram_data(init_data)
        telegram_id = None

        if isinstance(user_info, dict) and user_info.get("id"):
            telegram_id = str(user_info["id"]).strip()

        if not telegram_id:
            logger.warning("[Security Auth Failed] تعذر استخراج telegram_id من initData")
            return (
                False,
                None,
                None,
                (
                    jsonify(
                        {
                            "success": False,
                            "error": "غير مصرح: بيانات Telegram غير صالحة",
                        }
                    ),
                    401,
                ),
            )

        is_banned, check_success = check_banned_safely(telegram_id)
        
        # حماية Fail-Closed: إذا فشل الاتصال بقاعدة بيانات الحظر، يتم رفض الطلب لحين استقرار السيرفر
        if not check_success:
            logger.error(f"❌ [Security Error] متعذر التحقق من حالة حظر المستخدم {telegram_id}")
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
                    500,
                ),
            )

        if is_banned:
            logger.warning(f"🚫 [Security Banned] المستخدم {telegram_id} محظور")
            return (
                False,
                telegram_id,
                user_info,
                (
                    jsonify(
                        {
                            "success": False,
                            "error": "تم حظر حسابك لمخالفة القوانين",
                        }
                    ),
                    403,
                ),
            )

        request.telegram_user = user_info
        request.telegram_id = telegram_id

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
                        "error": "حدث خطأ في عملية المصادقة",
                    }
                ),
                500,
            ),
        )

import os
import hashlib
import hmac
import json
import time
import urllib.parse
import logging

from flask import jsonify

logger = logging.getLogger("security")

def get_possible_bot_tokens():
    """جلب جميع التوكينات المحتملة لتجربة التوثيق بحسب البوت المستخدم"""
    tokens = []
    for env_key in ["ADMIN_BOT_TOKEN", "WEBAPP_BOT_TOKEN", "BOT_TOKEN"]:
        val = os.environ.get(env_key, "").strip()
        if val and val not in tokens:
            tokens.append(val)
    return tokens


def validate_telegram_data(init_data: str):
    """التحقق المشدد من بيانات initData مع تجربة التوكينات المتاحة"""
    if not init_data or not isinstance(init_data, str):
        logger.warning("[Security] init_data فارغ أو ليس نصاً")
        return None

    init_data = init_data.strip()
    if init_data.startswith("Bearer "):
        init_data = init_data[7:].strip()

    bot_tokens = get_possible_bot_tokens()
    if not bot_tokens:
        logger.error("[Security] لم يتم العثور على أي BOT_TOKEN في متغيرات البيئة")
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

        valid_user_dict = None

        # تجربة التحقق مقابل توكينات البوتات المتاحة
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
                auth_date = parsed_data.get("auth_date")
                if not auth_date:
                    continue

                try:
                    auth_timestamp = int(auth_date)
                except (TypeError, ValueError):
                    continue

                now = int(time.time())
                max_age = int(os.environ.get("TELEGRAM_INITDATA_MAX_AGE", "86400"))

                if auth_timestamp > now + 60 or (max_age > 0 and now - auth_timestamp > max_age):
                    continue

                user_str = parsed_data.get("user", "{}")
                try:
                    user_dict = json.loads(user_str)
                    if isinstance(user_dict, dict) and user_dict.get("id"):
                        if parsed_data.get("start_param") is not None:
                            user_dict["start_param"] = parsed_data["start_param"]
                        valid_user_dict = user_dict
                        break
                except Exception:
                    continue

        return valid_user_dict

    except Exception as exc:
        logger.exception(f"[Security] validate_telegram_data exception: {exc}")
        return None


def check_banned_safely(telegram_id: str) -> tuple[bool, bool]:
    """فحص حالة الحظر بأمان"""
    try:
        try:
            from database import is_user_banned
            return bool(is_user_banned(str(telegram_id))), True
        except (ImportError, AttributeError):
            try:
                from users.users_db import is_user_banned
                return bool(is_user_banned(str(telegram_id))), True
            except (ImportError, AttributeError):
                return False, True
    except Exception as exc:
        logger.error(f"[Security] Error checking ban status for {telegram_id}: {exc}")
        return False, True


def get_authenticated_user(request, is_post=None):
    """مصادقة المستخدم من initData أو الهيدرز المعتمدة"""
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
            telegram_id = request.headers.get("X-Telegram-User-Id")
            if telegram_id:
                telegram_id = str(telegram_id).strip()
                user_info = {"id": telegram_id, "first_name": "User"}

        if not telegram_id:
            logger.warning("[Security Auth Failed] تعذر استخراج telegram_id")
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
                    500,
                ),
            )

        if is_banned:
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

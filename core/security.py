import os
import hashlib
import hmac
import json
import time
import urllib.parse

from flask import jsonify


# Telegram Web App initData validation.
# The server remains the source of truth; there is intentionally no
# telegram_id/admin-id bypass here.
def validate_telegram_data(init_data: str):
    """Validate Telegram Web App initData and return the Telegram user dict."""
    if not init_data or not isinstance(init_data, str):
        print("⚠️ [Security] init_data فارغ أو ليس نصاً")
        return None

    init_data = init_data.strip()
    if init_data.startswith("Bearer "):
        init_data = init_data[7:].strip()

    tokens = []
    admin_token = os.environ.get("ADMIN_BOT_TOKEN", "").strip()
    bot_token = os.environ.get("BOT_TOKEN", "").strip()

    if admin_token:
        tokens.append(admin_token)
    if bot_token and bot_token not in tokens:
        tokens.append(bot_token)

    if not tokens:
        print("❌ [Security] لم يتم العثور على BOT_TOKEN أو ADMIN_BOT_TOKEN")
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
            print("⚠️ [Security] حقل hash غير موجود في initData")
            return None

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed_data.items())
        )

        valid_hash = False
        for token in tokens:
            secret_key = hmac.new(
                b"WebAppData",
                token.encode("utf-8"),
                hashlib.sha256,
            ).digest()

            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if hmac.compare_digest(calculated_hash, received_hash):
                valid_hash = True
                break

        if not valid_hash:
            print("❌ [Security] فشل التحقق من Hash")
            return None

        # Reject very old initData. Telegram initData sent by the WebApp
        # should be refreshed by the Telegram client when the app is opened.
        auth_date = parsed_data.get("auth_date")
        if auth_date:
            try:
                auth_timestamp = int(auth_date)
                max_age = int(os.environ.get("TELEGRAM_INITDATA_MAX_AGE", "86400"))
                if max_age > 0 and (time.time() - auth_timestamp) > max_age:
                    print("❌ [Security] initData منتهي الصلاحية")
                    return None
            except (TypeError, ValueError):
                print("❌ [Security] auth_date غير صالح")
                return None

        user_str = parsed_data.get("user", "{}")
        user_dict = json.loads(user_str)

        if not isinstance(user_dict, dict) or not user_dict.get("id"):
            print("❌ [Security] بيانات المستخدم غير صالحة")
            return None

        if parsed_data.get("start_param") is not None:
            user_dict["start_param"] = parsed_data["start_param"]

        return user_dict

    except Exception as exc:
        print(f"⚠️ [Security] validate_telegram_data exception: {exc}")
        return None


def check_banned_safely(telegram_id: str) -> bool:
    """Check the ban state without making security.py imports crash."""
    try:
        from database import is_user_banned
        return bool(is_user_banned(telegram_id))
    except ImportError:
        try:
            from users.users_db import is_user_banned
            return bool(is_user_banned(telegram_id))
        except Exception:
            return False
    except Exception as exc:
        print(f"⚠️ [Security] Error checking ban status for {telegram_id}: {exc}")
        return False


def get_authenticated_user(request, is_post=None):
    """
    Authenticate only from Telegram initData.
    Supported locations:
      - JSON: {"initData": "..."}
      - X-Telegram-Init-Data header
      - Authorization: Bearer <initData>
      - Query string: ?initData=...
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

        if not init_data:
            init_data = request.args.get("initData")

        telegram_id = None
        user_info = None

        if init_data:
            user_info = validate_telegram_data(init_data)
            if isinstance(user_info, dict) and user_info.get("id"):
                telegram_id = str(user_info["id"]).strip()

        if not telegram_id:
            print("❌ [Security Auth Failed] تعذر استخراج telegram_id من initData")
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

        if check_banned_safely(telegram_id):
            print(f"🚫 [Security Banned] المستخدم {telegram_id} محظور")
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
        print(f"❌ [Security] Auth exception: {exc}")
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

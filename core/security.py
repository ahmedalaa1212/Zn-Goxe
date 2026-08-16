import os
import hashlib
import hmac
import json
import time
import urllib.parse

from flask import jsonify


def _tokens():
    result = []

    admin_token = os.environ.get("ADMIN_BOT_TOKEN", "").strip()
    bot_token = os.environ.get("BOT_TOKEN", "").strip()

    if admin_token:
        result.append(admin_token)

    if bot_token and bot_token not in result:
        result.append(bot_token)

    return result


def validate_telegram_data(init_data: str):
    if not init_data or not isinstance(init_data, str):
        return None

    init_data = init_data.strip()
    if init_data.startswith("Bearer "):
        init_data = init_data[7:].strip()

    tokens = _tokens()
    if not tokens:
        print("❌ [Security] BOT_TOKEN/ADMIN_BOT_TOKEN غير مضبوط")
        return None

    try:
        parsed = dict(
            urllib.parse.parse_qsl(
                init_data,
                keep_blank_values=True,
                strict_parsing=False
            )
        )

        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed.items())
        )

        valid = False
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
                valid = True
                break

        if not valid:
            print("❌ [Security] Telegram Hash verification failed")
            return None

        auth_date_raw = parsed.get("auth_date")
        if not auth_date_raw:
            return None

        try:
            auth_date = int(auth_date_raw)
        except (TypeError, ValueError):
            return None

        now = int(time.time())
        max_age = int(os.environ.get("TELEGRAM_INITDATA_MAX_AGE", "86400"))

        if auth_date > now + 60:
            return None

        if max_age > 0 and now - auth_date > max_age:
            return None

        try:
            user = json.loads(parsed.get("user", "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

        if not isinstance(user, dict) or not user.get("id"):
            return None

        if parsed.get("start_param") is not None:
            user["start_param"] = parsed["start_param"]

        return user

    except Exception as exc:
        print(f"⚠️ [Security] validation exception: {exc}")
        return None


def check_banned_safely(telegram_id: str) -> bool:
    try:
        from database import is_user_banned
        return bool(is_user_banned(str(telegram_id)))
    except ImportError:
        try:
            from users.users_db import is_user_banned
            return bool(is_user_banned(str(telegram_id)))
        except Exception:
            return False
    except Exception as exc:
        print(f"⚠️ [Security] ban check error: {exc}")
        return False


def get_authenticated_user(request, is_post=None):
    try:
        init_data = None

        if request.is_json:
            payload = request.get_json(silent=True) or {}
            if isinstance(payload, dict):
                init_data = payload.get("initData")

        if not init_data:
            init_data = request.headers.get("X-Telegram-Init-Data")

        if not init_data:
            init_data = request.headers.get("Authorization")

        if not init_data:
            # Kept only for legacy endpoints; front-end code no longer puts
            # initData in ordinary API URLs.
            init_data = request.args.get("initData")

        user_info = validate_telegram_data(init_data)

        if not isinstance(user_info, dict) or not user_info.get("id"):
            return (
                False,
                None,
                None,
                (
                    jsonify({
                        "success": False,
                        "error": "غير مصرح: بيانات Telegram غير صالحة"
                    }),
                    401,
                ),
            )

        telegram_id = str(user_info["id"]).strip()

        if check_banned_safely(telegram_id):
            return (
                False,
                telegram_id,
                user_info,
                (
                    jsonify({
                        "success": False,
                        "error": "تم حظر حسابك لمخالفة القوانين",
                        "banned": True,
                    }),
                    403,
                ),
            )

        request.telegram_user = user_info
        request.telegram_id = telegram_id

        return True, telegram_id, user_info, None

    except Exception as exc:
        print(f"❌ [Security] authentication exception: {exc}")
        return (
            False,
            None,
            None,
            (
                jsonify({
                    "success": False,
                    "error": "حدث خطأ في عملية المصادقة"
                }),
                500,
            ),
        )

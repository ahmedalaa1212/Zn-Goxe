import os
import sys

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database
from core.security import get_authenticated_user

app = Flask(__name__, static_folder=None)

WEB_URL = (
    os.environ.get(
        "WEB_URL",
        "https://zn-goxe-production.up.railway.app",
    )
    .strip()
    .rstrip("/")
)

# Same-origin Telegram WebApp normally does not need permissive CORS.
# WEB_URL is kept as the trusted external origin for API calls if needed.
CORS(
    app,
    resources={r"/api/.*": {"origins": [WEB_URL]}},
    supports_credentials=False,
)


# ==========================================
# تسجيل موديولات المسارات (Blueprints)
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from support.support_api import support_bp
from admin_chat.admin_chat_api import admin_chat_bp

app.register_blueprint(farm_bp, url_prefix="/api/farm")
app.register_blueprint(settings_bp, url_prefix="/api/settings")
app.register_blueprint(friends_bp, url_prefix="/api/friends")
app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
app.register_blueprint(shop_bp, url_prefix="/api/shop")
app.register_blueprint(support_bp, url_prefix="/api/support")
app.register_blueprint(admin_chat_bp, url_prefix="/api/admin-chat")


# Wallet module.
try:
    from wallet.wallet_api import wallet_bp

    app.register_blueprint(wallet_bp, url_prefix="/api/wallet")
    print("✅ تم تسجيل موديول المحفظة (wallet_bp) بنجاح!")
except Exception as exc:
    print(f"⚠️ تعذر تحميل موديول المحفظة الرئيسي: {exc}")


# Games module.
try:
    from games.games_api import games_bp

    app.register_blueprint(games_bp)
    print("✅ تم تسجيل موديول الألعاب الرئيسي (games_bp) بنجاح!")
except Exception as exc:
    print(f"⚠️ مجلد الألعاب غير موجود أو به خطأ، تم تخطيه: {exc}")


# ==========================================
# Wallet frontend static files
# ==========================================
@app.route("/wallet/<path:filename>", methods=["GET"])
def serve_wallet_frontend(filename):
    """
    Serve wallet frontend files from the real wallet/ directory.
    The API remains under /api/wallet/* and is handled by wallet_bp.
    """
    safe_name = filename.replace("\\", "/").lstrip("/")

    forbidden_extensions = (
        ".py", ".env", ".sh", ".git", ".pem", ".key",
        ".db", ".sqlite", ".json"
    )
    if safe_name.lower().endswith(forbidden_extensions):
        return jsonify({"success": False, "error": "Access Denied"}), 403

    allowed_extensions = (
        ".html", ".js", ".css", ".png", ".jpg", ".jpeg",
        ".webp", ".svg", ".ico", ".gif", ".woff", ".woff2", ".ttf"
    )
    if not safe_name.lower().endswith(allowed_extensions):
        return jsonify({"success": False, "error": "Unsupported file"}), 403

    wallet_root = os.path.join(BASE_DIR, "wallet")
    return send_from_directory(wallet_root, safe_name)


# ==========================================
# TON Connect manifest
# ==========================================
@app.route("/tonconnect-manifest.json", methods=["GET"])
def serve_tonconnect_manifest():
    try:
        response = send_from_directory(
            BASE_DIR,
            "tonconnect-manifest.json",
            mimetype="application/json",
        )
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate, max-age=0"
        )
        return response
    except Exception as exc:
        print(f"❌ Manifest Error: {exc}")
        return jsonify(
            {"success": False, "error": "Manifest file not found"}
        ), 404


# ==========================================
# User info
# ==========================================
@app.route("/api/user/info", methods=["GET", "POST"])
def get_user_info_main():
    success, telegram_id, user_info, error_response = get_authenticated_user(
        request
    )

    if not success:
        return error_response

    try:
        if hasattr(database, "is_user_banned") and database.is_user_banned(
            telegram_id
        ):
            return jsonify(
                {
                    "success": False,
                    "error": "حسابك معطل حالياً بسبب مخالفة الشروط",
                    "banned": True,
                }
            ), 403

        user_data = database.get_user(telegram_id)

        if not user_data:
            first_name = (
                user_info.get("first_name", "لاعب")
                if isinstance(user_info, dict)
                else "لاعب"
            )
            ref_id = (
                user_info.get("start_param")
                if isinstance(user_info, dict)
                else None
            )

            if hasattr(database, "init_user"):
                database.init_user(
                    telegram_id,
                    ref_id=ref_id,
                    first_name=first_name,
                )

            user_data = database.get_user(telegram_id) or {}

        balance = float(user_data.get("balance", 0.0))
        usd_balance = float(user_data.get("usd_balance", 0.0))

        return jsonify(
            {
                "success": True,
                "user": user_data,
                "player": user_data,
                "balance": balance,
                "usd_balance": usd_balance,
                "uid": telegram_id,
            }
        ), 200

    except Exception as exc:
        print(
            f"❌ Error fetching user info for {telegram_id}: {exc}"
        )
        return jsonify(
            {
                "success": False,
                "error": "حدث خطأ أثناء جلب بيانات الحساب",
            }
        ), 500


# ==========================================
# Security / no-cache for API
# ==========================================
@app.after_request
def add_security_headers(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()"
    )

    if request.path.lower().endswith((".html", ".js", ".css")):
        response.headers.setdefault(
            "Cache-Control",
            "no-cache, no-store, must-revalidate, max-age=0"
        )
        response.headers.setdefault("Pragma", "no-cache")
        response.headers.setdefault("Expires", "0")

    return response


# ==========================================
# Error handlers
# ==========================================
@app.errorhandler(500)
def handle_500_error(error):
    if request.path.startswith("/api/"):
        return jsonify(
            {
                "status": "error",
                "success": False,
                "error": "حدث خطأ داخلي في السيرفر",
                "message": "خطأ في الاتصال بالخادم.",
            }
        ), 500

    if request.path.lower().endswith((
        ".html", ".js", ".css", ".json", ".png", ".jpg", ".jpeg",
        ".webp", ".svg", ".ico", ".gif", ".woff", ".woff2", ".ttf"
    )):
        return jsonify({
            "success": False,
            "error": "Static file server error",
            "path": request.path
        }), 500

    return send_from_directory(BASE_DIR, "index.html"), 500


@app.errorhandler(404)
def handle_404_error(error):
    if request.path.startswith("/api/"):
        return jsonify(
            {
                "status": "error",
                "success": False,
                "error": "المسار غير موجود",
                "message": "خطأ في الاتصال بالخادم.",
            }
        ), 404

    # A missing static asset must stay a real 404. Returning index.html here
    # was one of the reasons module loaders could mistakenly render "Coming Soon".
    asset_extensions = (
        ".html",
        ".js",
        ".css",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".svg",
        ".ico",
        ".gif",
        ".woff",
        ".woff2",
        ".ttf",
    )

    if request.path.lower().endswith(asset_extensions):
        return jsonify(
            {
                "success": False,
                "error": "الملف المطلوب غير موجود",
                "path": request.path,
            }
        ), 404

    return send_from_directory(BASE_DIR, "index.html")


# ==========================================
# Static files
# ==========================================
@app.route("/")
def serve_index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    path_lower = path.lower()

    if path_lower == "tonconnect-manifest.json":
        return serve_tonconnect_manifest()

    forbidden_extensions = (
        ".py",
        ".env",
        ".sh",
        ".git",
        ".pem",
        ".key",
        ".db",
        ".sqlite",
    )

    forbidden_files = (
        "firebase-adminsdk.json",
        "config.json",
        "requirements.txt",
        "dockerfile",
    )

    if (
        any(path_lower.endswith(ext) for ext in forbidden_extensions)
        or any(name in path_lower for name in forbidden_files)
    ):
        return jsonify(
            {"success": False, "error": "Access Denied"}
        ), 403

    try:
        return send_from_directory(BASE_DIR, path)
    except Exception:
        # Do not silently turn missing .html/.js module files into index.html.
        static_extensions = (
            ".html",
            ".js",
            ".css",
            ".json",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".svg",
            ".ico",
            ".gif",
            ".woff",
            ".woff2",
            ".ttf",
        )

        if path_lower.endswith(static_extensions):
            return jsonify(
                {
                    "success": False,
                    "error": "Static file not found",
                    "path": path,
                }
            ), 404

        return send_from_directory(BASE_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )

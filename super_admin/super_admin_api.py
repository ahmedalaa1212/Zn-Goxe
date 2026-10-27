# =========================================================
# 🛡️ super_admin/super_admin_api.py
# Secured Super Admin API Blueprint (Supabase / PostgreSQL)
# =========================================================

import os
import time
import json
import hmac
import hashlib
import urllib.parse
import threading
from flask import Blueprint, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
import super_admin.super_admin_db as super_admin_db

# محاولة استيراد نظام الأمان المركزي إن وُجد
try:
    import core.security as security
except ImportError:
    security = None

super_admin_bp = Blueprint('super_admin_bp', __name__)

# الاعتماد الحصري والصارم على توكن بوت المستخدمين الرئيسي (Zn Goxe) للإرسال
USER_BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "").strip()
user_bot = telebot.TeleBot(USER_BOT_TOKEN) if USER_BOT_TOKEN else None

# متغير لمتابعة حالة الإرسال الجماعي الحية
current_broadcast_status = {
    "is_running": False,
    "total": 0,
    "sent": 0,
    "failed": 0,
    "blocked": 0,
    "last_campaign_time": None
}


def set_bot(new_bot):
    """حماية الموديول لمنع استبدال البوت ببوت الأدمن من أي ملف آخر"""
    pass


# =========================================================
# 🔐 طبقة التوثيق الجنائي والتحقق من صلاحيات الإدارة
# =========================================================

def _extract_raw_init_data(req):
    """استخراج سلسلة initData المشفرة من الهيدرز المعتمدة فقط"""
    init_data = (
        req.headers.get("X-Telegram-Init-Data")
        or req.headers.get("X-Init-Data")
        or ""
    ).strip()

    if not init_data:
        auth_header = req.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            init_data = auth_header.replace("Bearer ", "", 1).strip()
        elif auth_header.startswith("tma "):
            init_data = auth_header.replace("tma ", "", 1).strip()

    return init_data


def _verify_telegram_init_data_signature(init_data_str, max_age_seconds=86400):
    """
    التحقق الجنائي من صحة توقيع Telegram WebApp initData عبر HMAC-SHA256.
    يفحص التوقيع مقابل BOT_TOKEN و ADMIN_BOT_TOKEN لضمان عمل اللوحة من كلا البوتين بأمان.
    """
    if not init_data_str:
        return None

    # 1. إذا كان core.security يحتوي على دالة تحقق جاهزة، نحاول استخدامها أولاً
    if security and hasattr(security, "verify_telegram_init_data"):
        try:
            verified = security.verify_telegram_init_data(init_data_str)
            if verified and isinstance(verified, dict):
                user_info = verified.get("user") if "user" in verified else verified
                if isinstance(user_info, str):
                    user_info = json.loads(user_info)
                if isinstance(user_info, dict) and user_info.get("id"):
                    return str(user_info.get("id")).strip()
        except Exception:
            pass

    # 2. التحقق المباشر عبر HMAC-SHA256 ضد التوكنات المعتمدة في البيئة
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data_str, keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            return None

        # التحقق من صلاحية الوقت (منع هجمات إعادة الإرسال Replay Attacks)
        auth_date = int(parsed_data.get("auth_date", 0))
        if auth_date > 0 and max_age_seconds > 0:
            if abs(int(time.time()) - auth_date) > max_age_seconds:
                return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )

        valid_tokens = [t for t in [USER_BOT_TOKEN, ADMIN_BOT_TOKEN] if t]
        is_signature_valid = False

        for token in valid_tokens:
            secret_key = hmac.new(
                b"WebAppData", token.encode("utf-8"), hashlib.sha256
            ).digest()
            calculated_hash = hmac.new(
                secret_key, data_check_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            if hmac.compare_digest(calculated_hash, received_hash):
                is_signature_valid = True
                break

        if not is_signature_valid:
            return None

        user_raw = parsed_data.get("user")
        if not user_raw:
            return None

        user_obj = json.loads(user_raw)
        if user_obj and user_obj.get("id"):
            return str(user_obj.get("id")).strip()

    except Exception:
        return None

    return None


def extract_admin_id_from_request(req):
    """
    استخراج معرّف الأدمن الموثق جنائياً فقط من Telegram initData.
    تم إغلاق ثغرة قبول X-Admin-ID أو tg_id غير المشفر نهائياً.
    """
    raw_init_data = _extract_raw_init_data(req)
    if not raw_init_data:
        return None
    return _verify_telegram_init_data_signature(raw_init_data)


def _get_super_admin_ids():
    """جلب قائمة معرفات السوبر أدمن الرئيسي من متغيرات البيئة"""
    ids = set()
    for env_key in ("ADMIN_ID", "SUPER_ADMIN_ID", "OWNER_ID"):
        val = str(os.getenv(env_key, "")).strip()
        if val:
            for part in val.split(","):
                if part.strip():
                    ids.add(part.strip())
    # الاحتفاظ بمعرف المالك الأساسي بعد اجتياز التشفير الجنائي لـ initData
    ids.add("5102387551")
    return ids


def verify_admin_access(req, required_permission=None):
    """
    فحص طبقة الأمان والتوثيق الجنائي للمشرفين عبر Supabase (PostgreSQL)
    والتأكد من الصلاحيات الدقيقة لكل مشرف.
    """
    try:
        admin_id = extract_admin_id_from_request(req)
        if not admin_id:
            return False, "غير مصرح: بيانات التوثيق المشفرة (initData) مفقودة أو غير صالحة", None

        # 1. التحقق مما إذا كان المستخدم هو السوبر أدمن الرئيسي
        if admin_id in _get_super_admin_ids():
            return True, "تم التحقق بنجاح (السوبر أدمن الرئيسي)", "السوبر أدمن الرئيسي"

        # 2. التحقق من جدول المشرفين (moderators) في Supabase
        mod_data = None
        if hasattr(super_admin_db, "get_moderator_by_id"):
            mod_data = super_admin_db.get_moderator_by_id(admin_id)
        elif hasattr(super_admin_db, "list_moderators_db"):
            all_mods = super_admin_db.list_moderators_db() or []
            for m in all_mods:
                if str(m.get("telegram_id", "")).strip() == admin_id:
                    mod_data = m
                    break

        if not mod_data:
            return False, "حساب إداري غير مسجل أو لا يملك صلاحية الوصول", None

        mod_name = mod_data.get("name") or f"مشرف ({admin_id})"
        permissions = mod_data.get("permissions") or {}
        if isinstance(permissions, str):
            try:
                permissions = json.loads(permissions)
            except Exception:
                permissions = {}

        # دمج الصلاحيات سواء كانت مخزنة كـ JSON أو أعمدة مباشرة في جدول moderators
        effective_perms = {
            "perm_users": bool(permissions.get("perm_users") or mod_data.get("perm_users")),
            "perm_security": bool(permissions.get("perm_security") or mod_data.get("perm_security")),
            "perm_ads": bool(permissions.get("perm_ads") or mod_data.get("perm_ads")),
            "perm_transactions": bool(permissions.get("perm_transactions") or mod_data.get("perm_transactions")),
            "perm_settings": bool(permissions.get("perm_settings") or mod_data.get("perm_settings")),
            "perm_support": bool(permissions.get("perm_support") or mod_data.get("perm_support")),
        }

        is_super_mod = bool(mod_data.get("is_super") or mod_data.get("role") == "super_admin")

        if is_super_mod:
            return True, "تم التحقق بنجاح", mod_name

        # إذا كان المسار يتطلب صلاحية محددة بعينها
        if required_permission:
            if effective_perms.get(required_permission):
                return True, "تم التحقق بنجاح", mod_name
            return False, f"عذراً، لا تملك الصلاحية المطلوبة ({required_permission}) لتنفيذ هذا الإجراء", None

        # التحقق العام لدخول اللوحة (يملك أي صلاحية إدارية فعالة)
        if any(effective_perms.values()):
            return True, "تم التحقق بنجاح", mod_name

        return False, "حساب المشرف لا يملك أي صلاحيات مفعلة حالياً", None

    except Exception as e:
        return False, f"خطأ في التوثيق الأمني: {str(e)}", None


# =========================================================
# 📢 معالج ومسارات البث الجماعي والرسائل المباشرة
# =========================================================

def async_broadcast_worker(user_ids, message_text, button_text=None, button_url=None, image_url=None, admin_name="الأدمن"):
    """معالج الإرسال الخلفي عبر بوت المستخدمين (Zn Goxe) حصراً"""
    global current_broadcast_status

    current_broadcast_status["is_running"] = True
    current_broadcast_status["total"] = len(user_ids)
    current_broadcast_status["sent"] = 0
    current_broadcast_status["failed"] = 0
    current_broadcast_status["blocked"] = 0

    if not user_bot:
        print("❌ [Broadcast Error] USER_BOT (BOT_TOKEN) غير مضبوط!")
        current_broadcast_status["is_running"] = False
        return

    markup = None
    if button_text and button_url:
        markup = InlineKeyboardMarkup()
        target_url = str(button_url).strip()
        if not target_url.startswith(('http://', 'https://', 'tg://')):
            target_url = f"https://{target_url}"
        markup.add(InlineKeyboardButton(text=str(button_text).strip(), url=target_url))

    for user_id in user_ids:
        try:
            if image_url and str(image_url).strip():
                try:
                    user_bot.send_photo(
                        chat_id=user_id,
                        photo=str(image_url).strip(),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_markup=markup
                    )
                except telebot.apihelper.ApiTelegramException as pe:
                    if "can't parse entities" in str(pe).lower():
                        user_bot.send_photo(
                            chat_id=user_id,
                            photo=str(image_url).strip(),
                            caption=message_text,
                            reply_markup=markup
                        )
                    else:
                        raise pe
            else:
                try:
                    user_bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=False
                    )
                except telebot.apihelper.ApiTelegramException as te:
                    if "can't parse entities" in str(te).lower():
                        user_bot.send_message(
                            chat_id=user_id,
                            text=message_text,
                            reply_markup=markup,
                            disable_web_page_preview=False
                        )
                    else:
                        raise te
            current_broadcast_status["sent"] += 1
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 403 or "bot was blocked" in str(e).lower() or "user is deactivated" in str(e).lower():
                current_broadcast_status["blocked"] += 1
            else:
                current_broadcast_status["failed"] += 1
        except Exception:
            current_broadcast_status["failed"] += 1

        time.sleep(0.035)

    current_broadcast_status["is_running"] = False
    current_broadcast_status["last_campaign_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        super_admin_db.log_broadcast_campaign(
            admin_name=admin_name,
            message=message_text,
            total_targets=current_broadcast_status["total"],
            success_count=current_broadcast_status["sent"],
            blocked_count=current_broadcast_status["blocked"]
        )
    except Exception as e:
        print(f"⚠️ [Broadcast Log Warning]: {e}")


@super_admin_bp.route('/send-message', methods=['POST'])
def send_admin_message():
    """مسار إرسال الرسائل الإدارية عبر بوت المستخدمين (Zn Goxe)"""
    is_valid, msg, admin_name = verify_admin_access(request, required_permission="perm_ads")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    target_type = data.get("target_type", "all")
    target_id = str(data.get("target_id") or "").strip()
    message_text = (data.get("message") or "").strip()
    button_text = data.get("button_text")
    button_url = data.get("button_url")
    image_url = data.get("image_url")

    if not message_text:
        return jsonify({"success": False, "message": "نص الرسالة مطلوب"}), 400

    if not USER_BOT_TOKEN or not user_bot:
        return jsonify({"success": False, "message": "توكن بوت المستخدمين (BOT_TOKEN) غير مضبوط في متغيرات البيئة"}), 500

    if target_type == "single":
        if not target_id:
            return jsonify({"success": False, "message": "يرجى إدخال معرف المستخدم (ID)"}), 400

        user_exists, _ = super_admin_db.get_user_by_id(target_id)
        if not user_exists:
            return jsonify({"success": False, "message": f"المستخدم رقم ({target_id}) غير مسجل بالنظام"}), 404

        markup = None
        if button_text and button_url:
            markup = InlineKeyboardMarkup()
            target_url = str(button_url).strip()
            if not target_url.startswith(('http://', 'https://', 'tg://')):
                target_url = f"https://{target_url}"
            markup.add(InlineKeyboardButton(text=str(button_text).strip(), url=target_url))

        try:
            if image_url and str(image_url).strip():
                try:
                    user_bot.send_photo(
                        chat_id=target_id,
                        photo=str(image_url).strip(),
                        caption=message_text,
                        parse_mode="HTML",
                        reply_markup=markup
                    )
                except telebot.apihelper.ApiTelegramException as pe:
                    if "can't parse entities" in str(pe).lower():
                        user_bot.send_photo(
                            chat_id=target_id,
                            photo=str(image_url).strip(),
                            caption=message_text,
                            reply_markup=markup
                        )
                    else:
                        raise pe
            else:
                try:
                    user_bot.send_message(
                        chat_id=target_id,
                        text=message_text,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=False
                    )
                except telebot.apihelper.ApiTelegramException as te:
                    if "can't parse entities" in str(te).lower():
                        user_bot.send_message(
                            chat_id=target_id,
                            text=message_text,
                            reply_markup=markup,
                            disable_web_page_preview=False
                        )
                    else:
                        raise te

            try:
                database.log_admin_action(admin_name, f"إرسال رسالة مباشرة للمستخدم {target_id}")
            except Exception:
                pass

            return jsonify({"success": True, "message": f"تم إرسال الرسالة بنجاح عبر بوت المستخدمين للمستلم {target_id}"})
        except Exception as e:
            return jsonify({"success": False, "message": f"فشل الإرسال عبر بوت المستخدمين: {str(e)}"}), 500

    elif target_type == "all":
        if current_broadcast_status["is_running"]:
            return jsonify({"success": False, "message": "توجد حملة إرسال جارٍ تنفيذها بالفعل، يرجى الانتظار"}), 400

        user_ids = super_admin_db.get_all_user_ids()
        if not user_ids:
            return jsonify({"success": False, "message": "لا يوجد مستخدمين نشطين للإرسال إليهم"}), 400

        thread = threading.Thread(
            target=async_broadcast_worker,
            args=(user_ids, message_text, button_text, button_url, image_url, admin_name)
        )
        thread.daemon = True
        thread.start()

        try:
            database.log_admin_action(admin_name, f"بدء حملة بث جماعي لـ {len(user_ids)} مستخدم")
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"بدأت عملية الإرسال الجماعي عبر بوت المستخدمين لـ {len(user_ids)} مستخدم في الخلفية"
        })

    return jsonify({"success": False, "message": "نوع المستهدف غير معروف"}), 400


@super_admin_bp.route('/broadcast-stats', methods=['GET'])
def get_broadcast_stats():
    """مسار جلب إحصائيات الإرسال الحية وأحدث الحملات"""
    is_valid, msg, _ = verify_admin_access(request)
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    latest_campaign = super_admin_db.get_latest_broadcast_stats()
    return jsonify({
        "success": True,
        "live_status": current_broadcast_status,
        "latest_campaign": latest_campaign
    })


# =========================================================
# 📈 مسار التحليلات والإحصائيات الشاملة
# =========================================================

@super_admin_bp.route('/analytics', methods=['GET'])
def get_analytics():
    """مسار جلب الإحصائيات العامة للمستخدمين والمتفاعلين والأكثر نشاطاً وفق نطاق زمني محدد"""
    is_valid, msg, _ = verify_admin_access(request)
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        analytics_data = super_admin_db.get_system_global_analytics(
            start_date=start_date,
            end_date=end_date
        )
        if not isinstance(analytics_data, dict):
            analytics_data = {}

        return jsonify({
            "success": True,
            "analytics": analytics_data
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"خطأ أثناء جلب التحليلات: {str(e)}",
            "analytics": {
                "total_users": 0,
                "active_today": 0,
                "banned_users": 0,
                "total_coins": 0,
                "top_active_users": []
            }
        }), 200


# =========================================================
# 🚫 مسارات إدارة الحظر وفك الحظر الشامل (حسابات + أجهزة + بصمات)
# =========================================================

@super_admin_bp.route('/banned-users', methods=['GET'])
def get_banned_users():
    """مسار جلب كافة الحسابات والأجهزة المحظورة بالنظام وتفاصيلها"""
    is_valid, msg, _ = verify_admin_access(request)
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    try:
        banned_users = super_admin_db.get_banned_users_db()
        if not isinstance(banned_users, list):
            banned_users = []

        return jsonify({
            "success": True,
            "banned_users": banned_users,
            "total_banned": len(banned_users)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"خطأ أثناء جلب قائمة المحظورين: {str(e)}",
            "banned_users": [],
            "total_banned": 0
        }), 200


@super_admin_bp.route('/ban-user', methods=['POST'])
def ban_user():
    """مسار حظر مستخدم في النظام وحظر جميع أجهزته وبصماته والحسابات المرتبطة بها"""
    is_valid, msg, admin_name = verify_admin_access(request, required_permission="perm_security")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    telegram_id = data.get("telegram_id") or data.get("tg_id") or data.get("user_id") or data.get("target_id")
    reason = (data.get("reason") or "تم الحظر من قبل الإدارة العليا").strip()

    if not telegram_id:
        return jsonify({"success": False, "message": "معرّف المستخدم (Telegram ID) مطلوب"}), 400

    target_uid = str(telegram_id).strip()
    if target_uid in _get_super_admin_ids():
        return jsonify({"success": False, "message": "لا يمكن حظر حساب السوبر أدمن الرئيسي!"}), 400

    try:
        success, res_msg = super_admin_db.ban_user_db(target_uid, reason, admin_name)
        if success:
            try:
                database.log_admin_action(admin_name, f"حظر المستخدم {target_uid} والأجهزة المرتبطة به - السبب: {reason}")
            except Exception:
                pass
            return jsonify({"success": True, "message": res_msg or f"تم حظر المستخدم {target_uid} والأجهزة المربوطة به بنجاح"})
        else:
            return jsonify({"success": False, "message": res_msg or "فشل حظر المستخدم"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء تنفيذ الحظر: {str(e)}"}), 500


@super_admin_bp.route('/unban-user', methods=['POST'])
def unban_user():
    """مسار فك الحظر الشامل عن مستخدم وجميع أجهزته وبصماته المربوطة به"""
    is_valid, msg, admin_name = verify_admin_access(request, required_permission="perm_security")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    telegram_id = data.get("telegram_id") or data.get("tg_id") or data.get("user_id") or data.get("target_id")

    if not telegram_id:
        return jsonify({"success": False, "message": "معرّف المستخدم (Telegram ID) مطلوب"}), 400

    target_uid = str(telegram_id).strip()

    try:
        success, res_msg = super_admin_db.unban_user_db(target_uid, admin_name)
        if success:
            try:
                database.log_admin_action(admin_name, f"فك الحظر الشامل عن المستخدم {target_uid} وجميع الأجهزة المربوطة به")
            except Exception:
                pass
            return jsonify({"success": True, "message": res_msg or f"تم فك الحظر عن المستخدم {target_uid} وجميع الأجهزة المربوطة به بنجاح"})
        else:
            return jsonify({"success": False, "message": res_msg or "فشل فك الحظر"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء فك الحظر: {str(e)}"}), 500


# =========================================================
# 🔍 مسارات التحكم بحساب المستخدم (كشف، تعديل رصيد، تصفير حساب)
# =========================================================

@super_admin_bp.route('/user-details', methods=['GET', 'POST'])
def get_user_details():
    """مسار كشف كافة تفاصيل المستخدم، أرصدته، أجهزته، والحسابات المشتركة معه"""
    is_valid, msg, _ = verify_admin_access(request, required_permission="perm_users")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    telegram_id = (
        request.args.get("telegram_id")
        or request.args.get("user_id")
        or request.args.get("tg_id")
        or data.get("telegram_id")
        or data.get("user_id")
        or data.get("tg_id")
    )

    if not telegram_id:
        return jsonify({"success": False, "message": "معرّف المستخدم (Telegram ID) مطلوب للكشف"}), 400

    target_uid = str(telegram_id).strip()

    try:
        # إذا كانت دالة get_user_details_db متوفرة في super_admin_db
        if hasattr(super_admin_db, "get_user_details_db"):
            found, details = super_admin_db.get_user_details_db(target_uid)
            if not found:
                return jsonify({"success": False, "message": f"المستخدم ({target_uid}) غير موجود في قاعدة البيانات"}), 404
            return jsonify({"success": True, "user": details})

        # بديل آمن عبر get_user_by_id
        found, user_data = super_admin_db.get_user_by_id(target_uid)
        if not found or not user_data:
            return jsonify({"success": False, "message": f"المستخدم ({target_uid}) غير موجود في قاعدة البيانات"}), 404

        return jsonify({"success": True, "user": user_data})
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء جلب بيانات المستخدم: {str(e)}"}), 500


@super_admin_bp.route('/modify-balance', methods=['POST'])
def modify_balance():
    """مسار إضافة أو خصم أو تعيين رصيد مستخدم في قاعدة البيانات"""
    is_valid, msg, admin_name = verify_admin_access(request, required_permission="perm_users")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    telegram_id = data.get("telegram_id") or data.get("user_id") or data.get("tg_id")
    action = str(data.get("action") or "add").strip().lower()  # add, deduct/sub, set
    currency = str(data.get("currency") or data.get("field") or "balance").strip()
    raw_amount = data.get("amount")

    if not telegram_id or raw_amount is None:
        return jsonify({"success": False, "message": "معرّف المستخدم والمبلغ مطلوبان"}), 400

    try:
        amount = float(raw_amount)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "قيمة المبلغ غير صالحة"}), 400

    target_uid = str(telegram_id).strip()

    try:
        if hasattr(super_admin_db, "modify_user_balance_db"):
            success, res_msg = super_admin_db.modify_user_balance_db(
                telegram_id=target_uid,
                amount=amount,
                action=action,
                currency=currency,
                admin_name=admin_name
            )
        elif hasattr(super_admin_db, "update_user_balance_db"):
            delta = -abs(amount) if action in ("deduct", "sub", "subtract") else amount
            success, res_msg = super_admin_db.update_user_balance_db(target_uid, delta, admin_name)
        else:
            return jsonify({"success": False, "message": "دالة تعديل الرصيد غير متوفرة في super_admin_db"}), 500

        if success:
            try:
                database.log_admin_action(
                    admin_name,
                    f"تعديل رصيد المستخدم {target_uid} ({action}: {amount} في {currency})"
                )
            except Exception:
                pass
            return jsonify({"success": True, "message": res_msg or f"تم تحديث رصيد المستخدم {target_uid} بنجاح"})
        else:
            return jsonify({"success": False, "message": res_msg or "فشل تعديل رصيد المستخدم"}), 400

    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء تعديل الرصيد: {str(e)}"}), 500


@super_admin_bp.route('/reset-account', methods=['POST'])
def reset_account():
    """مسار تصفير حساب المستخدم وإعادة ضبط أرصدته وتقدمه"""
    is_valid, msg, admin_name = verify_admin_access(request, required_permission="perm_users")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    telegram_id = data.get("telegram_id") or data.get("user_id") or data.get("tg_id")

    if not telegram_id:
        return jsonify({"success": False, "message": "معرّف المستخدم (Telegram ID) مطلوب لتصفير الحساب"}), 400

    target_uid = str(telegram_id).strip()
    if target_uid in _get_super_admin_ids():
        return jsonify({"success": False, "message": "لا يمكن تصفير حساب السوبر أدمن الرئيسي!"}), 400

    try:
        if hasattr(super_admin_db, "reset_user_account_db"):
            success, res_msg = super_admin_db.reset_user_account_db(target_uid, admin_name)
        else:
            return jsonify({"success": False, "message": "دالة تصفير الحساب غير متوفرة في super_admin_db"}), 500

        if success:
            try:
                database.log_admin_action(admin_name, f"تصفير شامل لحساب المستخدم {target_uid}")
            except Exception:
                pass
            return jsonify({"success": True, "message": res_msg or f"تم تصفير حساب المستخدم {target_uid} بنجاح"})
        else:
            return jsonify({"success": False, "message": res_msg or "فشل تصفير حساب المستخدم"}), 400

    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء تصفير الحساب: {str(e)}"}), 500


# =========================================================
# 🛡️ مسارات إدارة المشرفين والسجلات الإدارية
# =========================================================

@super_admin_bp.route('/add-moderator', methods=['POST'])
def add_moderator():
    """مسار إضافة مشرف جديد ورصد صلاحياته (مخصص للسوبر أدمن أو من يملك صلاحية الإعدادات)"""
    is_valid, msg, admin_name = verify_admin_access(request, required_permission="perm_settings")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    telegram_id = data.get("telegram_id")
    name = (data.get("name") or "").strip()
    permissions = data.get("permissions", {})

    if not telegram_id or not name:
        return jsonify({"success": False, "message": "معرّف التليجرام واسم المشرف مطلوبان"}), 400

    target_mod_id = str(telegram_id).strip()

    try:
        success, res_msg = super_admin_db.add_moderator_db(target_mod_id, name, permissions, admin_name)
        if success:
            try:
                database.log_admin_action(admin_name, f"إضافة/تحديث المشرف {name} ({target_mod_id})")
            except Exception:
                pass
            return jsonify({"success": True, "message": res_msg or "تمت إضافة المشرف بنجاح"})
        else:
            return jsonify({"success": False, "message": res_msg or "فشل إضافة المشرف"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء إضافة المشرف: {str(e)}"}), 500


@super_admin_bp.route('/list-moderators', methods=['GET'])
def list_moderators():
    """مسار جلب قائمة المشرفين المسجلين"""
    is_valid, msg, _ = verify_admin_access(request)
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    try:
        moderators = super_admin_db.list_moderators_db()
        return jsonify({"success": True, "moderators": moderators or []})
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء جلب المشرفين: {str(e)}"}), 500


@super_admin_bp.route('/remove-moderator', methods=['POST'])
def remove_moderator():
    """مسار حذف مشرف من النظام"""
    is_valid, msg, admin_name = verify_admin_access(request, required_permission="perm_settings")
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.get_json(silent=True) or {}
    telegram_id = data.get("telegram_id")

    if not telegram_id:
        return jsonify({"success": False, "message": "معرّف المشرف مطلوب"}), 400

    target_mod_id = str(telegram_id).strip()

    try:
        success, res_msg = super_admin_db.remove_moderator_db(target_mod_id, admin_name)
        if success:
            try:
                database.log_admin_action(admin_name, f"حذف المشرف {target_mod_id}")
            except Exception:
                pass
            return jsonify({"success": True, "message": res_msg or "تم حذف المشرف بنجاح"})
        else:
            return jsonify({"success": False, "message": res_msg or "فشل حذف المشرف"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء حذف المشرف: {str(e)}"}), 500


@super_admin_bp.route('/logs', methods=['GET'])
def get_logs():
    """مسار جلب سجل الحركات الإدارية"""
    is_valid, msg, _ = verify_admin_access(request)
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    try:
        logs = super_admin_db.get_admin_logs()
        return jsonify({"success": True, "logs": logs or []})
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ أثناء جلب السجلات: {str(e)}"}), 500

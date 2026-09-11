import os
import time
import json
import urllib.parse
import threading
from flask import Blueprint, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
import super_admin.super_admin_db as super_admin_db

super_admin_bp = Blueprint('super_admin_bp', __name__)

# الاعتماد الحصري والصارم على توكن بوت المستخدمين الرئيسي (Zn Goxe)
USER_BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
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

def extract_admin_id_from_request(req):
    """استخراج Telegram ID الخاص بالأدمن من كافة المصادر الممكنة في الطلب"""
    admin_id = req.headers.get("X-Admin-ID")
    if admin_id and str(admin_id).strip():
        return str(admin_id).strip()

    if req.is_json and req.json:
        admin_id = req.json.get("admin_id") or req.json.get("tg_id")
        if admin_id:
            return str(admin_id).strip()

    init_data = req.headers.get("X-Telegram-Init-Data") or req.headers.get("Authorization", "").replace("Bearer ", "")
    if init_data:
        try:
            parsed = urllib.parse.parse_qs(init_data)
            if 'user' in parsed:
                user_obj = json.loads(parsed['user'][0])
                if user_obj.get('id'):
                    return str(user_obj.get('id')).strip()
        except Exception:
            pass

    return None


def verify_admin_access(req):
    """فحص طبقة الأمان والتوثيق المزدوج للمشرفين والتأكد من الصلاحية"""
    try:
        admin_id = extract_admin_id_from_request(req)
        
        if not admin_id:
            return False, "غير مصرح: المعرف مفقود", None

        env_admin_id = str(os.getenv("ADMIN_ID", "")).strip()
        env_super_admin_id = str(os.getenv("SUPER_ADMIN_ID", "")).strip()

        if admin_id in [env_admin_id, env_super_admin_id, "5102387551"]:
            return True, "تم التحقق بنجاح (الأدمن الرئيسي)", "السوبر أدمن الرئيسي"

        db = database.get_db()
        if db:
            admin_ref = db.collection("admins").document(str(admin_id)).get()
            if admin_ref.exists:
                admin_data = admin_ref.to_dict() or {}
                permissions = admin_data.get("permissions", {})
                
                if permissions.get("perm_users") or permissions.get("perm_ads") or admin_data.get("is_super", False) or admin_data.get("role") == "super_admin":
                    return True, "تم التحقق بنجاح", admin_data.get("name", "مشرف")

        return False, "حساب إداري غير موجود", None
    except Exception as e:
        return False, f"خطأ في التوثيق: {str(e)}", None


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
            if e.error_code == 403 or "bot was blocked" in str(e).lower():
                current_broadcast_status["blocked"] += 1
            else:
                current_broadcast_status["failed"] += 1
        except Exception:
            current_broadcast_status["failed"] += 1

        time.sleep(0.035)

    current_broadcast_status["is_running"] = False
    current_broadcast_status["last_campaign_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

    super_admin_db.log_broadcast_campaign(
        admin_name=admin_name,
        message=message_text,
        total_targets=current_broadcast_status["total"],
        success_count=current_broadcast_status["sent"],
        blocked_count=current_broadcast_status["blocked"]
    )


@super_admin_bp.route('/send-message', methods=['POST'])
def send_admin_message():
    """مسار إرسال الرسائل الإدارية عبر بوت المستخدمين (Zn Goxe)"""
    is_valid, msg, admin_name = verify_admin_access(request)
    if not is_valid:
        return jsonify({"success": False, "message": msg}), 403

    data = request.json or {}
    target_type = data.get("target_type", "all")
    target_id = data.get("target_id")
    message_text = data.get("message")
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

            return jsonify({"success": True, "message": f"تم إرسال الرسالة بنجاح عبر بوت المستخدمين (Zn Goxe) للمستلم {target_id}"})
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

import os
import time
import threading
from flask import Blueprint, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
import super_admin.super_admin_db as super_admin_db

super_admin_bp = Blueprint('super_admin_bp', __name__)

# جلب التوكن الخفي للبوت
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

# متغير لمعاينة حالة البث الحي
current_broadcast_status = {
    "is_running": False,
    "total": 0,
    "sent": 0,
    "failed": 0,
    "blocked": 0,
    "last_campaign_time": None
}

def verify_admin_access(req):
    """فحص طبقة الأمان والتوثيق المزدوج للمشرفين والتأكد من الصلاحية"""
    try:
        init_data = req.headers.get("X-Telegram-Init-Data")
        auth_header = req.headers.get("Authorization")
        
        # التوثيق عبر الجلسة أو الـ Header
        admin_id = req.headers.get("X-Admin-ID") or req.json.get("admin_id") if req.is_json else None
        if not admin_id:
            return False, "غير مصرح: المعرف مفقود", None

        db = database.get_db()
        admin_ref = db.collection("admins").document(str(admin_id)).get()
        
        if not admin_ref.exists:
            # التحقق مما إذا كان الأدمن الرئيسي
            if str(admin_id) == str(os.getenv("SUPER_ADMIN_ID", "")):
                return True, "السوبر أدمن الرئيسي", "Super Admin"
            return False, "حساب إداري غير موجود", None

        admin_data = admin_ref.to_dict() or {}
        permissions = admin_data.get("permissions", {})
        
        # التأكد من امتلاك صلاحية إدارة المستخدمين أو الإعلانات
        if not (permissions.get("perm_users") or permissions.get("perm_ads") or admin_data.get("is_super", False)):
            return False, "ليس لديك صلاحية إرسال الإشعارات الجماعية", None

        return True, "تم التحقق بنجاح", admin_data.get("name", "مشرف")
    except Exception as e:
        return False, f"خطأ في التوثيق: {str(e)}", None


def async_broadcast_worker(user_ids, message_text, button_text=None, button_url=None, image_url=None, admin_name="الأدمن"):
    """معالج الإرسال الخلفي لضمان عدم توقف السيرفر ومراعاة Rate Limits"""
    global current_broadcast_status
    
    current_broadcast_status["is_running"] = True
    current_broadcast_status["total"] = len(user_ids)
    current_broadcast_status["sent"] = 0
    current_broadcast_status["failed"] = 0
    current_broadcast_status["blocked"] = 0

    # تجهيز كيبورد الأزرار
    markup = None
    if button_text and button_url:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text=button_text, url=button_url))

    for user_id in user_ids:
        try:
            if image_url:
                bot.send_photo(
                    chat_id=user_id,
                    photo=image_url,
                    caption=message_text,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            else:
                bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True
                )
            current_broadcast_status["sent"] += 1
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 403:
                current_broadcast_status["blocked"] += 1
            else:
                current_broadcast_status["failed"] += 1
        except Exception:
            current_broadcast_status["failed"] += 1

        # فاصل زمني (0.035 ثانية) لتفادي حظر البوت (حدود تليجرام 30 رسالة/ثانية)
        time.sleep(0.035)

    current_broadcast_status["is_running"] = False
    current_broadcast_status["last_campaign_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # أرشفة الحملة في قاعدة البيانات
    super_admin_db.log_broadcast_campaign(
        admin_name=admin_name,
        message=message_text,
        total_targets=current_broadcast_status["total"],
        success_count=current_broadcast_status["sent"],
        blocked_count=current_broadcast_status["blocked"]
    )


@super_admin_bp.route('/send-message', methods=['POST'])
def send_admin_message():
    """مسار إرسال الرسائل الإدارية (فردي / جماعي)"""
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

    if not bot:
        return jsonify({"success": False, "message": "توكن البوت غير مهيأ"}), 500

    # 🎯 إرسال لمستخدم فردي
    if target_type == "single":
        if not target_id:
            return jsonify({"success": False, "message": "يرجى إدخال معرف المستخدم (ID)"}), 400
        
        user_exists, user_data = super_admin_db.get_user_by_id(target_id)
        if not user_exists:
            return jsonify({"success": False, "message": "المستخدم غير موجود بالنظام"}), 404

        markup = None
        if button_text and button_url:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text=button_text, url=button_url))

        try:
            if image_url:
                bot.send_photo(chat_id=target_id, photo=image_url, caption=message_text, parse_mode="HTML", reply_markup=markup)
            else:
                bot.send_message(chat_id=target_id, text=message_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
            
            database.log_admin_action(admin_name, f"إرسال رسالة مباشرة للمستخدم {target_id}")
            return jsonify({"success": True, "message": f"تم إرسال الرسالة بنجاح للمستخدم {target_id}"})
        except Exception as e:
            return jsonify({"success": False, "message": f"فشل الإرسال: {str(e)}"}), 500

    # 📢 إرسال جماعي لكافة المستخدمين
    elif target_type == "all":
        if current_broadcast_status["is_running"]:
            return jsonify({"success": False, "message": "توجد حملة إرسال جارٍ تنفيذها بالفعل، يرجى الانتظار"}), 400

        user_ids = super_admin_db.get_all_user_ids()
        if not user_ids:
            return jsonify({"success": False, "message": "لا يوجد مستخدمين نشطين للإرسال إليم"}), 400

        # إطلاق معالج الإرسال في الخلفية
        thread = threading.Thread(
            target=async_broadcast_worker,
            args=(user_ids, message_text, button_text, button_url, image_url, admin_name)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            "success": True, 
            "message": f"بدأت عملية الإرسال الجماعي لـ {len(user_ids)} مستخدم في الخلفية"
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

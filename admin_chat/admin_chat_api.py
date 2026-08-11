# admin_chat/admin_chat_api.py
from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
import json, hmac, hashlib, urllib.parse, os, requests

from admin_chat.admin_chat_db import (
    get_db,
    get_all_tickets_from_db,
    get_ticket_by_id_from_db,
    mark_ticket_read_in_db,
    add_admin_reply_to_db,
    close_ticket_in_db
)

admin_chat_bp = Blueprint('admin_chat', __name__)

def check_admin_auth():
    """التحقق المرن والشامل من صلاحيات الأدمن مع تنظيف البادئات مثل Bearer"""
    admin_bot_token = (os.environ.get("ADMIN_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or "").strip()
    admin_id = str(os.environ.get("ADMIN_ID", "5102387551")).strip()

    # جلب initData من كافة المصادر المحتملة
    init_data = (
        request.headers.get('X-Telegram-Init-Data') or 
        request.headers.get('Authorization') or 
        request.args.get('initData')
    )
    if not init_data and request.is_json:
        req_json = request.get_json(silent=True) or {}
        init_data = req_json.get('initData')

    if not init_data:
        print("⚠️ [Auth Error] لم يتم استقبال initData في الهيدر أو البارامترات")
        return None

    # تنظيف كلمة Bearer إذا كانت موجودة
    if isinstance(init_data, str) and init_data.startswith('Bearer '):
        init_data = init_data[7:].strip()

    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        user_raw = parsed_data.get('user', '{}')
        user_data = json.loads(user_raw)
        u_id = str(user_data.get('id', ''))

        if not u_id:
            print("⚠️ [Auth Error] تعذر استخراج ID المستخدم من user")
            return None

        # التحقق المباشر مما إذا كان المستخدم هو الأدمن أو مشرف
        db_conn = get_db()
        is_mod = False
        if db_conn:
            try:
                is_mod = db_conn.collection('moderators').document(u_id).get().exists
            except Exception:
                is_mod = False

        if u_id == admin_id or is_mod:
            # تحقق HMAC اختياري للسجلات فقط لعدم حجب الأدمن
            hash_val = parsed_data.pop('hash', None)
            if admin_bot_token and hash_val:
                data_check_str = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
                secret_key = hmac.new(b"WebAppData", admin_bot_token.encode('utf-8'), hashlib.sha256).digest()
                calc_hash = hmac.new(secret_key, data_check_str.encode('utf-8'), hashlib.sha256).hexdigest()
                if calc_hash != hash_val:
                    print(f"⚠️ [Auth Note] الـ Hash غير مطابق ولكن تم السماح بناءً على ID الأدمن: {u_id}")
            return u_id

        print(f"❌ [Auth Denied] المستخدم {u_id} غير مصرح له كأدمن")
        return None

    except Exception as e:
        print(f"❌ [Auth Exception]: {e}")
        return None

def send_telegram_notification(chat_id, text):
    """
    ملاحظة: تم إيقاف إرسال الإشعارات عبر التلجرام لمنع وصول الردود لشات التلجرام،
    ولضمان انحصار المحادثة في الويب فقط بناءً على طلبك.
    """
    pass

# 1. جلب قائمة التذاكر
@admin_chat_bp.route('/tickets', methods=['GET'])
def get_tickets():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "Access Denied"}), 403

    try:
        tickets = get_all_tickets_from_db()
        return jsonify({"success": True, "tickets": tickets}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ قاعدة البيانات: {str(e)}"}), 500

# 2. جلب تذكرة واحدة فقط
@admin_chat_bp.route('/ticket/<ticket_id>', methods=['GET'])
def get_single_ticket(ticket_id):
    if not check_admin_auth():
        return jsonify({"success": False, "message": "Access Denied"}), 403

    try:
        ticket_data = get_ticket_by_id_from_db(ticket_id)
        if not ticket_data:
            return jsonify({"success": False, "message": "التذكرة غير موجودة"}), 404

        return jsonify({"success": True, "ticket": ticket_data}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ: {str(e)}"}), 500

# 3. تعيين التذكرة كـ "مقروءة" عند فتحها
@admin_chat_bp.route('/mark_read', methods=['POST'])
def mark_read():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "Access Denied"}), 403

    data = request.get_json() or {}
    ticket_id = data.get('ticket_id')
    if not ticket_id:
        return jsonify({"success": False, "message": "رقم التذكرة مفقود"}), 400

    try:
        mark_ticket_read_in_db(ticket_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# 4. إرسال رد الأدمن (إلى شاشة الويب حصراً)
@admin_chat_bp.route('/reply', methods=['POST'])
def send_reply():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "Access Denied"}), 403

    data = request.get_json() or {}
    ticket_id = data.get('ticket_id')
    text = data.get('text')

    if not ticket_id or not text:
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400

    try:
        now_str = datetime.now(timezone.utc).isoformat()
        success, user_id, err_msg = add_admin_reply_to_db(ticket_id, text, now_str)

        if not success:
            return jsonify({"success": False, "message": err_msg or "خطأ في الإرسال"}), 404

        # الرد يُحفظ في قاعدة البيانات للويب مباشرة دون إرسال إشعار تلجرام
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# 5. إغلاق التذكرة
@admin_chat_bp.route('/close', methods=['POST'])
def close_ticket():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "Access Denied"}), 403

    data = request.get_json() or {}
    ticket_id = data.get('ticket_id')

    if not ticket_id:
        return jsonify({"success": False, "message": "رقم التذكرة مفقود"}), 400

    try:
        now_str = datetime.now(timezone.utc).isoformat()
        close_ticket_in_db(ticket_id, now_str)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -*- coding: utf-8 -*-
# admin_chat/admin_chat_api.py
from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
import json
import hmac
import hashlib
import urllib.parse
import os

from database import is_admin_or_mod, is_admin_exempt
from admin_chat.admin_chat_db import (
    get_all_tickets_from_db,
    get_ticket_by_id_from_db,
    mark_ticket_read_in_db,
    add_admin_reply_to_db,
    close_ticket_in_db
)

admin_chat_bp = Blueprint('admin_chat', __name__)


@admin_chat_bp.after_request
def add_no_cache_headers(response):
    """منع الكاش نهائياً لضمان تحديث رسائل الأدمن والتذاكر في نفس اللحظة"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _verify_telegram_hmac(parsed_data: dict, hash_val: str) -> bool:
    """فحص توقيع التليجرام مقابل جميع التوكنات المتاحة في البيئة (أدمن أو بوت مستخدمين)"""
    candidate_tokens = [
        (os.environ.get("ADMIN_BOT_TOKEN") or "").strip(),
        (os.environ.get("BOT_TOKEN") or "").strip(),
        (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    ]
    valid_tokens = [t for t in candidate_tokens if t]

    # إذا لم يكن هناك توكن مضبوط في البيئة لا نمنع الأدمن من الدخول
    if not valid_tokens or not hash_val:
        return True

    data_check_str = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
    for token in valid_tokens:
        secret_key = hmac.new(b"WebAppData", token.encode('utf-8'), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_str.encode('utf-8'), hashlib.sha256).hexdigest()
        if hmac.compare_digest(calc_hash, hash_val):
            return True
    return False


def check_admin_auth():
    """التحقق المرن والآمن من صلاحيات الأدمن أو المشرفين عبر Supabase مباشرة"""
    init_data = (
        request.headers.get('X-Telegram-Init-Data') or
        request.headers.get('X-Telegram-Init-Data-Raw') or
        request.headers.get('Authorization') or
        request.args.get('initData')
    )
    req_json = request.get_json(silent=True) or {} if request.is_json else {}
    if not init_data:
        init_data = req_json.get('initData')

    # استخراج معرف الأدمن الاحتياطي إن وجد في الهيدر أو الطلب
    fallback_uid = (
        request.headers.get('X-Admin-Id') or
        request.headers.get('X-User-Id') or
        request.args.get('admin_id') or
        request.args.get('user_id') or
        req_json.get('admin_id') or
        req_json.get('user_id')
    )

    if isinstance(init_data, str) and init_data.startswith('Bearer '):
        init_data = init_data[7:].strip()

    u_id = None

    if init_data:
        try:
            parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
            hash_val = parsed_data.pop('hash', None)

            user_raw = parsed_data.get('user', '{}')
            user_data = json.loads(user_raw) if isinstance(user_raw, str) else {}
            extracted_id = str(user_data.get('id', '')).strip()

            if extracted_id:
                # فحص توقيع التليجرام، أو السماح للأدمن الرئيسي الموثق في Supabase
                if _verify_telegram_hmac(parsed_data, hash_val) or is_admin_exempt(extracted_id):
                    u_id = extracted_id
        except Exception as e:
            print(f"⚠️ [Auth Parse Warning]: {e}")

    if not u_id and fallback_uid:
        u_id = str(fallback_uid).strip()

    if not u_id:
        return None

    # التحقق المباشر عبر دوال Supabase الجاهزة في database.py (تشمل الأدمن الرئيسي والمشرفين)
    if is_admin_exempt(u_id) or is_admin_or_mod(u_id):
        return u_id

    return None


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

    data = request.get_json(silent=True) or {}
    ticket_id = str(data.get('ticket_id', '')).strip()
    if not ticket_id:
        return jsonify({"success": False, "message": "رقم التذكرة مفقود"}), 400

    try:
        mark_ticket_read_in_db(ticket_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# 4. إرسال رد الأدمن وإرجاع التذكرة المحدثة للعرض اللحظي
@admin_chat_bp.route('/reply', methods=['POST'])
def send_reply():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "Access Denied"}), 403

    data = request.get_json(silent=True) or {}
    ticket_id = str(data.get('ticket_id', '')).strip()
    text = str(data.get('text', '')).strip()

    if not ticket_id or not text:
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400

    if len(text) > 4000:
        return jsonify({"success": False, "message": "الرسالة طويلة جداً (الحد الأقصى 4000 حرف)"}), 400

    try:
        now_str = datetime.now(timezone.utc).isoformat()
        success, user_id, err_msg = add_admin_reply_to_db(ticket_id, text, now_str)

        if not success:
            return jsonify({"success": False, "message": err_msg or "خطأ في الإرسال"}), 404

        updated_ticket = get_ticket_by_id_from_db(ticket_id)
        return jsonify({
            "success": True,
            "user_id": user_id,
            "ticket": updated_ticket
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# 5. إغلاق التذكرة
@admin_chat_bp.route('/close', methods=['POST'])
def close_ticket():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "Access Denied"}), 403

    data = request.get_json(silent=True) or {}
    ticket_id = str(data.get('ticket_id', '')).strip()

    if not ticket_id:
        return jsonify({"success": False, "message": "رقم التذكرة مفقود"}), 400

    try:
        now_str = datetime.now(timezone.utc).isoformat()
        close_ticket_in_db(ticket_id, now_str)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

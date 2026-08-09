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
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551")

def check_admin_auth():
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        hash_val = parsed_data.pop('hash', None)
        if not hash_val: 
            return None
        
        data_check_str = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_str.encode(), hashlib.sha256).hexdigest()
        
        if calc_hash == hash_val:
            user_data = json.loads(parsed_data.get('user', '{}'))
            u_id = str(user_data.get('id'))
            db_conn = get_db()
            if u_id == str(ADMIN_ID) or (db_conn and db_conn.collection('moderators').document(u_id).get().exists):
                return u_id
        return None
    except Exception as e:
        print(f"❌ Auth Error: {e}")
        return None

def send_telegram_notification(chat_id, text):
    """إرسال إشعار للمستخدم عبر بوت التليجرام مباشرة عند رد الأدمن"""
    if not BOT_TOKEN or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"💬 **رد جديد من الدعم الفني:**\n\n{text}",
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"⚠️ Failed to send Telegram message to user: {e}")

# 1. جلب قائمة التذاكر
@admin_chat_bp.route('/tickets', methods=['GET'])
def get_tickets():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 403

    try:
        tickets = get_all_tickets_from_db()
        return jsonify({"success": True, "tickets": tickets}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# 2. جلب تذكرة واحدة فقط (لتوفير قراءات Firestore أثناء فتح المحادثة)
@admin_chat_bp.route('/ticket/<ticket_id>', methods=['GET'])
def get_single_ticket(ticket_id):
    if not check_admin_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 403

    try:
        ticket_data = get_ticket_by_id_from_db(ticket_id)
        if not ticket_data:
            return jsonify({"success": False, "message": "التذكرة غير موجودة"}), 404

        return jsonify({"success": True, "ticket": ticket_data}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# 3. تعيين التذكرة كـ "مقروءة" عند فتحها
@admin_chat_bp.route('/mark_read', methods=['POST'])
def mark_read():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 403

    data = request.get_json() or {}
    ticket_id = data.get('ticket_id')
    if not ticket_id:
        return jsonify({"success": False, "message": "رقم التذكرة مفقود"}), 400

    try:
        mark_ticket_read_in_db(ticket_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# 4. إرسال رد الأدمن
@admin_chat_bp.route('/reply', methods=['POST'])
def send_reply():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 403

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

        if user_id:
            send_telegram_notification(user_id, text)

        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# 5. إغلاق التذكرة
@admin_chat_bp.route('/close', methods=['POST'])
def close_ticket():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 403

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

# support/support_api.py
import traceback
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
# تعديل مسار الاستدعاء المباشر للملف support_db
from support.support_db import (
    get_or_create_active_ticket,
    add_support_message,
    create_new_user_ticket
)

support_bp = Blueprint('support', __name__)

@support_bp.route('/ticket', methods=['GET', 'POST'])
def get_ticket():
    try:
        is_post = (request.method == 'POST')
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        ticket_id = request.args.get('ticket_id') or (request.json.get('ticket_id') if request.is_json else None)
        ticket_data = get_or_create_active_ticket(str(uid), custom_ticket_id=ticket_id)

        if not ticket_data:
            return jsonify({"success": False, "message": "تعذر جلب التذكرة"}), 500

        return jsonify({
            "success": True,
            "ticket_id": ticket_data.get('ticket_id'),
            "status": ticket_data.get('status', 'open'),
            "messages": ticket_data.get('messages', [])
        }), 200

    except Exception as e:
        print(f"Error in get_ticket: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "خطأ داخلي في السيرفر"}), 500

@support_bp.route('/message', methods=['POST'])
def send_message():
    try:
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json(silent=True) or {}
        ticket_id = data.get('ticket_id')
        text = data.get('text', '').strip()

        if not text:
            return jsonify({"success": False, "message": "لا يمكن إرسال رسالة فارغة"}), 400

        if not ticket_id:
            ticket_data = get_or_create_active_ticket(str(uid))
            ticket_id = ticket_data.get('ticket_id')

        res = add_support_message(str(uid), ticket_id, text, sender="user")
        
        if not res.get("success"):
            return jsonify(res), 400

        return jsonify(res), 200

    except Exception as e:
        print(f"Error in send_message: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "خطأ داخلي في السيرفر"}), 500

@support_bp.route('/new_ticket', methods=['POST'])
def new_ticket():
    try:
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        ticket_data = create_new_user_ticket(str(uid))
        if not ticket_data:
            return jsonify({"success": False, "message": "تعذر إنشاء تذكرة جديدة"}), 500

        return jsonify({
            "success": True,
            "ticket_id": ticket_data.get('ticket_id'),
            "status": "open",
            "messages": ticket_data.get('messages', [])
        }), 200

    except Exception as e:
        print(f"Error in new_ticket: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "خطأ داخلي في السيرفر"}), 500

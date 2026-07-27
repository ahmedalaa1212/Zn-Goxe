from flask import Blueprint, jsonify, request
from datetime import datetime
from database import db
from google.cloud import firestore
import json, hmac, hashlib, urllib.parse, os

admin_chat_bp = Blueprint('admin_chat', __name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = "5102387551"

def check_admin_auth():
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        hash_val = parsed_data.pop('hash', None)
        if not hash_val: return None
        
        data_check_str = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_str.encode(), hashlib.sha256).hexdigest()
        
        if calc_hash == hash_val:
            user_data = json.loads(parsed_data.get('user', '{}'))
            u_id = str(user_data.get('id'))
            if u_id == str(ADMIN_ID) or (db and db.collection('moderators').document(u_id).get().exists):
                return u_id
        return None
    except:
        return None

# جلب قائمة جميع التذاكر
@admin_chat_bp.route('/tickets', methods=['GET'])
def get_tickets():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 403

    try:
        tickets_ref = db.collection('support_tickets').stream()
        tickets = []
        for doc in tickets_ref:
            t = doc.to_dict()
            tickets.append(t)
            
        tickets.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        return jsonify({"success": True, "tickets": tickets}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# إرسال رد من الأدمن على تذكرة
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
        t_ref = db.collection('support_tickets').document(ticket_id)
        if not t_ref.get().exists:
            return jsonify({"success": False, "message": "التذكرة غير موجودة"}), 404

        new_msg = {
            'sender': 'admin',
            'text': text,
            'timestamp': datetime.utcnow().isoformat()
        }

        t_ref.update({
            'messages': firestore.ArrayUnion([new_msg]),
            'updated_at': datetime.utcnow().isoformat()
        })

        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# إغلاق تذكرة
@admin_chat_bp.route('/close', methods=['POST'])
def close_ticket():
    if not check_admin_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 403

    data = request.get_json() or {}
    ticket_id = data.get('ticket_id')

    if not ticket_id:
        return jsonify({"success": False, "message": "رقم التذكرة مفقود"}), 400

    try:
        t_ref = db.collection('support_tickets').document(ticket_id)
        t_ref.update({
            'status': 'closed',
            'updated_at': datetime.utcnow().isoformat()
        })
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

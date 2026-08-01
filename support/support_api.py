# support/support_api.py
import traceback
import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db
from core.security import get_authenticated_user

support_bp = Blueprint('support', __name__)

# ==========================================
# دالة لتوليد رقم التذكرة خفيفة وسريعة (بدون Transaction مجهدة)
# ==========================================
def generate_fast_ticket_id(uid):
    short_uid = str(uid)[-4:] if uid else "0000"
    timestamp_sec = int(time.time()) % 100000
    return f"TK-{short_uid}-{timestamp_sec}"

# ==========================================
# مسار: جلب تذكرة المستخدم أو إنشاء واحدة جديدة
# ==========================================
@support_bp.route('/ticket', methods=['GET', 'POST'])
def get_or_create_ticket():
    try:
        is_post = (request.method == 'POST')
        success, uid, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        tickets_ref = db.collection('support_tickets')
        
        # قراءة التذاكر النشطة فقط مع حد أقصى (Limit 5) لمنع استنزاف Firestore
        docs = list(tickets_ref.where('user_id', '==', str(uid)).limit(5).stream())
        
        user_tickets = [d.to_dict() for d in docs]
        user_tickets.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)

        latest_ticket = user_tickets[0] if user_tickets else None
        now_iso = datetime.now(timezone.utc).isoformat()

        # إنشاء تذكرة جديدة إذا لم تكن هناك تذكرة سابقة، أو إذا كانت الأخيرة مغلقة
        if not latest_ticket or latest_ticket.get('status') == 'closed':
            
            # جلب معلومات خفيفة عن المستخدم
            user_info = {"telegram_id": str(uid), "first_name": "لاعب"}
            try:
                u_doc = db.collection('users').document(str(uid)).get()
                if u_doc.exists:
                    u_data = u_doc.to_dict() or {}
                    user_info["first_name"] = u_data.get('first_name', u_data.get('name', 'لاعب'))
                    user_info["username"] = u_data.get('username', '')
            except Exception:
                pass

            new_ticket_id = generate_fast_ticket_id(uid)
            new_ticket_data = {
                'ticket_id': new_ticket_id,
                'user_id': str(uid),
                'user_info': user_info,
                'status': 'open',
                'created_at': now_iso,
                'updated_at': now_iso,
                'messages': []
            }
            tickets_ref.document(new_ticket_id).set(new_ticket_data)
            return jsonify({
                "success": True, 
                "ticket_id": new_ticket_id, 
                "status": "open", 
                "messages": []
            }), 200

        return jsonify({
            "success": True,
            "ticket_id": latest_ticket['ticket_id'],
            "status": latest_ticket.get('status', 'open'),
            "messages": latest_ticket.get('messages', [])
        }), 200

    except Exception as e:
        print(f"Support API Error (Get Ticket): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "حدث خطأ في الخادم أثناء جلب التذكرة."}), 500

# ==========================================
# مسار: إرسال رسالة من المستخدم
# ==========================================
@support_bp.route('/message', methods=['POST'])
def send_message():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        req_data = request.get_json() or {}
        
        ticket_id = req_data.get('ticket_id')
        text = req_data.get('text')

        if not ticket_id or not text or not str(text).strip():
            return jsonify({"success": False, "message": "بيانات الرسالة غير مكتملة."}), 400

        ticket_ref = db.collection('support_tickets').document(str(ticket_id))
        ticket_doc = ticket_ref.get()

        if not ticket_doc.exists:
            return jsonify({"success": False, "message": "التذكرة غير موجودة."}), 404
            
        ticket_data = ticket_doc.to_dict() or {}
        
        if ticket_data.get('user_id') != str(uid):
            return jsonify({"success": False, "message": "غير مصرح لك بالإرسال لهذه التذكرة."}), 403

        if ticket_data.get('status') == 'closed':
            return jsonify({"success": False, "message": "تم إغلاق هذه التذكرة ولا يمكن الإرسال بها."}), 400

        new_msg = {
            'sender': 'user',
            'text': str(text).strip(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        ticket_ref.update({
            'messages': firestore.ArrayUnion([new_msg]),
            'updated_at': datetime.now(timezone.utc).isoformat()
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"Support API Error (Send Msg): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "حدث خطأ في الخادم أثناء إرسال الرسالة."}), 500

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
# دالة لتوليد رقم التذكرة الخفيف (بدون Transaction مجهدة)
# ==========================================
def generate_fast_ticket_id(uid):
    short_uid = str(uid)[-4:] if uid else "0000"
    timestamp_sec = int(time.time()) % 100000
    return f"TK-{short_uid}-{timestamp_sec}"

# ==========================================
# مسار: جلب آخر تذكرة للمستخدم
# ==========================================
@support_bp.route('/ticket', methods=['GET'])
def get_ticket():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=False)
        if not success:
            return error_res

        tickets_ref = db.collection('support_tickets')
        
        # قراءة أحدث 5 تذاكر فقط لتجنب استنزاف القراءات
        docs = list(tickets_ref.where('user_id', '==', str(uid)).limit(5).stream())
        user_tickets = [d.to_dict() for d in docs]
        user_tickets.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)

        latest_ticket = user_tickets[0] if user_tickets else None

        # إنشاء تذكرة أولى تلقائياً إذا لم توجد أي تذكرة سابقة
        if not latest_ticket:
            now_iso = datetime.now(timezone.utc).isoformat()
            new_ticket_id = generate_fast_ticket_id(uid)
            welcome_msg = {
                'sender': 'admin',
                'text': f'مرحباً بك في الدعم الفني! كودك المرجعي للمحادثة هو: {new_ticket_id}. اكتب استفسارك وسيجيبك الفريق.',
                'timestamp': now_iso
            }
            new_ticket_data = {
                'ticket_id': new_ticket_id,
                'user_id': str(uid),
                'status': 'open',
                'created_at': now_iso,
                'updated_at': now_iso,
                'messages': [welcome_msg]
            }
            tickets_ref.document(new_ticket_id).set(new_ticket_data)
            return jsonify({
                "success": True,
                "ticket_id": new_ticket_id,
                "status": "open",
                "messages": [welcome_msg]
            }), 200

        return jsonify({
            "success": True,
            "ticket_id": latest_ticket.get('ticket_id'),
            "status": latest_ticket.get('status', 'open'),
            "messages": latest_ticket.get('messages', [])
        }), 200

    except Exception as e:
        print(f"Support API Error (Get Ticket): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "حدث خطأ في الخادم أثناء جلب التذكرة."}), 500

# ==========================================
# مسار: بدء محادثة / تذكرة جديدة فوراً
# ==========================================
@support_bp.route('/new_ticket', methods=['POST'])
def create_new_ticket():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        tickets_ref = db.collection('support_tickets')
        now_iso = datetime.now(timezone.utc).isoformat()
        new_ticket_id = generate_fast_ticket_id(uid)
        
        welcome_msg = {
            'sender': 'admin',
            'text': f'تم فتح تذكرة محادثة جديدة برقم مرجعي: {new_ticket_id}. تفضل بكتابة استفسارك.',
            'timestamp': now_iso
        }

        new_ticket_data = {
            'ticket_id': new_ticket_id,
            'user_id': str(uid),
            'status': 'open',
            'created_at': now_iso,
            'updated_at': now_iso,
            'messages': [welcome_msg]
        }
        tickets_ref.document(new_ticket_id).set(new_ticket_data)

        return jsonify({
            "success": True,
            "ticket_id": new_ticket_id,
            "status": "open",
            "messages": [welcome_msg]
        }), 200

    except Exception as e:
        print(f"Support API Error (New Ticket): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "حدث خطأ أثناء إنشاء تذكرة جديدة."}), 500

# ==========================================
# مسار: إرسال رسالة داخل التذكرة
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
            # في حال عدم وجود التذكرة بالخادم، يتم إنشاؤها فوراً دون تعطيل المستخدم
            now_iso = datetime.now(timezone.utc).isoformat()
            new_msg = {
                'sender': 'user',
                'text': str(text).strip(),
                'timestamp': now_iso
            }
            ticket_ref.set({
                'ticket_id': str(ticket_id),
                'user_id': str(uid),
                'status': 'open',
                'created_at': now_iso,
                'updated_at': now_iso,
                'messages': [new_msg]
            })
            return jsonify({"success": True, "message": "تم إرسال الرسالة وإنشاء التذكرة بنجاح."}), 200

        ticket_data = ticket_doc.to_dict() or {}

        if ticket_data.get('user_id') != str(uid):
            return jsonify({"success": False, "message": "غير مصرح لك بالإرسال لهذه التذكرة."}), 403

        if ticket_data.get('status') == 'closed':
            return jsonify({"success": False, "message": "تم إنهاء هذه المحادثة من قبل الدعم الفني."}), 400

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

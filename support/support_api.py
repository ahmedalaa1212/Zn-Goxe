# support/support_api.py
import traceback
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db
from core.security import get_authenticated_user

support_bp = Blueprint('support', __name__)

# ==========================================
# دالة لتوليد رقم التذكرة المتسلسل الآمن
# ==========================================
def generate_next_ticket_id():
    tracker_ref = db.collection('system').document('ticket_tracker')
    
    @firestore.transactional
    def get_and_increment_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            transaction.set(ref, {'last_id': 1})
            new_id = 1
        else:
            data = snapshot.to_dict() or {}
            new_id = data.get('last_id', 0) + 1
            transaction.update(ref, {'last_id': new_id})
        return new_id

    transaction = db.transaction()
    new_id = get_and_increment_transaction(transaction, tracker_ref)
    return f"{new_id:010d}"

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

        # جلب بيانات المستخدم لإرفاقها مع التذكرة
        user_doc = db.collection('users').document(uid).get()
        user_info = {
            "telegram_id": uid,
            "first_name": "غير محدد",
            "username": "لا يوجد",
            "joined_at": "غير معروف",
            "storage_level": 1,
            "upgrades": {}
        }
        
        if user_doc.exists:
            u_data = user_doc.to_dict() or {}
            user_info["first_name"] = u_data.get('first_name', u_data.get('name', 'غير محدد'))
            user_info["username"] = u_data.get('username', 'لا يوجد')
            user_info["joined_at"] = u_data.get('created_at', u_data.get('joined_at', 'غير محدد'))
            user_info["storage_level"] = u_data.get('storage_level', 1)
            user_info["upgrades"] = u_data.get('upgrades', {})

        tickets_ref = db.collection('support_tickets')
        docs = list(tickets_ref.where('user_id', '==', uid).stream())
        
        user_tickets = [d.to_dict() for d in docs]
        user_tickets.sort(key=lambda x: x.get('ticket_id', ''), reverse=True)

        latest_ticket = user_tickets[0] if user_tickets else None
        now_iso = datetime.now(timezone.utc).isoformat()

        # إنشاء تذكرة جديدة إذا لم تكن هناك تذكرة سابقة، أو إذا كانت التذكرة الأخيرة مغلقة
        if not latest_ticket or latest_ticket.get('status') == 'closed':
            new_ticket_id = generate_next_ticket_id()
            new_ticket_data = {
                'ticket_id': new_ticket_id,
                'user_id': uid,
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
        
        # تحديث بيانات المستخدم المرفقة في التذكرة النشطة
        tickets_ref.document(latest_ticket['ticket_id']).update({'user_info': user_info})

        return jsonify({
            "success": True,
            "ticket_id": latest_ticket['ticket_id'],
            "status": latest_ticket['status'],
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
        
        if ticket_data.get('user_id') != uid:
            return jsonify({"success": False, "message": "غير مصرح لك بالإرسال لهذه التذكرة."}), 403

        if ticket_data.get('status') == 'closed':
            return jsonify({"success": False, "message": "تم إغلاق هذه التذكرة ولا يمكن الإرسال بها."}), 400

        new_msg = {
            'sender': 'user',
            'text': str(text).strip(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # إضافة الرسالة ذرياً لضمان عدم الضياع
        ticket_ref.update({
            'messages': firestore.ArrayUnion([new_msg]),
            'updated_at': datetime.now(timezone.utc).isoformat()
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"Support API Error (Send Msg): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "حدث خطأ في الخادم أثناء إرسال الرسالة."}), 500

from flask import Blueprint, jsonify, request
import traceback
from datetime import datetime
from core.security import validate_telegram_data
from database import db
from google.cloud import firestore

support_bp = Blueprint('support', __name__)

# ==========================================
# دالة لتوليد رقم التذكرة المتسلسل (0000000001)
# ==========================================
def generate_next_ticket_id():
    tracker_ref = db.collection('system').document('ticket_tracker')
    
    @firestore.transactional
    def get_and_increment_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            transaction.set(ref, {'last_id': 0})
            new_id = 1
        else:
            new_id = snapshot.get('last_id', 0) + 1
            transaction.update(ref, {'last_id': new_id})
        return new_id

    transaction = db.transaction()
    new_id = get_and_increment_transaction(transaction, tracker_ref)
    return f"{new_id:010d}"

# ==========================================
# مسار: جلب تذكرة المستخدم أو إنشاء واحدة جديدة مع البيانات
# ==========================================
@support_bp.route('/ticket', methods=['GET'])
def get_or_create_ticket():
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        return jsonify({"success": False, "message": "Missing auth"}), 401

    auth_result = validate_telegram_data(init_data)
    if not auth_result or 'id' not in auth_result:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    user_id = str(auth_result['id'])

    try:
        # 🟢 1. جلب كافة بيانات المستخدم الحالية لتضمينها في التذكرة للأدمن
        user_doc = db.collection('users').document(user_id).get()
        user_info = {
            "telegram_id": user_id,
            "first_name": auth_result.get('first_name', 'غير محدد'),
            "username": auth_result.get('username', 'لا يوجد'),
            "joined_at": "غير معروف",
            "storage_level": 1,
            "upgrades": {}
        }
        
        if user_doc.exists:
            u_data = user_doc.to_dict()
            user_info["first_name"] = u_data.get('first_name', user_info["first_name"])
            user_info["username"] = u_data.get('username', user_info["username"])
            user_info["joined_at"] = u_data.get('created_at', u_data.get('joined_at', 'غير محدد'))
            user_info["storage_level"] = u_data.get('storage_level', 1)
            user_info["upgrades"] = u_data.get('upgrades', {})

        # 🟢 2. جلب التذاكر بدون الحاجة لـ Composite Index وتفادي التعليق
        tickets_ref = db.collection('support_tickets')
        docs = list(tickets_ref.where('user_id', '==', user_id).stream())
        
        user_tickets = [d.to_dict() for d in docs]
        # فرز التذاكر من الأحدث للأقدم داخل بايثون
        user_tickets.sort(key=lambda x: x.get('ticket_id', ''), reverse=True)

        latest_ticket = user_tickets[0] if user_tickets else None

        # إذا كانت لا توجد تذكرة أو كانت آخر تذكرة مغلقة -> إنشاء تذكرة جديدة
        if not latest_ticket or latest_ticket.get('status') == 'closed':
            new_ticket_id = generate_next_ticket_id()
            new_ticket_data = {
                'ticket_id': new_ticket_id,
                'user_id': user_id,
                'user_info': user_info,  # ✅ بيانات المستخدم الشاملة تم حفظها مع التذكرة
                'status': 'open',
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                'messages': []
            }
            tickets_ref.document(new_ticket_id).set(new_ticket_data)
            return jsonify({
                "success": True, 
                "ticket_id": new_ticket_id, 
                "status": "open", 
                "messages": []
            }), 200
        
        # إن كانت التذكرة مفتوحة، نقوم بتحديث بيانات المستخدم فيها لضمان دقتها
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
        return jsonify({"success": False, "message": str(e)}), 500

# ==========================================
# مسار: إرسال رسالة من المستخدم
# ==========================================
@support_bp.route('/message', methods=['POST'])
def send_message():
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        return jsonify({"success": False, "message": "Missing auth"}), 401

    auth_result = validate_telegram_data(init_data)
    if not auth_result or 'id' not in auth_result:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    user_id = str(auth_result['id'])
    req_data = request.get_json() or {}
    
    ticket_id = req_data.get('ticket_id')
    text = req_data.get('text')

    if not ticket_id or not text:
        return jsonify({"success": False, "message": "Missing data"}), 400

    try:
        ticket_ref = db.collection('support_tickets').document(ticket_id)
        ticket_doc = ticket_ref.get()

        if not ticket_doc.exists:
            return jsonify({"success": False, "message": "Ticket not found"}), 404
            
        ticket_data = ticket_doc.to_dict()
        
        if ticket_data.get('user_id') != user_id:
            return jsonify({"success": False, "message": "Unauthorized ticket access"}), 403

        if ticket_data.get('status') == 'closed':
            return jsonify({"success": False, "message": "Ticket is closed"}), 400

        new_msg = {
            'sender': 'user',
            'text': text,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        ticket_ref.update({
            'messages': firestore.ArrayUnion([new_msg]),
            'updated_at': datetime.utcnow().isoformat()
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"Support API Error (Send Msg): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

from flask import Blueprint, jsonify, request
import traceback
from datetime import datetime
from core.security import validate_telegram_data
from database import db
from google.cloud import firestore

support_bp = Blueprint('support', __name__)

# ==========================================
# دالة لتوليد رقم التذكرة المتسلسل (مثال: 0000000001)
# ==========================================
def generate_next_ticket_id():
    # نستخدم مستند في الفايربيس لتتبع آخر رقم تم إصداره
    tracker_ref = db.collection('system').document('ticket_tracker')
    
    @firestore.transactional
    def get_and_increment_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            transaction.set(ref, {'last_id': 0})
            new_id = 1
        else:
            new_id = snapshot.get('last_id') + 1
            transaction.update(ref, {'last_id': new_id})
        return new_id

    transaction = db.transaction()
    new_id = get_and_increment_transaction(transaction, tracker_ref)
    
    # تنسيق الرقم ليكون 10 خانات (0000000001)
    return f"{new_id:010d}"

# ==========================================
# مسار: جلب تذكرة المستخدم أو إنشاء واحدة جديدة
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
        # نبحث عن أحدث تذكرة لهذا المستخدم
        tickets_ref = db.collection('support_tickets')
        query = tickets_ref.where('user_id', '==', user_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(1)
        results = query.stream()
        
        ticket_doc = None
        ticket_data = None
        
        for doc in results:
            ticket_doc = doc
            ticket_data = doc.to_dict()
            break

        # إذا لم تكن هناك تذكرة، أو كانت آخر تذكرة 'مغلقة'، ننشئ واحدة جديدة
        if not ticket_data or ticket_data.get('status') == 'closed':
            new_ticket_id = generate_next_ticket_id()
            new_ticket_data = {
                'ticket_id': new_ticket_id,
                'user_id': user_id,
                'status': 'open', # open, closed
                'created_at': firestore.SERVER_TIMESTAMP,
                'messages': [] # مصفوفة لتخزين الرسائل {sender: 'user'/'admin', text: '...'}
            }
            # نحفظ التذكرة مستخدمين الرقم المرجعي كاسم للمستند لسهولة البحث للأدمن لاحقاً
            tickets_ref.document(new_ticket_id).set(new_ticket_data)
            return jsonify({
                "success": True, 
                "ticket_id": new_ticket_id, 
                "status": "open", 
                "messages": []
            }), 200
        
        # إذا كانت هناك تذكرة مفتوحة، نعيد بياناتها
        return jsonify({
            "success": True,
            "ticket_id": ticket_data['ticket_id'],
            "status": ticket_data['status'],
            "messages": ticket_data.get('messages', [])
        }), 200

    except Exception as e:
        print(f"Support API Error (Get Ticket): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Server error"}), 500

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
    req_data = request.get_json()
    
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
        
        # التأكد أن التذكرة تخص هذا المستخدم
        if ticket_data.get('user_id') != user_id:
            return jsonify({"success": False, "message": "Unauthorized ticket access"}), 403

        # التأكد أن التذكرة ما زالت مفتوحة
        if ticket_data.get('status') == 'closed':
            return jsonify({"success": False, "message": "Ticket is closed"}), 400

        # إضافة الرسالة لمصفوفة الرسائل
        new_msg = {
            'sender': 'user',
            'text': text,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # تحديث المصفوفة في الفايربيس
        ticket_ref.update({
            'messages': firestore.ArrayUnion([new_msg]),
            'updated_at': firestore.SERVER_TIMESTAMP # لتسهيل فرز التذاكر للأدمن
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"Support API Error (Send Msg): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Server error"}), 500


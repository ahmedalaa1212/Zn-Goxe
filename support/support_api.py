import traceback
import time
import json
import urllib.parse
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from google.cloud import firestore

import database
from core.security import get_authenticated_user

support_bp = Blueprint('support', __name__)

def get_db():
    """ضمان الحصول على قاعدة البيانات Firestore بدون أن تكون None"""
    if database.db is None:
        return database.initialize_firebase()
    return database.db

def generate_fast_ticket_id(uid):
    """توليد رقم تذكرة مرجعي سريع فريد"""
    short_uid = str(uid)[-4:] if uid else "0000"
    timestamp_sec = int(time.time()) % 100000
    return f"TK-{short_uid}-{timestamp_sec}"

def get_telegram_user_info(req, uid=None, auth_user_info=None):
    """استخراج اسم المستخدم ومعرفه من التليجرام لربطه باللوحة"""
    if auth_user_info and isinstance(auth_user_info, dict):
        return {
            'id': str(auth_user_info.get('id', uid or '')),
            'first_name': auth_user_info.get('first_name', 'مستخدم'),
            'username': auth_user_info.get('username', 'بدون')
        }
    try:
        init_data = req.headers.get('X-Telegram-Init-Data', '')
        if not init_data:
            auth_header = req.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                init_data = auth_header[7:]
                
        if init_data:
            parsed_data = dict(urllib.parse.parse_qsl(init_data))
            user_raw = parsed_data.get('user')
            if user_raw:
                u = json.loads(user_raw)
                return {
                    'id': str(u.get('id', uid or '')),
                    'first_name': u.get('first_name', 'مستخدم'),
                    'username': u.get('username', 'بدون')
                }
    except Exception as e:
        print(f"⚠️ User Info Extract Warning: {e}")
    return {'id': str(uid or ''), 'first_name': 'مستخدم', 'username': 'بدون'}

# نص الترحيب الرسمي والتنبيه الانضباطي
WELCOME_NOTICE_TEXT = (
    "مرحباً بك في مركز الدعم الفني! 🎧\n"
    "كودك المرجعي للمحادثة: {ticket_id}\n\n"
    "⚠️ تنبيه هام لجميع المستخدمين:\n"
    "يرجى التكرم بالالتزام بآداب الحوار والتعامل اللائق مع فريق الدعم. "
    "المحادثات مخصصة فقط للاستفسارات الفنية والمشكلات. أي إساءة لفظية أو تجاوز قد يعرض حسابك للحظر النهائي والمنع من الخدمة فوراً.\n\n"
    "تفضل بكتابة استفسارك وسيقوم الفريق بالرد عليك في أقرب وقت."
)

# ==========================================
# مسار: جلب أحدث تذكرة للمستخدم (معدّل للحد من القراءات)
# ==========================================
@support_bp.route('/ticket', methods=['GET'])
def get_ticket():
    try:
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=False)
        if not success:
            return error_res

        db_conn = get_db()
        tickets_ref = db_conn.collection('support_tickets')
        
        requested_ticket_id = request.args.get('ticket_id')

        # إذا أرسل العميل رقم التذكرة المتوفر لديه، يتم الجلب المباشر بالوثيقة (قراءة واحدة 1 Read)
        if requested_ticket_id:
            doc = tickets_ref.document(str(requested_ticket_id)).get()
            if doc.exists:
                ticket_data = doc.to_dict() or {}
                if ticket_data.get('user_id') == str(uid):
                    return jsonify({
                        "success": True,
                        "ticket_id": ticket_data.get('ticket_id'),
                        "status": ticket_data.get('status', 'open'),
                        "messages": ticket_data.get('messages', [])
                    }), 200

        # في حال عدم وجود رقم تذكرة مسبق أو تعذر الوصول إليها، يجلب أحدث تذكرة للمستخدم فقط
        docs = list(tickets_ref.where('user_id', '==', str(uid)).limit(3).stream())
        user_tickets = [d.to_dict() for d in docs if d.exists]
        user_tickets.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)

        latest_ticket = user_tickets[0] if user_tickets else None

        if not latest_ticket:
            now_iso = datetime.now(timezone.utc).isoformat()
            new_ticket_id = generate_fast_ticket_id(uid)
            u_info = get_telegram_user_info(request, uid=uid, auth_user_info=user_info)

            welcome_msg = {
                'sender': 'admin',
                'text': WELCOME_NOTICE_TEXT.format(ticket_id=new_ticket_id),
                'timestamp': now_iso
            }
            new_ticket_data = {
                'ticket_id': new_ticket_id,
                'user_id': str(uid),
                'user_info': u_info,
                'status': 'open',
                'has_unread_admin': False,
                'last_sender': 'admin',
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
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        db_conn = get_db()
        tickets_ref = db_conn.collection('support_tickets')
        now_iso = datetime.now(timezone.utc).isoformat()
        new_ticket_id = generate_fast_ticket_id(uid)
        u_info = get_telegram_user_info(request, uid=uid, auth_user_info=user_info)
        
        welcome_msg = {
            'sender': 'admin',
            'text': WELCOME_NOTICE_TEXT.format(ticket_id=new_ticket_id),
            'timestamp': now_iso
        }

        new_ticket_data = {
            'ticket_id': new_ticket_id,
            'user_id': str(uid),
            'user_info': u_info,
            'status': 'open',
            'has_unread_admin': False,
            'last_sender': 'admin',
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
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        req_data = request.get_json() or {}
        ticket_id = req_data.get('ticket_id')
        text = req_data.get('text')

        if not ticket_id or not text or not str(text).strip():
            return jsonify({"success": False, "message": "بيانات الرسالة غير مكتملة."}), 400

        db_conn = get_db()
        ticket_ref = db_conn.collection('support_tickets').document(str(ticket_id))
        ticket_doc = ticket_ref.get()

        now_iso = datetime.now(timezone.utc).isoformat()
        u_info = get_telegram_user_info(request, uid=uid, auth_user_info=user_info)

        new_msg = {
            'sender': 'user',
            'text': str(text).strip(),
            'timestamp': now_iso
        }

        if not ticket_doc.exists:
            ticket_ref.set({
                'ticket_id': str(ticket_id),
                'user_id': str(uid),
                'user_info': u_info,
                'status': 'open',
                'has_unread_admin': True,
                'last_sender': 'user',
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

        ticket_ref.update({
            'messages': firestore.ArrayUnion([new_msg]),
            'updated_at': now_iso,
            'has_unread_admin': True,
            'last_sender': 'user',
            'user_info': u_info
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"Support API Error (Send Msg): {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "حدث خطأ في الخادم أثناء إرسال الرسالة."}), 500

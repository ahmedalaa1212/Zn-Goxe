# settings/settings_api.py
import traceback
from flask import Blueprint, jsonify, request
from database import db
from core.security import get_authenticated_user
import time

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/stats', methods=['GET', 'POST'])
def get_settings_stats():
    try:
        is_post = (request.method == 'POST')
        success, uid, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({
                "success": True,
                "farm_levels_count": 0,
                "storage_levels_count": 0,
                "balance": 0
            }), 200

        user_data = user_doc.to_dict() or {}
        
        farm_levels_count = 0
        upgrades_map = user_data.get('upgrades', {})
        if isinstance(upgrades_map, dict):
            for i in range(1, 10):
                lvl_val = upgrades_map.get(f'lvl{i}')
                if lvl_val is not None:
                    try:
                        farm_levels_count += int(lvl_val)
                    except (ValueError, TypeError):
                        pass

        storage_levels_count = 0
        storage_val = user_data.get('storage_level')
        if storage_val is not None:
            try:
                storage_levels_count = int(storage_val)
            except (ValueError, TypeError):
                pass

        balance = user_data.get('balance', 0)

        return jsonify({
            "success": True,
            "farm_levels_count": farm_levels_count,
            "storage_levels_count": storage_levels_count,
            "balance": balance
        }), 200

    except Exception as e:
        print(f"Error in get_settings_stats: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500


# ==========================================
# 🎧 مسارات الدعم الفني وتذاكر الشات (مصححة وآمنة)
# ==========================================

@settings_bp.route('/support/ticket', methods=['GET'])
def get_support_ticket():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=False)
        if not success:
            return error_res

        # البحث عن تذكرة مفتوحة للمستخدم
        tickets_ref = db.collection('support_tickets')
        query = tickets_ref.where('user_id', '==', str(uid)).limit(1)
        docs = list(query.stream())

        ticket_id = None
        ticket_data = {}

        if docs:
            ticket_doc = docs[0]
            ticket_id = ticket_doc.id
            ticket_data = ticket_doc.to_dict()
        else:
            # إنشاؤها تلقائياً إذا لم تكن موجودة لمنع الأخطاء
            new_ticket_ref = tickets_ref.document()
            ticket_id = new_ticket_ref.id
            ticket_data = {
                "user_id": str(uid),
                "status": "open",
                "created_at": time.time(),
                "messages": []
            }
            new_ticket_ref.set(ticket_data)

        return jsonify({
            "success": True,
            "ticket_id": ticket_id,
            "status": ticket_data.get('status', 'open'),
            "messages": ticket_data.get('messages', [])
        }), 200

    except Exception as e:
        print(f"Error in get_support_ticket: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "حدث خطأ في الخادم أثناء جلب التذكرة"}), 500


@settings_bp.route('/support/message', methods=['POST'])
def send_support_message():
    try:
        success, uid, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json() or {}
        ticket_id = data.get('ticket_id')
        text = data.get('text', '').strip()

        if not ticket_id or not text:
            return jsonify({"success": False, "message": "بيانات غير مكتملة"}), 400

        ticket_ref = db.collection('support_tickets').document(str(ticket_id))
        ticket_doc = ticket_ref.get()

        if not ticket_doc.exists:
            return jsonify({"success": False, "message": "التذكرة غير موجودة"}), 404

        ticket_data = ticket_doc.to_dict()
        if ticket_data.get('status') == 'closed':
            return jsonify({"success": False, "message": "تم إغلاق هذه التذكرة من الدعم الفني."}), 400

        new_msg = {
            "sender": "user",
            "text": text,
            "timestamp": time.time()
        }

        messages = ticket_data.get('messages', [])
        messages.append(new_msg)

        ticket_ref.update({
            "messages": messages,
            "updated_at": time.time()
        })

        return jsonify({"success": True, "messages": messages}), 200

    except Exception as e:
        print(f"Error in send_support_message: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "فشل إرسال الرسالة"}), 500

from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user  # دالة التحقق من صحة بيانات تليجرام
from database import db  # الاتصال بقاعدة بيانات Firebase

friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/list', methods=['POST'])
def get_friends_list():
    """جلب سجل الأصدقاء الذين قاموا بالدخول عبر رابط إحالة اللاعب"""
    try:
        data = request.get_json()
        init_data = data.get('initData')
        
        # 1. التحقق من الأمان
        user_info = get_authenticated_user(init_data)
        if not user_info:
            return jsonify({"success": False, "error": "غير مصرح لك (Unauthorized)"}), 401
            
        user_id = str(user_info.get('id'))
        
        # 2. الاستعلام من Firebase عن الأصدقاء
        friends_query = db.collection('users').where('referred_by', '==', user_id).stream()
        
        friends_list = []
        for doc in friends_query:
            f_data = doc.to_dict()
            friends_list.append({
                "name": f_data.get('first_name', 'صديق'),
                "upgrades_count": f_data.get('upgrades_count', 0),
                "generated": f_data.get('ref_generated_amount', 0) # كمية العملات التي ولدها هذا الصديق لك
            })
            
        return jsonify({"success": True, "friends": friends_list}), 200

    except Exception as e:
        print(f"Error in friends/list: {e}")
        return jsonify({"success": False, "error": "حدث خطأ في الخادم"}), 500


@friends_bp.route('/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    """سحب أرباح الأصدقاء المعلقة إلى الرصيد الأساسي مع خصم 1.5% رسوم"""
    try:
        data = request.get_json()
        init_data = data.get('initData')
        
        # 1. التحقق من الأمان
        user_info = get_authenticated_user(init_data)
        if not user_info:
            return jsonify({"success": False, "error": "غير مصرح لك"}), 401
            
        user_id = str(user_info.get('id'))
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "حساب المستخدم غير موجود"}), 404
            
        user_data = user_doc.to_dict()
        pending_earnings = float(user_data.get('pending_ref_earnings', 0))
        current_balance = float(user_data.get('balance', 0))
        
        # 2. التحقق من وجود رصيد قابل للسحب
        if pending_earnings <= 0:
            return jsonify({"success": False, "error": "لا توجد أرباح معلقة للسحب"}), 400
            
        # 3. حساب الرسوم (1.5%)
        fee_percentage = 0.015
        net_amount = pending_earnings - (pending_earnings * fee_percentage)
        
        new_balance = current_balance + net_amount
        
        # 4. تحديث قاعدة البيانات
        user_ref.update({
            'balance': new_balance,
            'pending_ref_earnings': 0
        })
        
        return jsonify({
            "success": True, 
            "new_balance": new_balance,
            "net_amount": net_amount
        }), 200

    except Exception as e:
        print(f"Error in claim_ref_earnings: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية السحب"}), 500


@friends_bp.route('/claim_ref_task', methods=['POST'])
def claim_ref_task():
    """استلام مكافآت الإنجازات بناءً على عدد الأصدقاء"""
    try:
        data = request.get_json()
        init_data = data.get('initData')
        task_id = int(data.get('taskId'))
        expected_reward = float(data.get('reward'))
        req_friends = int(data.get('reqFriends'))
        
        # 1. التحقق من الأمان
        user_info = get_authenticated_user(init_data)
        if not user_info:
            return jsonify({"success": False, "error": "غير مصرح لك"}), 401
            
        user_id = str(user_info.get('id'))
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "حساب المستخدم غير موجود"}), 404
            
        user_data = user_doc.to_dict()
        invited_count = int(user_data.get('invited_friends_count', 0))
        claimed_tasks = user_data.get('claimed_ref_tasks', [])
        current_balance = float(user_data.get('balance', 0))
        
        # 2. التحقق من أحقية الاستلام (Logic Checks)
        if invited_count < req_friends:
            return jsonify({"success": False, "error": "لم تصل للعدد المطلوب من الأصدقاء بعد"}), 400
            
        if task_id in claimed_tasks:
            return jsonify({"success": False, "error": "تم استلام هذه المكافأة مسبقاً"}), 400
            
        # 3. تحديث قاعدة البيانات (إضافة الرصيد وتوثيق المهمة)
        new_balance = current_balance + expected_reward
        claimed_tasks.append(task_id)
        
        user_ref.update({
            'balance': new_balance,
            'claimed_ref_tasks': claimed_tasks
        })
        
        return jsonify({
            "success": True, 
            "new_balance": new_balance
        }), 200

    except Exception as e:
        print(f"Error in claim_ref_task: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500

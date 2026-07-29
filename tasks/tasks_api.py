import os
import json
import uuid
import datetime
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from database import db as firestore_db
from firebase_admin import firestore

tasks_bp = Blueprint('tasks', __name__)

def is_task_completed_by_user(task, user_completed_data):
    """
    فحص إكمال المهمة:
    - مهام 'موقع': تتجدد يومياً وتعتبر مكتملة فقط إذا أُنجزت اليوم بنفس التاريخ (UTC YYYY-MM-DD).
    - باقي المنصات (يوتيوب، تيليجرام، انستغرام، X...): مكتملة بصفة دائمة بمجرد إنجازها مرّة واحدة.
    """
    task_id = str(task.get('id', '')).strip()
    platform = str(task.get('platform', '')).strip()
    
    if not user_completed_data or not task_id:
        return False

    today_str = datetime.datetime.utcnow().strftime('%Y-%m-%d')

    # 1. إذا كان التخزين بالشكل القديم (قائمة List)
    if isinstance(user_completed_data, list):
        if task_id not in user_completed_data:
            return False
        if platform == 'موقع':
            return False
        return True

    # 2. إذا كان التخزين بالشكل الجديد (Dictionary)
    if isinstance(user_completed_data, dict):
        if task_id not in user_completed_data:
            return False

        record = user_completed_data[task_id]
        
        if platform == 'موقع':
            if isinstance(record, str):
                return record == today_str
            elif isinstance(record, dict):
                task_date = record.get('date')
                if task_date:
                    return task_date == today_str
                ts = record.get('timestamp')
                if ts:
                    task_dt = datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                    return task_dt == today_str
            elif isinstance(record, (int, float)):
                task_dt = datetime.datetime.utcfromtimestamp(record).strftime('%Y-%m-%d')
                return task_dt == today_str
            return False
        else:
            return True

    return False

@tasks_bp.route('/get_campaigns', methods=['GET'])
def get_campaigns():
    is_auth, telegram_id, err_response = get_authenticated_user(request, is_post=False)
    if not is_auth:
        telegram_id = request.args.get('telegramId', '5102387551').strip()

    telegram_id_str = str(telegram_id).strip()

    ad_balance = 0.0
    balance = 0.0
    try:
        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_doc = user_ref.get()
        if user_doc.exists:
            u_data = user_doc.to_dict() or {}
            ad_balance = float(u_data.get('ad_balance', 0.0))
            balance = float(u_data.get('balance', 0.0))
    except Exception as e:
        print(f"Error fetching user data in get_campaigns: {e}")

    campaigns = []
    user_completed_data = {}

    try:
        # جلب المهام المكتملة للمستخدم مباشرة من Firestore السحابية
        completed_ref = firestore_db.collection('completed_tasks').document(telegram_id_str).get()
        if completed_ref.exists:
            user_completed_data = completed_ref.to_dict() or {}

        # جلب جميع الحملات من Firestore السحابية
        docs = firestore_db.collection('campaigns').stream()
        for doc in docs:
            c_data = doc.to_dict() or {}
            c_data['id'] = doc.id
            campaigns.append(c_data)
    except Exception as e:
        print(f"Error fetching campaigns from Firestore: {e}")

    result_campaigns = []
    for c in campaigns:
        # إخفاء الحملات المنتهية للمستخدمين الآخرين وإظهارها لصاحب الحملة
        if c.get('users_completed', 0) >= c.get('users_needed', 1) and str(c.get('creator_id')).strip() != telegram_id_str:
            continue
            
        c_copy = dict(c)
        c_copy['is_completed'] = is_task_completed_by_user(c, user_completed_data)
        result_campaigns.append(c_copy)

    return jsonify({
        "success": True,
        "user_id": telegram_id_str,
        "ad_balance": ad_balance,
        "balance": balance,
        "campaigns": result_campaigns
    }), 200

@tasks_bp.route('/create_campaign', methods=['POST'])
def create_campaign():
    is_auth, telegram_id, err_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_response

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    platform = req.get('platform')
    url = req.get('url')
    description = req.get('description')
    reward = req.get('reward')
    users_needed = req.get('users_needed')

    if not all([platform, url, description, reward, users_needed]):
        return jsonify({"success": False, "error": "جميع البيانات مطلوبة"}), 400

    try:
        reward = float(reward)
        users_needed = int(users_needed)
        if reward <= 0 or users_needed <= 0:
            raise ValueError()
    except ValueError:
        return jsonify({"success": False, "error": "قيم الكلفة والأعضاء غير صحيحة"}), 400

    total_cost = reward * users_needed

    try:
        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404

        user_data = user_doc.to_dict() or {}
        current_ad_balance = float(user_data.get('ad_balance', 0.0))

        if current_ad_balance < total_cost:
            return jsonify({"success": False, "error": f"رصيدك الإعلاني غير كافٍ. المطلوب: {total_cost} AdZN"}), 400

        # خصم التكلفة من رصيد الإعلانات
        user_ref.set({
            'ad_balance': firestore.Increment(-total_cost)
        }, merge=True)

        camp_id = f"camp_{uuid.uuid4().hex[:10]}"
        new_campaign = {
            "id": camp_id,
            "creator_id": telegram_id_str,
            "platform": platform,
            "url": url,
            "description": description,
            "reward": reward,
            "users_needed": users_needed,
            "users_completed": 0,
            "created_at": datetime.datetime.utcnow().isoformat()
        }

        # حفظ الحملة في قاعدة بيانات Firestore السحابية الدائمة
        firestore_db.collection('campaigns').document(camp_id).set(new_campaign)

        return jsonify({
            "success": True, 
            "campaign": new_campaign,
            "new_ad_balance": current_ad_balance - total_cost
        }), 200

    except Exception as e:
        print(f"Error creating campaign: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء حفظ الحملة"}), 500

@tasks_bp.route('/complete_task', methods=['POST'])
def complete_task():
    is_auth, telegram_id, err_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_response

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    task_id = req.get('taskId')

    if not task_id:
        return jsonify({"success": False, "error": "رقم المهمة مفقود"}), 400

    try:
        camp_ref = firestore_db.collection('campaigns').document(task_id)
        camp_doc = camp_ref.get()

        if not camp_doc.exists:
            return jsonify({"success": False, "error": "المهمة غير موجودة أو انتهت"}), 404

        target_campaign = camp_doc.to_dict() or {}
        target_campaign['id'] = camp_doc.id

        if str(target_campaign.get('creator_id')).strip() == telegram_id_str:
            return jsonify({"success": False, "error": "لا يمكنك تنفيذ حملتك الخاصة"}), 400

        # منع التنافس الزائد وإكمال مهام مكتملة بالفعل
        if target_campaign.get('users_completed', 0) >= target_campaign.get('users_needed', 1):
            return jsonify({"success": False, "error": "هذه المهمة مكتملة بالكامل واستوفت عدد الأعضاء المطلوب!"}), 400

        # جلب المهام المكتملة للمستخدم من Firestore
        completed_ref = firestore_db.collection('completed_tasks').document(telegram_id_str)
        completed_doc = completed_ref.get()
        user_completed_map = completed_doc.to_dict() if completed_doc.exists else {}

        if is_task_completed_by_user(target_campaign, user_completed_map):
            if target_campaign.get('platform') == 'موقع':
                return jsonify({"success": False, "error": "لقد قمت بزيارة هذا الموقع اليوم، يمكنك زيارته غداً مجدداً!"}), 400
            else:
                return jsonify({"success": False, "error": "لقد قمت بإكمال هذه المهمة مسبقاً"}), 400

        reward_amount = float(target_campaign['reward'])

        # إضافة المكافأة لرصيد المستخدم في فايربيس
        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_ref.set({
            'balance': firestore.Increment(reward_amount)
        }, merge=True)

        now_utc = datetime.datetime.utcnow()
        task_record = {
            "date": now_utc.strftime('%Y-%m-%d'),
            "timestamp": now_utc.timestamp()
        }

        # تحديث سجل المهام المكتملة للمستخدم في فايربيس
        completed_ref.set({
            task_id: task_record
        }, merge=True)

        # زيادة عدد المكتملين للمهمة في فايربيس
        camp_ref.set({
            'users_completed': firestore.Increment(1)
        }, merge=True)

        return jsonify({
            "success": True, 
            "reward": reward_amount,
            "message": "تم إكمال المهمة وإضافة المكافأة"
        }), 200

    except Exception as e:
        print(f"Error completing task: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إكمال المهمة"}), 500

@tasks_bp.route('/cancel_campaign', methods=['POST'])
def cancel_campaign():
    is_auth, telegram_id, err_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_response

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    campaign_id = req.get('campaignId')

    try:
        camp_ref = firestore_db.collection('campaigns').document(campaign_id)
        camp_doc = camp_ref.get()

        if not camp_doc.exists:
            return jsonify({"success": False, "error": "الحملة غير موجودة"}), 404

        target_campaign = camp_doc.to_dict() or {}

        if str(target_campaign.get('creator_id')).strip() != telegram_id_str:
            return jsonify({"success": False, "error": "غير مصرح لك بإلغاء هذه الحملة"}), 403

        comp = target_campaign.get('users_completed', 0)
        need = target_campaign.get('users_needed', 1)
        cost_per_user = target_campaign.get('reward', 0)
        
        refund_amount = max(0, (need - comp) * cost_per_user)

        if refund_amount > 0:
            user_ref = firestore_db.collection('users').document(telegram_id_str)
            user_ref.set({
                'ad_balance': firestore.Increment(refund_amount)
            }, merge=True)

        # حذف الحملة نهائياً من فايربيس
        camp_ref.delete()

        return jsonify({
            "success": True, 
            "refund": refund_amount,
            "message": "تم إلغاء الحملة وإرجاع الميزانية المتبقية"
        }), 200

    except Exception as e:
        print(f"Error canceling campaign: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إلغاء الحملة"}), 500

@tasks_bp.route('/convert_adzn', methods=['POST'])
def convert_adzn():
    is_auth, telegram_id, err_response = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_response

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "المبلغ غير صحيح"}), 400

    if amount <= 0:
        return jsonify({"success": False, "error": "المبلغ غير صحيح"}), 400

    try:
        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404

        user_data = user_doc.to_dict() or {}
        current_balance = float(user_data.get('balance', 0.0))

        if current_balance < amount:
            return jsonify({"success": False, "error": "رصيد ZN الحالي غير كافٍ لهذا التحويل"}), 400

        fee = amount * 0.10
        received = amount - fee

        # خصم ZN وزيادة AdZN حقيقياً داخل فايربيس
        user_ref.set({
            'balance': firestore.Increment(-amount),
            'ad_balance': firestore.Increment(received)
        }, merge=True)

        new_balance = current_balance - amount
        new_ad_balance = float(user_data.get('ad_balance', 0.0)) + received

        return jsonify({
            "success": True,
            "received": received,
            "fee": fee,
            "new_balance": new_balance,
            "new_ad_balance": new_ad_balance,
            "message": "تم تحويل الرصيد وحفظه بنجاح"
        }), 200

    except Exception as e:
        print(f"Error in convert_adzn: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إجراء التحويل في السيرفر"}), 500


# tasks/tasks_api.py
import os
import json
import uuid
import time
import datetime
import urllib.parse
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from database import db as firestore_db
from firebase_admin import firestore

# إنشاء الـ Blueprint الخاص بمسارات المهام والحملات الإعلانية
tasks_bp = Blueprint('tasks', __name__)

# ==================== الإعدادات والثوابت ====================
# 🔒 الحد الأدنى لسعر الضغطة والميزانية الكلية للحملة
MIN_REWARD_PER_CLICK = 250.0
MIN_AD_CAMPAIGN_COST = 250.0

# 🚫 قائمة الكلمات المحظورة للمواقع والإعلانات المخالفة
FORBIDDEN_KEYWORDS = ['porn', 'sexy', 'xnx', 'adult', 'gambling', 'casino', 'bet365', '1xbet', 'sex', 'إباحي', 'جنس', 'قمار']

# ==================== In-Memory Cache for Campaigns ====================
_CAMPAIGNS_CACHE = None
_CAMPAIGNS_CACHE_TIME = 0
CAMPAIGNS_CACHE_TTL = 300  # كاش قائمة الحملات لمدة 5 دقائق (300 ثانية)

def get_cached_raw_campaigns():
    """
    جلب كافة الحملات الإعلانية من الذاكرة المؤقتة لـ RAM السيرفر.
    يمنع قراءة الفايربيس في كل طلب عشوائي إلا مرة واحدة كل 5 دقائق.
    """
    global _CAMPAIGNS_CACHE, _CAMPAIGNS_CACHE_TIME
    now = time.time()
    if _CAMPAIGNS_CACHE is not None and (now - _CAMPAIGNS_CACHE_TIME) < CAMPAIGNS_CACHE_TTL:
        return _CAMPAIGNS_CACHE

    try:
        campaigns = []
        docs = firestore_db.collection('campaigns').stream()
        for doc in docs:
            c_data = doc.to_dict() or {}
            c_data['id'] = doc.id
            campaigns.append(c_data)
        _CAMPAIGNS_CACHE = campaigns
        _CAMPAIGNS_CACHE_TIME = now
        return campaigns
    except Exception as e:
        print(f"[CACHE ERROR] Error fetching campaigns from Firestore: {e}")
        return _CAMPAIGNS_CACHE or []

def invalidate_campaigns_cache():
    """تفريغ الكاش لإجبار السيرفر على جلب التحديثات الجديدة فوراً عند إنشاء أو تجميد/إلغاء مهمة"""
    global _CAMPAIGNS_CACHE, _CAMPAIGNS_CACHE_TIME
    _CAMPAIGNS_CACHE = None
    _CAMPAIGNS_CACHE_TIME = 0
# ========================================================================

def is_task_completed_by_user(task, user_completed_data):
    """
    التحقق الآمن من إكمال المستخدم للمهمة،
    مع دعم إعادة فتح مهام زيارة المواقع يومياً.
    """
    task_id = str(task.get('id', '')).strip()
    platform = str(task.get('platform', '')).strip()
    
    if not user_completed_data or not task_id:
        return False

    today_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')

    if isinstance(user_completed_data, list):
        if task_id not in user_completed_data:
            return False
        if platform == 'موقع':
            return False
        return True

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
                    task_dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d')
                    return task_dt == today_str
            elif isinstance(record, (int, float)):
                task_dt = datetime.datetime.fromtimestamp(record, datetime.timezone.utc).strftime('%Y-%m-%d')
                return task_dt == today_str
            return False
        else:
            return True

    return False

# ==================== المسارات (Endpoints) ====================

@tasks_bp.route('/get_campaigns', methods=['GET'])
def get_campaigns():
    """جلب قائمة الحملات المتاحة للمستخدم مع تحديث حالة الإكمال والرصيد"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

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
        print(f"[FIRESTORE ERROR] Error fetching user data in get_campaigns: {e}")

    user_completed_data = {}
    try:
        completed_ref = firestore_db.collection('completed_tasks').document(telegram_id_str).get()
        if completed_ref.exists:
            user_completed_data = completed_ref.to_dict() or {}
    except Exception as e:
        print(f"[FIRESTORE ERROR] Error fetching completed tasks for user {telegram_id_str}: {e}")

    # قراءة المهام والحملات من الذاكرة المؤقتة لـ RAM
    campaigns = get_cached_raw_campaigns()

    result_campaigns = []
    for c in campaigns:
        # إخفاء المهام التي اكتمال أعضاؤها باستثناء المهام المملوكة للمستخدم نفسه لمتابعة التقدم
        creator_id_str = str(c.get('creator_id') or '').strip()
        if c.get('users_completed', 0) >= c.get('users_needed', 1) and creator_id_str != telegram_id_str:
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
    """إنشاء حملة إعلانية جديدة وتخصيص الميزانية لها"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    platform = str(req.get('platform', '')).strip()
    url = str(req.get('url', '')).strip()
    description = str(req.get('description', '')).strip()
    reward = req.get('reward')
    users_needed = req.get('users_needed')

    if not all([platform, url, description, reward, users_needed]):
        return jsonify({"success": False, "error": "جميع البيانات مطلوبة"}), 400

    if not (url.startswith('http://') or url.startswith('https://')):
        return jsonify({"success": False, "error": "الرابط يجب أن يبدأ بـ http:// أو https://"}), 400

    # 🛡️ الحماية والأمان للروابط المحظورة والمنصات
    url_lower = url.lower()
    if platform == 'يوتيوب' and not ('youtube.com' in url_lower or 'youtu.be' in url_lower):
        return jsonify({"success": False, "error": "رابط يوتيوب غير صحيح"}), 400
    if platform == 'تيليجرام' and 't.me' not in url_lower:
        return jsonify({"success": False, "error": "رابط تيليجرام غير صحيح"}), 400
    if platform == 'انستغرام' and 'instagram.com' not in url_lower:
        return jsonify({"success": False, "error": "رابط انستغرام غير صحيح"}), 400
    if platform == 'X' and not ('x.com' in url_lower or 'twitter.com' in url_lower):
        return jsonify({"success": False, "error": "رابط منصة X غير صحيح"}), 400

    if platform == 'موقع':
        if any(bad_word in url_lower for bad_word in FORBIDDEN_KEYWORDS):
            return jsonify({"success": False, "error": "الرابط يحتوي على محتوى مخالف للسياسات"}), 400

    try:
        reward = float(reward)
        users_needed = int(users_needed)
        if reward <= 0 or users_needed <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "قيم الكلفة والأعضاء غير صحيحة"}), 400

    if reward < MIN_REWARD_PER_CLICK:
        return jsonify({
            "success": False,
            "error": f"عذراً، الحد الأدنى لتكلفة الضغطة الواحدة هو {int(MIN_REWARD_PER_CLICK)} عملة AdZN."
        }), 400

    total_cost = reward * users_needed

    if total_cost < MIN_AD_CAMPAIGN_COST:
        return jsonify({
            "success": False,
            "error": f"عذراً، الحد الأدنى لتكلفة إنشاء أي حملة إعلانية هو {int(MIN_AD_CAMPAIGN_COST)} عملة AdZN."
        }), 400

    @firestore.transactional
    def run_create_transaction(transaction):
        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_snapshot = user_ref.get(transaction=transaction)

        if not user_snapshot.exists:
            raise ValueError("المستخدم غير موجود في الفايربيس")

        user_data = user_snapshot.to_dict() or {}
        current_ad_balance = float(user_data.get('ad_balance', 0.0))

        if current_ad_balance < total_cost:
            raise ValueError(f"رصيدك الإعلاني غير كافٍ. المطلوب: {total_cost} AdZN")

        new_ad_balance = current_ad_balance - total_cost

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
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        camp_ref = firestore_db.collection('campaigns').document(camp_id)
        
        transaction.update(user_ref, {'ad_balance': new_ad_balance})
        transaction.set(camp_ref, new_campaign)

        return new_campaign, new_ad_balance

    try:
        transaction = firestore_db.transaction()
        campaign_data, updated_ad_balance = run_create_transaction(transaction)

        # تفريغ كاش المهام لتظهر الحملة الجديدة للجميع فوراً
        invalidate_campaigns_cache()

        return jsonify({
            "success": True, 
            "campaign": campaign_data,
            "new_ad_balance": updated_ad_balance,
            "message": "تم إنشاء الإعلان ونشره بنجاح!"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error creating campaign: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء حفظ الحملة"}), 500


@tasks_bp.route('/complete_task', methods=['POST'])
def complete_task():
    """تأكيد إكمال المهمة إضافة المكافأة إلى رصيد المستخدم بشكل آمن (Transaction)"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    task_id = req.get('taskId')

    if not task_id:
        return jsonify({"success": False, "error": "رقم المهمة مفقود"}), 400

    @firestore.transactional
    def run_complete_transaction(transaction):
        camp_ref = firestore_db.collection('campaigns').document(str(task_id).strip())
        camp_snapshot = camp_ref.get(transaction=transaction)

        if not camp_snapshot.exists:
            raise ValueError("المهمة غير موجودة أو انتهت")

        target_campaign = camp_snapshot.to_dict() or {}
        target_campaign['id'] = camp_snapshot.id

        if str(target_campaign.get('creator_id')).strip() == telegram_id_str:
            raise ValueError("لا يمكنك تنفيذ حملتك الخاصة")

        users_completed = target_campaign.get('users_completed', 0)
        users_needed = target_campaign.get('users_needed', 1)

        if users_completed >= users_needed:
            raise ValueError("هذه المهمة مكتملة بالكامل واستوفت عدد الأعضاء المطلوب!")

        completed_ref = firestore_db.collection('completed_tasks').document(telegram_id_str)
        completed_snapshot = completed_ref.get(transaction=transaction)
        user_completed_map = completed_snapshot.to_dict() if completed_snapshot.exists else {}

        if is_task_completed_by_user(target_campaign, user_completed_map):
            if target_campaign.get('platform') == 'موقع':
                raise ValueError("لقد قمت بزيارة هذا الموقع اليوم، يمكنك زيارته غداً مجدداً!")
            else:
                raise ValueError("لقد قمت بإكمال هذه المهمة مسبقاً")

        reward_amount = float(target_campaign.get('reward', 0))

        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_snapshot = user_ref.get(transaction=transaction)
        
        current_balance = 0.0
        if user_snapshot.exists:
            current_balance = float((user_snapshot.to_dict() or {}).get('balance', 0.0))

        new_balance = current_balance + reward_amount

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        task_record = {
            "date": now_utc.strftime('%Y-%m-%d'),
            "timestamp": now_utc.timestamp()
        }

        transaction.set(user_ref, {'balance': new_balance}, merge=True)
        transaction.set(completed_ref, {task_id: task_record}, merge=True)
        transaction.update(camp_ref, {'users_completed': users_completed + 1})

        return reward_amount, new_balance

    try:
        transaction = firestore_db.transaction()
        reward_amount, new_balance = run_complete_transaction(transaction)

        # تفريغ كاش المهام لتحديث عدد المكتملين فوراً
        invalidate_campaigns_cache()

        return jsonify({
            "success": True, 
            "reward": reward_amount,
            "new_balance": new_balance,
            "message": "تم إكمال المهمة وإضافة المكافأة"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error completing task: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إكمال المهمة"}), 500


@tasks_bp.route('/cancel_campaign', methods=['POST'])
def cancel_campaign():
    """إلغاء الحملة وإرجاع ميزانية الأعضاء المتبقيين لرصيد صاحب الإعلان"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    campaign_id = req.get('campaignId')

    if not campaign_id:
        return jsonify({"success": False, "error": "معرف الحملة مفقود"}), 400

    @firestore.transactional
    def run_cancel_transaction(transaction):
        camp_ref = firestore_db.collection('campaigns').document(str(campaign_id).strip())
        camp_snapshot = camp_ref.get(transaction=transaction)

        if not camp_snapshot.exists:
            raise ValueError("الحملة غير موجودة")

        target_campaign = camp_snapshot.to_dict() or {}

        if str(target_campaign.get('creator_id')).strip() != telegram_id_str:
            raise ValueError("غير مصرح لك بإلغاء هذه الحملة")

        comp = target_campaign.get('users_completed', 0)
        need = target_campaign.get('users_needed', 1)
        cost_per_user = target_campaign.get('reward', 0)
        
        refund_amount = max(0.0, float((need - comp) * cost_per_user))

        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_snapshot = user_ref.get(transaction=transaction)
        
        current_ad_balance = 0.0
        if user_snapshot.exists:
            current_ad_balance = float((user_snapshot.to_dict() or {}).get('ad_balance', 0.0))

        new_ad_balance = current_ad_balance + refund_amount

        transaction.update(user_ref, {'ad_balance': new_ad_balance})
        transaction.delete(camp_ref)

        return refund_amount, new_ad_balance

    try:
        transaction = firestore_db.transaction()
        refund_amount, new_ad_balance = run_cancel_transaction(transaction)

        # تفريغ كاش المهام فوراً عند إلغاء أي حملة
        invalidate_campaigns_cache()

        return jsonify({
            "success": True, 
            "refund": refund_amount,
            "new_ad_balance": new_ad_balance,
            "message": "تم إلغاء الحملة وإرجاع الميزانية المتبقية"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error canceling campaign: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إلغاء الحملة"}), 500


@tasks_bp.route('/convert_adzn', methods=['POST'])
def convert_adzn():
    """تحويل الرصيد العادي (ZN) إلى رصيد إعلانات (ad_balance) مع خصم عمولة 10%"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "المبلغ غير صحيح"}), 400

    if amount <= 0:
        return jsonify({"success": False, "error": "المبلغ يجب أن يكون أكبر من صفر"}), 400

    @firestore.transactional
    def run_convert_transaction(transaction):
        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_snapshot = user_ref.get(transaction=transaction)

        if not user_snapshot.exists:
            raise ValueError("المستخدم غير موجود")

        user_data = user_snapshot.to_dict() or {}
        current_balance = float(user_data.get('balance', 0.0))
        current_ad_balance = float(user_data.get('ad_balance', 0.0))

        if current_balance < amount:
            raise ValueError("رصيد ZN الحالي غير كافٍ لهذا التحويل")

        fee = amount * 0.10
        received = amount - fee

        new_balance = current_balance - amount
        new_ad_balance = current_ad_balance + received

        transaction.update(user_ref, {
            'balance': new_balance,
            'ad_balance': new_ad_balance
        })

        return received, fee, new_balance, new_ad_balance

    try:
        transaction = firestore_db.transaction()
        received, fee, new_balance, new_ad_balance = run_convert_transaction(transaction)

        return jsonify({
            "success": True,
            "received": received,
            "fee": fee,
            "new_balance": new_balance,
            "new_ad_balance": new_ad_balance,
            "message": "تم تحويل الرصيد بنجاح"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error in convert_adzn: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إجراء التحويل في السيرفر"}), 500

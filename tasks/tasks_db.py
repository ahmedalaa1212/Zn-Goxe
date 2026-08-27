# tasks/tasks_db.py
import uuid
import time
import datetime
from firebase_admin import firestore
from database import db as firestore_db

# ==================== الثوابت والإعدادات الافتراضية ====================
DEFAULT_TASKS_CONFIG = {
    "min_reward_website": 15.0,
    "min_reward_default": 10.0,
    "min_reward_youtube": 10.0,
    "min_reward_telegram": 10.0,
    "min_reward_instagram": 10.0,
    "min_reward_x": 10.0,
    "wait_seconds": 15,
    "conversion_fee_percent": 10.0,
    "review_seconds": 3,
    "cache_ttl_seconds": 300
}

# كاش ديناميكي على مستوى السيرفر لقاعدة البيانات
_TASKS_CONFIG_CACHE = None
_TASKS_CONFIG_CACHE_TIME = 0
_CAMPAIGNS_CACHE = None
_CAMPAIGNS_CACHE_TIME = 0


# ==================== 1. إدارة الإعدادات ====================

def get_tasks_config() -> dict:
    """
    جلب وجدول الإعدادات الديناميكية والحد الأدنى للمكافآت لكل منصة.
    يتم استعلام كولكشن app_settings ومستند settings داخل حقل task.
    في حال عدم وجود المستند أو الحقل، يتم إنشاؤه تلقائياً في الفايربيس بقيم افتراضية.
    """
    global _TASKS_CONFIG_CACHE, _TASKS_CONFIG_CACHE_TIME
    now = time.time()

    cache_ttl = DEFAULT_TASKS_CONFIG["cache_ttl_seconds"]
    if _TASKS_CONFIG_CACHE and isinstance(_TASKS_CONFIG_CACHE, dict):
        cache_ttl = float(_TASKS_CONFIG_CACHE.get('cache_ttl_seconds', cache_ttl))

    if _TASKS_CONFIG_CACHE is not None and (now - _TASKS_CONFIG_CACHE_TIME) < cache_ttl:
        return _TASKS_CONFIG_CACHE

    try:
        doc_ref = firestore_db.collection('app_settings').document('settings')
        doc = doc_ref.get()

        should_update_db = False
        task_map = {}

        if doc.exists:
            doc_data = doc.to_dict() or {}
            if 'task' not in doc_data or not isinstance(doc_data.get('task'), dict):
                task_map = DEFAULT_TASKS_CONFIG.copy()
                should_update_db = True
            else:
                task_map = doc_data.get('task', {})
                for key, default_val in DEFAULT_TASKS_CONFIG.items():
                    if key not in task_map:
                        task_map[key] = default_val
                        should_update_db = True
        else:
            task_map = DEFAULT_TASKS_CONFIG.copy()
            should_update_db = True

        if should_update_db:
            doc_ref.set({'task': task_map}, merge=True)

        _TASKS_CONFIG_CACHE = {
            "min_reward_website": float(task_map.get('min_reward_website', DEFAULT_TASKS_CONFIG["min_reward_website"])),
            "min_reward_default": float(task_map.get('min_reward_default', DEFAULT_TASKS_CONFIG["min_reward_default"])),
            "min_reward_youtube": float(task_map.get('min_reward_youtube', DEFAULT_TASKS_CONFIG["min_reward_youtube"])),
            "min_reward_telegram": float(task_map.get('min_reward_telegram', DEFAULT_TASKS_CONFIG["min_reward_telegram"])),
            "min_reward_instagram": float(task_map.get('min_reward_instagram', DEFAULT_TASKS_CONFIG["min_reward_instagram"])),
            "min_reward_x": float(task_map.get('min_reward_x', DEFAULT_TASKS_CONFIG["min_reward_x"])),
            "wait_seconds": int(task_map.get('wait_seconds', DEFAULT_TASKS_CONFIG["wait_seconds"])),
            "conversion_fee_percent": float(task_map.get('conversion_fee_percent', DEFAULT_TASKS_CONFIG["conversion_fee_percent"])),
            "review_seconds": int(task_map.get('review_seconds', DEFAULT_TASKS_CONFIG["review_seconds"])),
            "cache_ttl_seconds": int(task_map.get('cache_ttl_seconds', DEFAULT_TASKS_CONFIG["cache_ttl_seconds"]))
        }

        _TASKS_CONFIG_CACHE_TIME = now
        return _TASKS_CONFIG_CACHE

    except Exception as e:
        print(f"[TASKS DB ERROR] Error fetching task settings from Firestore: {e}")
        if _TASKS_CONFIG_CACHE is not None:
            return _TASKS_CONFIG_CACHE
        return DEFAULT_TASKS_CONFIG.copy()


def get_min_reward_for_platform(platform: str, config: dict = None) -> float:
    """تحديد الحد الأدنى لتكلفة المهمة الواحدة بناءً على المنصة والإعدادات الديناميكية"""
    if config is None:
        config = get_tasks_config()

    platform_clean = str(platform).strip().lower()

    if platform_clean in ['موقع', 'website']:
        return float(config.get('min_reward_website', 15.0))
    elif platform_clean in ['يوتيوب', 'youtube']:
        return float(config.get('min_reward_youtube', 10.0))
    elif platform_clean in ['تيليجرام', 'telegram']:
        return float(config.get('min_reward_telegram', 10.0))
    elif platform_clean in ['انستغرام', 'instagram']:
        return float(config.get('min_reward_instagram', 10.0))
    elif platform_clean in ['x', 'twitter', 'منصة x']:
        return float(config.get('min_reward_x', 10.0))
    else:
        return float(config.get('min_reward_default', 10.0))


# ==================== 2. التحقق من إكمال المهام ====================

def is_task_completed_by_user(task: dict, user_completed_data: dict) -> bool:
    """
    التحقق الآمن من إكمال المستخدم للمهمة،
    مع فتح مهام زيارة المواقع مجدداً عند دخول يوم جديد بتوقيت UTC (00:00 UTC).
    """
    task_id = str(task.get('id', '')).strip()
    platform = str(task.get('platform', '')).strip().lower()
    is_website_task = platform in ['موقع', 'website']

    if not user_completed_data or not task_id:
        return False

    today_utc_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')

    # السجلات القديمة المخزنة كقائمة List
    if isinstance(user_completed_data, list):
        if task_id not in user_completed_data:
            return False
        if is_website_task:
            return False  # إعادة فتح مهام المواقع يومياً
        return True

    # السجلات المحدثة المخزنة كـ Map/Dict
    if isinstance(user_completed_data, dict):
        if task_id not in user_completed_data:
            return False

        record = user_completed_data[task_id]

        if is_website_task:
            if isinstance(record, str):
                return record == today_utc_str
            elif isinstance(record, dict):
                task_date = record.get('date')
                if task_date:
                    return str(task_date) == today_utc_str
                ts = record.get('timestamp')
                if ts:
                    task_dt = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).strftime('%Y-%m-%d')
                    return task_dt == today_utc_str
            elif isinstance(record, (int, float)):
                task_dt = datetime.datetime.fromtimestamp(float(record), datetime.timezone.utc).strftime('%Y-%m-%d')
                return task_dt == today_utc_str
            return False
        else:
            return True

    return False


# ==================== 3. جلب الحملات النشطة ====================

def invalidate_campaigns_cache():
    """تفريغ كاش الحملات لإجبار السيرفر على إعادة القراءة من Firestore عند إنشاء أو إلغاء مهمة"""
    global _CAMPAIGNS_CACHE, _CAMPAIGNS_CACHE_TIME
    _CAMPAIGNS_CACHE = None
    _CAMPAIGNS_CACHE_TIME = 0


def get_cached_raw_campaigns(cache_ttl: int = 300) -> list:
    """جلب كافة الحملات الإعلانية من Firestore مع تفعيل كاش RAM لتخفيف الضغط"""
    global _CAMPAIGNS_CACHE, _CAMPAIGNS_CACHE_TIME
    now = time.time()

    if _CAMPAIGNS_CACHE is not None and (now - _CAMPAIGNS_CACHE_TIME) < cache_ttl:
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
        print(f"[TASKS DB ERROR] Error reading campaigns from Firestore: {e}")
        return _CAMPAIGNS_CACHE or []


def get_active_campaigns(telegram_id_str: str) -> list:
    """
    جلب وتصفية قائمة الحملات الإعلانية النشطة والمتاحة للمستخدم،
    مع التحقق من حالة الإكمال واستبعاد الحملات المنتهية (إلا إن كان المستخدم هو المنشئ).
    """
    telegram_id_str = str(telegram_id_str).strip()

    user_completed_data = {}
    try:
        completed_ref = firestore_db.collection('completed_tasks').document(telegram_id_str).get()
        if completed_ref.exists:
            user_completed_data = completed_ref.to_dict() or {}
    except Exception as e:
        print(f"[TASKS DB ERROR] Error reading completed_tasks for user {telegram_id_str}: {e}")

    raw_campaigns = get_cached_raw_campaigns()
    result_campaigns = []

    for c in raw_campaigns:
        creator_id_str = str(c.get('creator_id') or '').strip()
        users_completed = int(c.get('users_completed', 0))
        users_needed = int(c.get('users_needed', 1))

        # استبعاد الحملات التي اكتملت إلا لو كان المستخدم هو ناشر الحملة نفسه
        if users_completed >= users_needed and creator_id_str != telegram_id_str:
            continue

        c_copy = dict(c)
        c_copy['is_completed'] = is_task_completed_by_user(c, user_completed_data)
        result_campaigns.append(c_copy)

    return result_campaigns


# ==================== 4. إكمال المهمة ====================

def complete_user_task(telegram_id_str: str, task_id: str) -> tuple:
    """
    إكمال المهمة بطلب آمن عبر Firestore Transaction:
    1. التأكد من وجود المهمة وعدم اكتمال عدد منفذيها.
    2. التحقق من عدم قيام صاحب الإعلان بتنفيذ مهمته بنفسه.
    3. التحقق من عدم تكرار الإكمال في نفس اليوم للمواقع أو مطلقاً للمنصات الأخرى.
    4. زيادة رصيد المستخدم (balance) بالعملة المكافأة وتحديث سجلات الإكمال.
    """
    telegram_id_str = str(telegram_id_str).strip()
    task_id_str = str(task_id).strip()

    @firestore.transactional
    def run_complete_transaction(transaction):
        camp_ref = firestore_db.collection('campaigns').document(task_id_str)
        camp_snapshot = camp_ref.get(transaction=transaction)

        if not camp_snapshot.exists:
            raise ValueError("المهمة غير موجودة أو تم إلغاؤها")

        target_campaign = camp_snapshot.to_dict() or {}
        target_campaign['id'] = camp_snapshot.id

        if str(target_campaign.get('creator_id')).strip() == telegram_id_str:
            raise ValueError("لا يمكنك تنفيذ حملتك الإعلانية الخاصة")

        users_completed = int(target_campaign.get('users_completed', 0))
        users_needed = int(target_campaign.get('users_needed', 1))

        if users_completed >= users_needed:
            raise ValueError("هذه المهمة مكتملة بالكامل واستوفت عدد الأعضاء المطلوب")

        completed_ref = firestore_db.collection('completed_tasks').document(telegram_id_str)
        completed_snapshot = completed_ref.get(transaction=transaction)
        user_completed_map = completed_snapshot.to_dict() if completed_snapshot.exists else {}

        if is_task_completed_by_user(target_campaign, user_completed_map):
            platform_clean = str(target_campaign.get('platform', '')).strip().lower()
            if platform_clean in ['موقع', 'website']:
                raise ValueError("لقد قمت بزيارة هذا الموقع اليوم، يمكنك زيارته مجدداً غداً!")
            else:
                raise ValueError("لقد قمت بإكمال هذه المهمة مسبقاً")

        reward_amount = float(target_campaign.get('reward', 0.0))

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
        transaction.set(completed_ref, {task_id_str: task_record}, merge=True)
        transaction.update(camp_ref, {'users_completed': users_completed + 1})

        return reward_amount, new_balance

    transaction = firestore_db.transaction()
    reward, new_balance = run_complete_transaction(transaction)
    invalidate_campaigns_cache()
    return reward, new_balance


# ==================== 5. إنشاء وتخفيض الحملة الإعلانية ====================

def create_ad_campaign(
    telegram_id_str: str, 
    platform: str, 
    url: str, 
    description: str, 
    reward: float, 
    users_needed: int
) -> tuple:
    """
    خصم تكلفة الحملة الكلية من رصيد الإعلانات (ad_balance) وإنشاء مستند الحملة في Firestore بأمان.
    """
    telegram_id_str = str(telegram_id_str).strip()
    total_cost = reward * users_needed

    @firestore.transactional
    def run_create_transaction(transaction):
        user_ref = firestore_db.collection('users').document(telegram_id_str)
        user_snapshot = user_ref.get(transaction=transaction)

        if not user_snapshot.exists:
            raise ValueError("المستخدم غير موجود في قاعدة البيانات")

        user_data = user_snapshot.to_dict() or {}
        current_ad_balance = float(user_data.get('ad_balance', 0.0))

        if current_ad_balance < total_cost:
            raise ValueError(f"رصيدك الإعلاني غير كافٍ. المطلوب: {total_cost} AdZ")

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

    transaction = firestore_db.transaction()
    campaign_data, updated_ad_balance = run_create_transaction(transaction)
    invalidate_campaigns_cache()
    return campaign_data, updated_ad_balance


def cancel_ad_campaign(telegram_id_str: str, campaign_id: str) -> tuple:
    """
    إلغاء الحملة وإعادة المبلغ المتبقي للأعضاء غير المنفذين إلى رصيد الإعلانات ad_balance.
    """
    telegram_id_str = str(telegram_id_str).strip()
    campaign_id_str = str(campaign_id).strip()

    @firestore.transactional
    def run_cancel_transaction(transaction):
        camp_ref = firestore_db.collection('campaigns').document(campaign_id_str)
        camp_snapshot = camp_ref.get(transaction=transaction)

        if not camp_snapshot.exists:
            raise ValueError("الحملة غير موجودة")

        target_campaign = camp_snapshot.to_dict() or {}

        if str(target_campaign.get('creator_id')).strip() != telegram_id_str:
            raise ValueError("غير مصرح لك بإلغاء هذه الحملة")

        comp = int(target_campaign.get('users_completed', 0))
        need = int(target_campaign.get('users_needed', 1))
        cost_per_user = float(target_campaign.get('reward', 0.0))

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

    transaction = firestore_db.transaction()
    refund_amount, new_ad_balance = run_cancel_transaction(transaction)
    invalidate_campaigns_cache()
    return refund_amount, new_ad_balance


# ==================== 6. تحويل الرصيد (ZN -> AdZ) ====================

def convert_balance_to_ad_balance(telegram_id_str: str, amount: float) -> tuple:
    """
    تحويل الرصيد الأساسي (ZN) إلى رصيد الإعلانات (AdZ) بعد خصم العمولة الديناميكية.
    """
    telegram_id_str = str(telegram_id_str).strip()

    if amount <= 0:
        raise ValueError("المبلغ المراد تحويله يجب أن يكون أكبر من صفر")

    config = get_tasks_config()
    fee_percent = float(config.get('conversion_fee_percent', 10.0))

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
            raise ValueError("رصيد ZN الحالي غير كافٍ لإجراء التحويل")

        fee = amount * (fee_percent / 100.0)
        received = amount - fee

        new_balance = current_balance - amount
        new_ad_balance = current_ad_balance + received

        transaction.update(user_ref, {
            'balance': new_balance,
            'ad_balance': new_ad_balance
        })

        return received, fee, fee_percent, new_balance, new_ad_balance

    transaction = firestore_db.transaction()
    return run_convert_transaction(transaction)

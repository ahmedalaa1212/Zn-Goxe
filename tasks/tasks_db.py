# tasks/tasks_db.py
from datetime import datetime, timezone
from firebase_admin import firestore
import database

# ==================== الإعدادات والكاش الديناميكي ====================
_CONFIG_CACHE = None
_CONFIG_CACHE_TIME = 0

DEFAULT_TASK_CONFIG = {
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

def get_tasks_config():
    """
    جلب الإعدادات من كولكشن app_settings -> مستند settings -> حقل task (Map).
    يقوم بإنشاء الكولكشن والمستند والحقل تلقائياً في الفايربيس فوراً إذا لم تكن موجودة.
    """
    global _CONFIG_CACHE, _CONFIG_CACHE_TIME
    now = datetime.now(timezone.utc).timestamp()
    
    ttl = _CONFIG_CACHE.get("cache_ttl_seconds", 300) if isinstance(_CONFIG_CACHE, dict) else 300
    if _CONFIG_CACHE and (now - _CONFIG_CACHE_TIME) < ttl:
        return _CONFIG_CACHE

    try:
        db = database.get_db()
        doc_ref = db.collection("app_settings").document("settings")
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict() or {}
            task_map = data.get("task")
            if isinstance(task_map, dict) and task_map:
                config = {**DEFAULT_TASK_CONFIG, **task_map}
            else:
                # المستند موجود ولكن حقل task غير موجود -> إنشاؤه وكتابته فوراً
                doc_ref.set({"task": DEFAULT_TASK_CONFIG}, merge=True)
                config = DEFAULT_TASK_CONFIG.copy()
        else:
            # المستند والكولكشن غير موجودين نهائياً -> إنشاؤهما في القاعدة فوراً
            doc_ref.set({"task": DEFAULT_TASK_CONFIG}, merge=True)
            config = DEFAULT_TASK_CONFIG.copy()

        _CONFIG_CACHE = config
        _CONFIG_CACHE_TIME = now
        return config
    except Exception as e:
        print(f"❌ Error fetching/creating app_settings/settings: {e}")
        if _CONFIG_CACHE is not None:
            return _CONFIG_CACHE
        return DEFAULT_TASK_CONFIG.copy()

def get_min_reward_for_platform(platform: str) -> float:
    """تحديد الحد الأدنى لتكلفة المهمة حسب نوع المنصة بناءً على الإعدادات الديناميكية"""
    config = get_tasks_config()
    p = str(platform).strip().lower()
    
    if p in ['موقع', 'website']:
        return float(config.get("min_reward_website", 15.0))
    elif p in ['يوتيوب', 'youtube']:
        return float(config.get("min_reward_youtube", 10.0))
    elif p in ['تيليجرام', 'telegram']:
        return float(config.get("min_reward_telegram", 10.0))
    elif p in ['انستغرام', 'instagram']:
        return float(config.get("min_reward_instagram", 10.0))
    elif p in ['x', 'twitter', 'منصة x']:
        return float(config.get("min_reward_x", 10.0))
    else:
        return float(config.get("min_reward_default", 10.0))

def is_task_completed_by_user(task_id: str, platform: str, user_completed_map: dict) -> bool:
    """
    التحقق الآمن من إكمال المهمة، مع فتح مهام المواقع مجدداً عند دخول يوم جديد بـ UTC.
    """
    if not user_completed_map or task_id not in user_completed_map:
        return False

    p = str(platform).strip().lower()
    is_website = (p in ['موقع', 'website'])

    if not is_website:
        return True  # باقي المنصات تنفذ مرة واحدة فقط

    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    record = user_completed_map[task_id]

    if isinstance(record, str):
        return record == today_utc
    elif isinstance(record, dict):
        task_date = record.get('date')
        if task_date:
            return str(task_date) == today_utc
        ts = record.get('timestamp')
        if ts:
            task_dt = datetime.fromtimestamp(float(ts), timezone.utc).strftime('%Y-%m-%d')
            return task_dt == today_utc
    elif isinstance(record, (int, float)):
        task_dt = datetime.fromtimestamp(float(record), timezone.utc).strftime('%Y-%m-%d')
        return task_dt == today_utc

    return False

# ==================== العمليات والاستعلامات ====================

def get_active_campaigns(tg_id):
    """جلب قائمة المهمات النشطة مراعياً شرط التجديد اليومي بـ UTC وإجبار إنشاء مستند الإعدادات"""
    try:
        # استدعاء دالة الإعدادات هنا يضمن إنشاء الكولكشن والمستند فوراً في الفايربيس عند فتح المهام
        _ = get_tasks_config()

        db = database.get_db()
        tg_id_str = str(tg_id).strip()
        
        user_doc = db.collection("users").document(tg_id_str).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}

        completed_doc = db.collection("completed_tasks").document(tg_id_str).get()
        user_completed_map = completed_doc.to_dict() if completed_doc.exists else {}

        campaigns_ref = db.collection("campaigns").limit(50)
        docs = campaigns_ref.stream()

        campaigns = []
        for doc in docs:
            d = doc.to_dict() or {}
            cid = doc.id
            comp_count = int(d.get("users_completed", 0))
            need_count = int(d.get("users_needed", 1))

            if comp_count >= need_count and str(d.get("creator_id", "")).strip() != tg_id_str:
                continue

            platform = d.get("platform", "أخرى")
            is_comp = is_task_completed_by_user(cid, platform, user_completed_map)

            campaigns.append({
                "id": cid,
                "creator_id": str(d.get("creator_id", "")),
                "platform": platform,
                "description": d.get("description", ""),
                "url": d.get("url", ""),
                "reward": float(d.get("reward", 0) or 0),
                "users_needed": need_count,
                "users_completed": comp_count,
                "is_completed": is_comp,
            })

        return (
            campaigns,
            float(user_data.get("balance", 0.0) or 0.0),
            float(user_data.get("ad_balance", 0.0) or 0.0),
        )
    except Exception as e:
        print(f"❌ Error fetching active campaigns: {e}")
        return [], 0.0, 0.0


def complete_user_task(tg_id, task_id):
    """إكمال مهمة وتسليم مكافأتها بأمان مالي مع تسجيل التاريخ بـ UTC"""
    try:
        if not tg_id or not task_id:
            return False, "بيانات غير صالحة", 0.0
        db = database.get_db()
        tg_id_str, task_id_str = str(tg_id).strip(), str(task_id).strip()

        user_ref = db.collection("users").document(tg_id_str)
        camp_ref = db.collection("campaigns").document(task_id_str)
        completed_ref = db.collection("completed_tasks").document(tg_id_str)

        user_doc, camp_doc = user_ref.get(), camp_ref.get()

        if not user_doc.exists or not camp_doc.exists:
            return False, "المهمة أو المستخدم غير موجود", 0.0

        user_data = user_doc.to_dict() or {}
        task_data = camp_doc.to_dict() or {}

        if str(task_data.get("creator_id", "")).strip() == tg_id_str:
            return False, "لا يمكنك تنفيذ حملتك الخاصة", float(user_data.get("balance", 0.0) or 0.0)

        completed_doc = completed_ref.get()
        completed_map = completed_doc.to_dict() if completed_doc.exists else {}

        platform = task_data.get("platform", "أخرى")
        if is_task_completed_by_user(task_id_str, platform, completed_map):
            p = str(platform).strip().lower()
            if p in ['موقع', 'website']:
                msg = "لقد قمت بزيارة هذا الموقع اليوم، يمكنك زيارته غداً مجدداً!"
            else:
                msg = "تم إكمال المهمة سابقاً!"
            return False, msg, float(user_data.get("balance", 0.0) or 0.0)

        reward = float(task_data.get("reward", 0.0) or 0.0)
        new_balance = round(float(user_data.get("balance", 0.0) or 0.0) + reward, 2)

        now_utc = datetime.now(timezone.utc)
        task_record = {
            "date": now_utc.strftime('%Y-%m-%d'),
            "timestamp": now_utc.timestamp()
        }

        camp_ref.update({"users_completed": firestore.Increment(1)})
        user_ref.update({"balance": new_balance})
        completed_ref.set({task_id_str: task_record}, merge=True)

        return True, "تم إكمال المهمة بنجاح!", new_balance
    except Exception as e:
        print(f"❌ Error completing task {task_id}: {e}")
        return False, "حدث خطأ أثناء معالجة المهمة", 0.0


def create_ad_campaign(tg_id, platform, description, url, reward, users_needed):
    """إنشاء حملة إعلانية جديدة مع مراعاة الحدود الأدنى للمنصات من الفايربيس"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", 0.0
        db = database.get_db()
        tg_id_str = str(tg_id).strip()

        reward = float(reward)
        users_needed = int(users_needed)
        total_cost = reward * users_needed

        min_reward = get_min_reward_for_platform(platform)
        min_val_str = f"{int(min_reward)}" if min_reward.is_integer() else f"{min_reward}"

        if reward < min_reward:
            return False, f"عذراً، الحد الأدنى لتكلفة المهمة الواحدة لمنصة ({platform}) هو {min_val_str} عملة AdZ.", 0.0

        if total_cost < min_reward:
            return False, f"عذراً، الحد الأدنى لتكلفة إنشاء أي حملة إعلانية هو {min_val_str} عملة AdZ.", 0.0

        user_ref = db.collection("users").document(tg_id_str)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0.0

        current_ad_bal = float((user_doc.to_dict() or {}).get("ad_balance", 0.0) or 0.0)
        if current_ad_bal < total_cost:
            return False, f"رصيد الإعلانات غير كافٍ! المطلوب: {total_cost} AdZ", current_ad_bal

        new_ad_bal = round(current_ad_bal - total_cost, 2)
        user_ref.update({"ad_balance": new_ad_bal})

        campaign_doc = {
            "creator_id": tg_id_str,
            "platform": platform,
            "description": description,
            "url": url,
            "reward": reward,
            "users_needed": users_needed,
            "users_completed": 0,
            "active": True,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("campaigns").add(campaign_doc)

        return True, "تم إنشاء الحملة بنجاح!", new_ad_bal
    except Exception as e:
        print(f"❌ Error creating campaign: {e}")
        return False, f"حدث خطأ: {e}", 0.0


def convert_balance_to_ad_balance(tg_id, amount):
    """تحويل من الرصيد ZN إلى رصيد الإعلانات AdZ مع عمولة ديناميكية محددة بالفايربيس"""
    try:
        if not tg_id or amount <= 0:
            return False, "مبلغ غير صالح", 0.0, 0.0
        db = database.get_db()
        tg_id_str = str(tg_id).strip()
        user_ref = db.collection("users").document(tg_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0.0, 0.0

        user_data = user_doc.to_dict() or {}
        current_bal = float(user_data.get("balance", 0.0) or 0.0)
        current_ad_bal = float(user_data.get("ad_balance", 0.0) or 0.0)

        if current_bal < amount:
            return False, "رصيدك الأساسي غير كافٍ!", current_bal, current_ad_bal

        config = get_tasks_config()
        fee_percent = float(config.get("conversion_fee_percent", 10.0))

        fee = amount * (fee_percent / 100.0)
        received = amount - fee

        new_bal = round(current_bal - amount, 2)
        new_ad_bal = round(current_ad_bal + received, 2)

        user_ref.update({
            "balance": new_bal,
            "ad_balance": new_ad_bal
        })

        return True, "تم تحويل الرصيد بنجاح!", new_bal, new_ad_bal
    except Exception as e:
        print(f"❌ Error converting balance: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0.0

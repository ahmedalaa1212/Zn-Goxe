# tasks/tasks_db.py
from datetime import datetime, timezone
from firebase_admin import firestore
import database

def get_min_reward_for_platform(platform: str) -> float:
    """تحديد الحد الأدنى لتكلفة الضغطة حسب المنصة"""
    if str(platform).strip() == 'موقع':
        return 100.0
    return 50.0

def get_active_campaigns(tg_id):
    """جلب قائمة المهمات النشطة والتوافق مع المجمّع الرئيسي"""
    try:
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

            is_comp = cid in user_completed_map

            campaigns.append({
                "id": cid,
                "creator_id": str(d.get("creator_id", "")),
                "platform": d.get("platform", "أخرى"),
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
    """إكمال مهمة وتسليم مكافأتها بأمان مالي"""
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

        if task_id_str in completed_map:
            return (
                False,
                "تم إكمال المهمة سابقاً!",
                float(user_data.get("balance", 0.0) or 0.0),
            )

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
    """إنشاء حملة إعلانية جديدة مع مراعاة الحدود الأدنى للمنصات"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", 0.0
        db = database.get_db()
        tg_id_str = str(tg_id).strip()

        reward = float(reward)
        users_needed = int(users_needed)
        total_cost = reward * users_needed

        min_reward = get_min_reward_for_platform(platform)

        if reward < min_reward or total_cost < min_reward:
            return False, f"الحد الأدنى لتكلفة المهمة لهذه المنصة هو {int(min_reward)} AdZ", 0.0

        user_ref = db.collection("users").document(tg_id_str)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0.0

        current_ad_bal = float((user_doc.to_dict() or {}).get("ad_balance", 0.0) or 0.0)
        if current_ad_bal < total_cost:
            return False, "رصيد الإعلانات غير كافٍ!", current_ad_bal

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
    """تحويل من الرصيد ZN إلى رصيد الإعلانات AdZ مع عمولة 10%"""
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

        fee = amount * 0.10
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

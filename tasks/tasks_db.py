from datetime import datetime, timezone
from firebase_admin import firestore
import database

def get_active_campaigns(tg_id):
    """جلب قائمة المهمات النشطة"""
    try:
        db = database.get_db()
        user_data = database.get_user(tg_id) or {}
        completed_list = [str(x) for x in user_data.get("completed_tasks", [])]

        campaigns_ref = db.collection("tasks").where("active", "==", True).limit(50)
        docs = campaigns_ref.stream()

        campaigns = []
        for doc in docs:
            d = doc.to_dict() or {}
            cid = doc.id
            comp_count = int(d.get("users_completed", 0))
            need_count = int(d.get("users_needed", 1))

            if comp_count >= need_count:
                continue

            campaigns.append({
                "id": cid,
                "creator_id": str(d.get("creator_id", "")),
                "platform": d.get("platform", "أخرى"),
                "description": d.get("description", ""),
                "url": d.get("url", ""),
                "reward": float(d.get("reward", 0) or 0),
                "users_needed": need_count,
                "users_completed": comp_count,
                "is_completed": (cid in completed_list),
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
    """إكمال مهمة وتسليم مكافأتها"""
    try:
        if not tg_id or not task_id:
            return False, "بيانات غير صالحة", 0.0
        db = database.get_db()
        tg_id_str, task_id_str = str(tg_id), str(task_id)

        user_ref = db.collection("users").document(tg_id_str)
        task_ref = db.collection("tasks").document(task_id_str)

        user_doc, task_doc = user_ref.get(), task_ref.get()

        if not user_doc.exists or not task_doc.exists:
            return False, "المهمة أو المستخدم غير موجود", 0.0

        user_data = user_doc.to_dict() or {}
        task_data = task_doc.to_dict() or {}

        completed = [str(x) for x in user_data.get("completed_tasks", [])]
        if task_id_str in completed:
            return (
                False,
                "تم إكمال المهمة سابقاً!",
                float(user_data.get("balance", 0.0) or 0.0),
            )

        reward = float(task_data.get("reward", 0.0) or 0.0)
        new_balance = round(float(user_data.get("balance", 0.0) or 0.0) + reward, 2)

        task_ref.update({"users_completed": firestore.Increment(1)})
        user_ref.update({
            "balance": new_balance,
            "completed_tasks": firestore.ArrayUnion([task_id_str]),
        })

        return True, "تم إكمال المهمة بنجاح!", new_balance
    except Exception as e:
        print(f"❌ Error completing task {task_id}: {e}")
        return False, "حدث خطأ أثناء معالجة المهمة", 0.0


def create_ad_campaign(tg_id, platform, description, url, reward, users_needed):
    """إنشاء حملة إعلانية جديدة"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", 0.0
        db = database.get_db()
        tg_id_str = str(tg_id)

        reward = float(reward)
        users_needed = int(users_needed)
        total_cost = reward * users_needed

        if reward < 250 or total_cost < 250:
            return False, "الحد الأدنى لتكلفة الضغطة والميزانية هو 250 AdZN", 0.0

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
        db.collection("tasks").add(campaign_doc)

        return True, "تم إنشاء الحملة بنجاح!", new_ad_bal
    except Exception as e:
        print(f"❌ Error creating campaign: {e}")
        return False, f"حدث خطأ: {e}", 0.0


def convert_balance_to_ad_balance(tg_id, amount):
    """تحويل من الرصيد ZN إلى رصيد الإعلانات AdZN"""
    try:
        if not tg_id or amount <= 0:
            return False, "مبلغ غير صالح", 0.0, 0.0
        db = database.get_db()
        tg_id_str = str(tg_id)
        user_ref = db.collection("users").document(tg_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0.0, 0.0

        user_data = user_doc.to_dict() or {}
        current_bal = float(user_data.get("balance", 0.0) or 0.0)
        current_ad_bal = float(user_data.get("ad_balance", 0.0) or 0.0)

        if current_bal < amount:
            return False, "رصيدك الأساسي غير كافٍ!", current_bal, current_ad_bal

        new_bal = round(current_bal - amount, 2)
        new_ad_bal = round(current_ad_bal + amount, 2)

        user_ref.update({"balance": new_bal, "ad_balance": new_ad_bal})

        return True, "تم التحويل بنجاح!", new_bal, new_ad_bal
    except Exception as e:
        print(f"❌ Error converting balance: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0.0


def claim_daily_reward(tg_id):
    """استلام المكافأة اليومية للمستخدم"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", 0.0, 0
        user_data = database.get_user(tg_id)
        if not user_data:
            return False, "المستخدم غير موجود", 0.0, 0

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last_claim_date = user_data.get("last_daily_claim_date")

        if last_claim_date == today_str:
            return (
                False,
                "لقد استلمت المكافأة اليومية بالفعل اليوم!",
                user_data.get("balance", 0.0),
                user_data.get("daily_streak", 0),
            )

        current_streak = int(user_data.get("daily_streak", 0)) + 1
        if current_streak > 30:
            current_streak = 1

        settings = database.get_game_settings()
        rewards_map = settings.get("daily_rewards", {})
        reward_amount = float(rewards_map.get(f"day_{current_streak}", 100))

        new_balance = round(float(user_data.get("balance", 0.0) or 0.0) + reward_amount, 2)

        database.update_user(tg_id, {
            "balance": new_balance,
            "daily_streak": current_streak,
            "last_daily_claim_date": today_str,
        })

        return (
            True,
            f"تم استلام مكافأة اليوم {current_streak} بنجاح (+{reward_amount} ZN)!",
            new_balance,
            current_streak,
        )
    except Exception as e:
        print(f"❌ Error claiming daily reward: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0

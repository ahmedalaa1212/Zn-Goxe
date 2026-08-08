from firebase_admin import firestore
import database

def get_user_friends(tg_id, limit=50):
    """جلب قائمة الأصدقاء والإحالات الخاصة بالمستخدم"""
    try:
        db = database.get_db()
        friends_ref = (
            db.collection("users")
            .document(str(tg_id))
            .collection("friends")
            .limit(limit)
        )
        docs = friends_ref.stream()
        friends = []
        for doc in docs:
            d = doc.to_dict() or {}
            friends.append({
                "tg_id": str(d.get("tg_id", doc.id)),
                "first_name": d.get("first_name", "صديق"),
                "earned_from_him": float(d.get("earned_from_him", 0.0) or 0.0),
            })
        return friends
    except Exception as e:
        print(f"❌ Error getting user friends for {tg_id}: {e}")
        return []


def add_referral_reward(referrer_id, amount):
    """إضافة مكافأة الإحالة للمُحيل"""
    try:
        if not referrer_id or amount <= 0:
            return False
        db = database.get_db()
        ref_str = str(referrer_id)
        user_ref = db.collection("users").document(ref_str)
        user_ref.update({
            "balance": firestore.Increment(amount),
            "total_ref_earnings": firestore.Increment(amount),
        })
        return True
    except Exception as e:
        print(f"❌ Error adding referral reward for {referrer_id}: {e}")
        return False

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


def get_friends_list_db(tg_id):
    """جلب قائمة الأصدقاء للاستخدام في API الأصدقاء"""
    return get_user_friends(tg_id)


def get_friends_data_db(tg_id):
    """جلب ملخص إحصائيات الأصدقاء والمكافآت"""
    try:
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        doc = user_ref.get()
        
        user_data = doc.to_dict() if doc.exists else {}
        friends = get_user_friends(tg_id)
        
        return {
            "friends_count": len(friends),
            "total_ref_earnings": float(user_data.get("total_ref_earnings", 0.0) or 0.0),
            "pending_ref_earnings": float(user_data.get("pending_ref_earnings", 0.0) or 0.0),
            "referral_code": str(tg_id)
        }
    except Exception as e:
        print(f"❌ Error getting friends data for {tg_id}: {e}")
        return {
            "friends_count": 0,
            "total_ref_earnings": 0.0,
            "pending_ref_earnings": 0.0,
            "referral_code": str(tg_id)
        }


def claim_ref_earnings_db(tg_id):
    """سحب أرباح الإحالات المعلقة وتحويلها للرصيد الرئيسي"""
    try:
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        
        @firestore.transactional
        def update_in_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
            
            data = snapshot.to_dict() or {}
            pending = float(data.get("pending_ref_earnings", 0.0) or 0.0)
            
            if pending <= 0:
                return {"success": False, "error": "لا توجد أرباح معلقة للسحب"}
            
            current_balance = float(data.get("balance", 0.0) or 0.0)
            new_balance = current_balance + pending
            
            transaction.update(ref, {
                "balance": new_balance,
                "pending_ref_earnings": 0.0
            })
            
            return {
                "success": True,
                "claimed_amount": pending,
                "new_balance": new_balance,
                "message": f"تم سحب {pending} بنجاح إلى رصيدك الرئيسي"
            }
        
        transaction = db.transaction()
        return update_in_transaction(transaction, user_ref)
    except Exception as e:
        print(f"❌ Error claiming ref earnings for {tg_id}: {e}")
        return {"success": False, "error": "حدث خطأ أثناء تنفيذ عملية السحب"}


def claim_ref_task_db(tg_id, task_id):
    """استلام مكافأة مهمة الإحالة"""
    try:
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        
        doc = user_ref.get()
        if not doc.exists:
            return {"success": False, "error": "المستخدم غير موجود"}
            
        user_data = doc.to_dict() or {}
        claimed_tasks = user_data.get("claimed_ref_tasks", [])
        
        if str(task_id) in [str(t) for t in claimed_tasks]:
            return {"success": False, "error": "تم استلام مكافأة هذه المهمة من قبل"}
        
        user_ref.update({
            "claimed_ref_tasks": firestore.ArrayUnion([str(task_id)])
        })
        
        return {"success": True, "message": "تم استلام مكافأة المهمة بنجاح"}
    except Exception as e:
        print(f"❌ Error claiming ref task for {tg_id}: {e}")
        return {"success": False, "error": "حدث خطأ أثناء استلام مكافأة المهمة"}

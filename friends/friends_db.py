from firebase_admin import firestore
import database

# نسبة عمولة السحب (1.5%) ونسبة أرباح الإحالة من التعدين (10%)
CLAIM_FEE_PERCENT = 0.015
REFERRAL_COMMISSION_PERCENT = 0.10


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
                "name": d.get("first_name") or d.get("name") or "صديق",
                "first_name": d.get("first_name", "صديق"),
                "generated": float(d.get("earned_from_him", 0.0) or 0.0),
                "earned_from_him": float(d.get("earned_from_him", 0.0) or 0.0),
                "upgrades_count": int(d.get("upgrades_count", 0) or 0)
            })
        return friends
    except Exception as e:
        print(f"❌ Error getting user friends for {tg_id}: {e}")
        return []


def add_referral_reward(referrer_id, user_id, mined_amount):
    """إضافة 10% من أرباح تعدين الصديق إلى حساب المُحيل"""
    try:
        if not referrer_id or mined_amount <= 0:
            return False
        
        reward = round(float(mined_amount) * REFERRAL_COMMISSION_PERCENT, 4)
        if reward <= 0:
            return False

        db = database.get_db()
        ref_str = str(referrer_id)
        user_str = str(user_id)

        # 1. تحديث الأرباح المعلقة والإجمالية للمُحيل
        user_ref = db.collection("users").document(ref_str)
        user_ref.update({
            "pending_ref_earnings": firestore.Increment(reward),
            "total_ref_earnings": firestore.Increment(reward),
        })

        # 2. تحديث الرصيد المجمّع من هذا الصديق بالتحديد
        friend_ref = user_ref.collection("friends").document(user_str)
        friend_ref.set({
            "earned_from_him": firestore.Increment(reward)
        }, merge=True)

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
        
        # حساب الأصدقاء المؤهلين للمهام (الذين اشتروا 3 ترقيات أو أكثر)
        eligible_count = sum(1 for f in friends if f.get("upgrades_count", 0) >= 3)
        
        return {
            "balance": float(user_data.get("balance", 0.0) or 0.0),
            "pending_ref_earnings": float(user_data.get("pending_ref_earnings", 0.0) or 0.0),
            "total_ref_earnings": float(user_data.get("total_ref_earnings", 0.0) or 0.0),
            "invited_friends_count": len(friends),
            "eligible_task_friends_count": eligible_count,
            "claimed_ref_tasks": user_data.get("claimed_ref_tasks", []),
            "referral_code": str(tg_id)
        }
    except Exception as e:
        print(f"❌ Error getting friends data for {tg_id}: {e}")
        return {
            "balance": 0.0,
            "pending_ref_earnings": 0.0,
            "total_ref_earnings": 0.0,
            "invited_friends_count": 0,
            "eligible_task_friends_count": 0,
            "claimed_ref_tasks": [],
            "referral_code": str(tg_id)
        }


def claim_ref_earnings_db(tg_id):
    """سحب أرباح الإحالات المعلقة وتحويلها للرصيد الرئيسي مع خصم 1.5% رسوم"""
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
            
            # خصم 1.5% رسوم تحويل
            fee_amount = round(pending * CLAIM_FEE_PERCENT, 4)
            net_amount = round(pending - fee_amount, 4)
            
            current_balance = float(data.get("balance", 0.0) or 0.0)
            new_balance = round(current_balance + net_amount, 4)
            
            transaction.update(ref, {
                "balance": new_balance,
                "pending_ref_earnings": 0.0
            })
            
            return {
                "success": True,
                "claimed_amount": pending,
                "fee_amount": fee_amount,
                "net_amount": net_amount,
                "new_balance": new_balance,
                "message": f"تم سحب {net_amount} ZN بنجاح إلى رصيدك (بعد خصم {fee_amount} ZN رسوم 1.5%)"
            }
        
        transaction = db.transaction()
        return update_in_transaction(transaction, user_ref)
    except Exception as e:
        print(f"❌ Error claiming ref earnings for {tg_id}: {e}")
        return {"success": False, "error": "حدث خطأ أثناء تنفيذ عملية السحب"}


def claim_ref_task_db(tg_id, task_id, reward=0, req_friends=1):
    """استلام مكافأة مهمة دعوة الأصدقاء"""
    try:
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        
        @firestore.transactional
        def update_task_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
            
            user_data = snapshot.to_dict() or {}
            claimed_tasks = user_data.get("claimed_ref_tasks", [])
            
            if str(task_id) in [str(t) for t in claimed_tasks]:
                return {"success": False, "error": "تم استلام مكافأة هذه المهمة من قبل"}
            
            # التحقق من الأصدقاء المؤهلين
            friends = get_user_friends(tg_id)
            eligible_count = sum(1 for f in friends if f.get("upgrades_count", 0) >= 3)
            
            if eligible_count < int(req_friends):
                return {"success": False, "error": f"تحتاج إلى {req_friends} أصدقاء مؤهلين لاستلام هذه المكافأة"}
            
            current_balance = float(user_data.get("balance", 0.0) or 0.0)
            new_balance = round(current_balance + float(reward), 4)
            
            new_claimed = list(claimed_tasks)
            new_claimed.append(str(task_id))
            
            transaction.update(ref, {
                "balance": new_balance,
                "claimed_ref_tasks": new_claimed
            })
            
            return {
                "success": True, 
                "new_balance": new_balance,
                "claimed_ref_tasks": new_claimed,
                "message": f"تم استلام مكافأة {reward} ZN بنجاح"
            }

        transaction = db.transaction()
        return update_task_transaction(transaction, user_ref)
    except Exception as e:
        print(f"❌ Error claiming ref task for {tg_id}: {e}")
        return {"success": False, "error": "حدث خطأ أثناء استلام مكافأة المهمة"}

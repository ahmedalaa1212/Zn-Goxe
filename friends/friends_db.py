import time
from firebase_admin import firestore
import database

# الإعدادات الافتراضية لنظام الأصدقاء
DEFAULT_FRIENDS_CONFIG = {
    "commission_percent": 10.0,       # نسبة أرباح الإحالة العادية (10%)
    "vip_commission_percent": 12.0,   # نسبة أرباح الإحالة لمشتركي VIP (12%)
    "claim_fee_percent": 1.5,         # نسبة عمولة السحب العادية (1.5%)
    "vip_claim_fee_percent": 0.0,     # نسبة عمولة السحب لمشتركي VIP (0%)
    "min_upgrades_for_task": 1,       # عدد الترقيات المطلوب لاحتساب الصديق مؤهل للمهام (ترقية 1 فقط)
    "ref_tasks": {
        "1": {"reqFriends": 1, "reward": 50},
        "2": {"reqFriends": 3, "reward": 200},
        "3": {"reqFriends": 5, "reward": 500},
        "4": {"reqFriends": 10, "reward": 1200},
        "5": {"reqFriends": 20, "reward": 2800},
        "6": {"reqFriends": 35, "reward": 5500},
        "7": {"reqFriends": 50, "reward": 9000},
        "8": {"reqFriends": 75, "reward": 15000},
        "9": {"reqFriends": 100, "reward": 22000},
        "10": {"reqFriends": 150, "reward": 35000}
    }
}

# ذاكرة تخزين مؤقت مع توقيت صلاحية (TTL) لتوفير قراءات الفايربيس
_CONFIG_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 60  # كاش لمدة دقيقة كاملة


def is_user_vip(tg_id, user_data=None):
    """دالة مساعدة للتحقق مما إذا كان المستخدم يمتلك اشتراك VIP نشط"""
    try:
        now_ts = time.time()
        if user_data is None:
            db = database.get_db()
            doc = db.collection("users").document(str(tg_id)).get()
            if not doc.exists:
                return False
            user_data = doc.to_dict() or {}

        # التحقق من خيار vip_active أو تاريخ انتهاء اشتراك الـ VIP
        if user_data.get("vip_active") is True:
            return True

        vip_expires = user_data.get("vip_expires", 0)
        if isinstance(vip_expires, (int, float)) and vip_expires > now_ts:
            return True

        if user_data.get("is_vip") is True:
            return True

        return False
    except Exception as e:
        print(f"⚠️ Error checking VIP status for {tg_id}: {e}")
        return False


def get_friends_config(force_refresh=False):
    """جلب إعدادات نظام الأصدقاء المخصصة من الفايربيس مع Caching حيوي لتوفير الاستهلاك"""
    global _CONFIG_CACHE
    now_ts = time.time()

    if not force_refresh and _CONFIG_CACHE["data"] and (now_ts - _CONFIG_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _CONFIG_CACHE["data"]

    try:
        db = database.get_db()
        config_ref = db.collection("settings").document("friends_config")
        doc = config_ref.get()
        
        if doc.exists:
            data = doc.to_dict() or {}
            config = DEFAULT_FRIENDS_CONFIG.copy()
            config.update(data)
            _CONFIG_CACHE = {"data": config, "timestamp": now_ts}
            return config
        else:
            config_ref.set(DEFAULT_FRIENDS_CONFIG, merge=True)
            _CONFIG_CACHE = {"data": DEFAULT_FRIENDS_CONFIG, "timestamp": now_ts}
            return DEFAULT_FRIENDS_CONFIG
    except Exception as e:
        print(f"⚠️ Error getting friends config from Firestore: {e}")
        return _CONFIG_CACHE["data"] or DEFAULT_FRIENDS_CONFIG


def get_user_friends(tg_id, limit=100):
    """جلب قائمة الأصدقاء والإحالات الخاصة بالمستخدم بطريقة محسّنة وموفرة لقراءات الفايربيس"""
    try:
        db = database.get_db()
        friends_ref = (
            db.collection("users")
            .document(str(tg_id))
            .collection("friends")
            .limit(limit)
        )
        docs = list(friends_ref.stream())
        if not docs:
            return []

        missing_doc_ids = []
        friends_map = {}

        for doc in docs:
            d = doc.to_dict() or {}
            friend_id = str(d.get("tg_id", doc.id))
            
            if "upgrades_count" in d and ("first_name" in d or "name" in d):
                friends_map[friend_id] = {
                    "tg_id": friend_id,
                    "name": d.get("first_name") or d.get("name") or "صديق",
                    "first_name": d.get("first_name") or d.get("name") or "صديق",
                    "generated": float(d.get("earned_from_him", 0.0) or 0.0),
                    "earned_from_him": float(d.get("earned_from_him", 0.0) or 0.0),
                    "upgrades_count": int(d.get("upgrades_count", 0))
                }
            else:
                missing_doc_ids.append(friend_id)

        friend_user_docs = {}
        if missing_doc_ids:
            try:
                friend_refs = [db.collection("users").document(fid) for fid in missing_doc_ids]
                fetched_docs = db.get_all(friend_refs)
                for u_doc in fetched_docs:
                    if u_doc.exists:
                        friend_user_docs[u_doc.id] = u_doc.to_dict() or {}
            except Exception as fetch_err:
                print(f"⚠️ Warning fetching friend user docs: {fetch_err}")

        friends = []
        for doc in docs:
            d = doc.to_dict() or {}
            friend_id = str(d.get("tg_id", doc.id))

            if friend_id in friends_map:
                friends.append(friends_map[friend_id])
            else:
                real_user = friend_user_docs.get(friend_id, {})
                upgrades_dict = real_user.get("upgrades", {})
                calc_upgrades = 0
                if isinstance(upgrades_dict, dict):
                    calc_upgrades = sum(int(v) for v in upgrades_dict.values() if isinstance(v, (int, float)))

                real_upgrades_count = int(
                    real_user.get("upgrades_count")
                    if real_user.get("upgrades_count") is not None
                    else (calc_upgrades or d.get("upgrades_count", 0) or 0)
                )

                friends.append({
                    "tg_id": friend_id,
                    "name": real_user.get("first_name") or real_user.get("name") or d.get("first_name") or d.get("name") or "صديق",
                    "first_name": real_user.get("first_name") or d.get("first_name", "صديق"),
                    "generated": float(d.get("earned_from_him", 0.0) or 0.0),
                    "earned_from_him": float(d.get("earned_from_him", 0.0) or 0.0),
                    "upgrades_count": real_upgrades_count
                })
        return friends
    except Exception as e:
        print(f"❌ Error getting user friends for {tg_id}: {e}")
        return []


def add_referral_reward(referrer_id, user_id, mined_amount, user_upgrades_count=None, user_name=None):
    """إضافة أرباح التعدين وتحديث بيانات مستند الصديق تلقائياً مع مراعاة نسبة VIP (12%)"""
    try:
        if not referrer_id or mined_amount <= 0:
            return False
        
        config = get_friends_config()
        db = database.get_db()
        ref_str = str(referrer_id)
        user_str = str(user_id)

        # التحقق مما إذا كان المُحيل يملك اشتراك VIP
        referrer_ref = db.collection("users").document(ref_str)
        ref_doc = referrer_ref.get()
        referrer_data = ref_doc.to_dict() if ref_doc.exists else {}

        if is_user_vip(ref_str, referrer_data):
            comm_percent = float(config.get("vip_commission_percent", 12.0)) / 100.0
        else:
            comm_percent = float(config.get("commission_percent", 10.0)) / 100.0

        reward = round(float(mined_amount) * comm_percent, 6)
        if reward <= 0:
            return False

        # 1. تحديث الأرباح المعلقة والإجمالية للمُحيل بأمان
        referrer_ref.set({
            "pending_ref_earnings": firestore.Increment(reward),
            "total_ref_earnings": firestore.Increment(reward),
        }, merge=True)

        # 2. تحديث الرصيد المجمّع وتفاصيل الصديق داخل المجموعة الفرعية
        friend_data = {
            "earned_from_him": firestore.Increment(reward),
            "tg_id": user_str
        }
        if user_name:
            friend_data["first_name"] = user_name
            friend_data["name"] = user_name
        if user_upgrades_count is not None:
            friend_data["upgrades_count"] = int(user_upgrades_count)

        friend_ref = referrer_ref.collection("friends").document(user_str)
        friend_ref.set(friend_data, merge=True)

        return True
    except Exception as e:
        print(f"❌ Error adding referral reward for {referrer_id}: {e}")
        return False


def get_friends_list_db(tg_id):
    """جلب قائمة الأصدقاء للاستخدام في API الأصدقاء"""
    return get_user_friends(tg_id)


def get_friends_data_db(tg_id):
    """جلب ملخص إحصائيات الأصدقاء والمكافآت وإعدادات قائمة الأصدقاء ديناميكياً مع حالة VIP"""
    try:
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        doc = user_ref.get()
        
        user_data = doc.to_dict() if doc.exists else {}
        friends = get_user_friends(tg_id)
        config = get_friends_config()
        
        min_upgrades = int(config.get("min_upgrades_for_task", 1))
        
        # حساب الأصدقاء المؤهلين للمهام بناءً على شرط الترقية (1 ترقية فقط)
        eligible_count = sum(1 for f in friends if f.get("upgrades_count", 0) >= min_upgrades)
        
        vip_status = is_user_vip(tg_id, user_data)
        effective_commission = float(config.get("vip_commission_percent", 12.0)) if vip_status else float(config.get("commission_percent", 10.0))
        effective_claim_fee = float(config.get("vip_claim_fee_percent", 0.0)) if vip_status else float(config.get("claim_fee_percent", 1.5))

        return {
            "balance": round(float(user_data.get("balance", 0.0) or 0.0), 6),
            "pending_ref_earnings": round(float(user_data.get("pending_ref_earnings", 0.0) or 0.0), 6),
            "total_ref_earnings": round(float(user_data.get("total_ref_earnings", 0.0) or 0.0), 6),
            "invited_friends_count": len(friends),
            "eligible_task_friends_count": eligible_count,
            "claimed_ref_tasks": user_data.get("claimed_ref_tasks", []),
            "referral_code": str(tg_id),
            "is_vip": vip_status,
            "effective_commission": effective_commission,
            "effective_claim_fee": effective_claim_fee,
            "friends_config": config
        }
    except Exception as e:
        print(f"❌ Error getting friends data for {tg_id}: {e}")
        config = get_friends_config()
        return {
            "balance": 0.0,
            "pending_ref_earnings": 0.0,
            "total_ref_earnings": 0.0,
            "invited_friends_count": 0,
            "eligible_task_friends_count": 0,
            "claimed_ref_tasks": [],
            "referral_code": str(tg_id),
            "is_vip": False,
            "effective_commission": 10.0,
            "effective_claim_fee": 1.5,
            "friends_config": config
        }


def claim_ref_earnings_db(tg_id):
    """سحب أرباح الإحالات المعلقة وتحويلها للرصيد الرئيسي مع خصم الرسوم (0% لمشتركي VIP و 1.5% للعاديين)"""
    try:
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        config = get_friends_config()
        
        @firestore.transactional
        def update_in_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
            
            data = snapshot.to_dict() or {}
            pending = float(data.get("pending_ref_earnings", 0.0) or 0.0)
            
            if pending <= 0:
                return {"success": False, "error": "لا توجد أرباح معلقة للسحب"}
            
            # التحقق من حالة الـ VIP لتحديد نسبة الخصم
            vip_status = is_user_vip(tg_id, data)
            claim_fee_percent = float(config.get("vip_claim_fee_percent", 0.0)) if vip_status else float(config.get("claim_fee_percent", 1.5))
            fee_rate = claim_fee_percent / 100.0
            
            fee_amount = round(pending * fee_rate, 6)
            net_amount = round(pending - fee_amount, 6)
            
            current_balance = float(data.get("balance", 0.0) or 0.0)
            new_balance = round(current_balance + net_amount, 6)
            
            transaction.update(ref, {
                "balance": new_balance,
                "pending_ref_earnings": 0.0
            })
            
            fee_msg = "معفي من الرسوم (0% VIP)" if vip_status else f"خصم {fee_amount} ZN رسوم ({claim_fee_percent}%)"
            return {
                "success": True,
                "claimed_amount": pending,
                "fee_amount": fee_amount,
                "net_amount": net_amount,
                "new_balance": new_balance,
                "message": f"تم سحب {net_amount} ZN بنجاح إلى رصيدك ({fee_msg})"
            }
        
        transaction = db.transaction()
        return update_in_transaction(transaction, user_ref)
    except Exception as e:
        print(f"❌ Error claiming ref earnings for {tg_id}: {e}")
        return {"success": False, "error": "حدث خطأ أثناء تنفيذ عملية السحب"}


def claim_ref_task_db(tg_id, task_id, reward=0, req_friends=1):
    """استلام مكافأة مهمة دعوة الأصدقاء والتحقق منها بداخل معاملة Firestore آمنة آلياً"""
    try:
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        
        config = get_friends_config()
        min_upgrades = int(config.get("min_upgrades_for_task", 1))
        ref_tasks = config.get("ref_tasks", {})
        
        task_info = ref_tasks.get(str(task_id))
        if task_info:
            actual_req_friends = int(task_info.get("reqFriends", req_friends))
            actual_reward = float(task_info.get("reward", reward))
        else:
            actual_req_friends = int(req_friends)
            actual_reward = float(reward)

        # تجهيز قائمة الأصدقاء وحساب المؤهلين (ترقية 1 على الأقل)
        friends = get_user_friends(tg_id)
        eligible_count = sum(1 for f in friends if f.get("upgrades_count", 0) >= min_upgrades)

        if eligible_count < actual_req_friends:
            return {"success": False, "error": f"تحتاج إلى {actual_req_friends} أصدقاء مؤهلين لاستلام هذه المكافأة"}

        @firestore.transactional
        def update_task_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return {"success": False, "error": "المستخدم غير موجود"}
            
            user_data = snapshot.to_dict() or {}
            claimed_tasks = user_data.get("claimed_ref_tasks", [])
            
            if str(task_id) in [str(t) for t in claimed_tasks]:
                return {"success": False, "error": "تم استلام مكافأة هذه المهمة من قبل"}
            
            current_balance = float(user_data.get("balance", 0.0) or 0.0)
            new_balance = round(current_balance + actual_reward, 6)
            
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
                "message": f"تم استلام مكافأة {actual_reward} ZN بنجاح"
            }

        transaction = db.transaction()
        return update_task_transaction(transaction, user_ref)
    except Exception as e:
        print(f"❌ Error claiming ref task for {tg_id}: {e}")
        return {"success": False, "error": "حدث خطأ أثناء استلام مكافأة المهمة"}

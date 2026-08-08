from datetime import datetime, timezone
from google.cloud import firestore
from database import get_db

# ==================== الإعدادات الافتراضية بنظام الأصدقاء ====================
DEFAULT_FRIENDS_CONFIG = {
    "commission_percent": 10.0,
    "claim_fee_percent": 1.5,
    "min_upgrades_for_task": 3,
    "ref_tasks": {
        "1": {"reqFriends": 1, "reward": 3000.0},
        "2": {"reqFriends": 5, "reward": 18000.0},
        "3": {"reqFriends": 10, "reward": 40000.0},
        "4": {"reqFriends": 25, "reward": 110000.0},
        "5": {"reqFriends": 50, "reward": 250000.0},
        "6": {"reqFriends": 100, "reward": 600000.0},
        "7": {"reqFriends": 500, "reward": 3500000.0}
    }
}


# ==================== الوظائف المساعدة لقراءة الإعدادات ====================

def get_friends_config():
    """جلب إعدادات نظام الأصدقاء والمكافآت من الفايربيس بشكل ديناميكي"""
    db = get_db()
    try:
        doc = db.collection('settings').document('game_settings').get()
        if doc.exists:
            settings = doc.to_dict() or {}
            config = settings.get('friends_config')
            if isinstance(config, dict):
                # دمج القواعد مع الافتراضية لضمان عدم انقطاع أي حقل في حال الإضافة المستقبليّة
                merged_config = DEFAULT_FRIENDS_CONFIG.copy()
                merged_config.update(config)
                return merged_config
    except Exception as e:
        print(f"⚠️ خطأ أثناء جلب إعدادات الأصدقاء من الفايربيس: {e}")
    return DEFAULT_FRIENDS_CONFIG


def get_user_upgrades_count(user_data):
    """حساب إجمالي عدد الترقيات التي اشتراها اللاعب لتحديد أهليته لمهام الإحالة"""
    if not isinstance(user_data, dict):
        return 0
    upgrades = user_data.get('upgrades', {})
    total = 0
    if isinstance(upgrades, dict):
        if 'upgrades_count' in upgrades:
            try:
                return int(upgrades['upgrades_count'])
            except (ValueError, TypeError):
                pass
        for v in upgrades.values():
            try:
                total += int(v)
            except (ValueError, TypeError):
                pass
    elif isinstance(upgrades, (int, float)):
        total = int(upgrades)
    return total


# ==================== دوال قاعدة البيانات لنظام الأصدقاء ====================

def add_referral_commission_db(user_id, claimed_amount):
    """
    إضافة عمولة التعدين للمُحيل (تُستدعى عند تجميع أرباح المزرعة)
    """
    try:
        if not user_id or float(claimed_amount) <= 0:
            return False

        user_id_str = str(user_id)
        db = get_db()
        user_ref = db.collection('users').document(user_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return False

        user_data = user_doc.to_dict() or {}
        referrer_id = user_data.get('referred_by')

        if not referrer_id or str(referrer_id).strip() in ["", "null", "None"]:
            return False

        referrer_id_str = str(referrer_id)
        config = get_friends_config()
        commission_percent = float(config.get('commission_percent', 10.0))
        commission = round((float(claimed_amount) * commission_percent) / 100.0, 4)

        if commission <= 0:
            return False

        ref_user_ref = db.collection('users').document(referrer_id_str)
        ref_user_doc = ref_user_ref.get()

        if not ref_user_doc.exists:
            return False

        # تحديث أرباح الداعي عبر update وتحديث الحقول المحددة فقط
        ref_user_ref.update({
            'pending_ref_earnings': firestore.Increment(commission),
            'total_ref_earnings': firestore.Increment(commission)
        })

        # تحديث السجل داخل مجموعة الأصدقاء الفرعية
        sub_friend_ref = ref_user_ref.collection('friends').document(user_id_str)
        sub_friend_doc = sub_friend_ref.get()
        user_display_name = user_data.get('first_name') or user_data.get('name') or 'صديق'

        if sub_friend_doc.exists:
            sub_friend_ref.update({
                'earned_from_him': firestore.Increment(commission),
                'name': user_display_name
            })
        else:
            sub_friend_ref.set({
                'earned_from_him': commission,
                'name': user_display_name,
                'joined_at': firestore.SERVER_TIMESTAMP
            }, merge=True)

        return True

    except Exception as e:
        print(f"❌ خطأ أثناء إضافة عمولة الإحالة: {e}")
        return False


def get_friends_data_db(user_id_str):
    """جلب ملخص بيانات نظام الأصدقاء والمكافآت للمستخدم"""
    db = get_db()
    user_ref = db.collection('users').document(user_id_str)
    user_doc = user_ref.get()
    friends_config = get_friends_config()

    if not user_doc.exists:
        user_data = {}
    else:
        user_data = user_doc.to_dict() or {}

    # قراءة الحقول مع قيم افتراضية آمنة
    balance = round(float(user_data.get('balance', 0.0)), 2)
    pending_earnings = round(float(user_data.get('pending_ref_earnings', 0.0)), 2)
    total_earnings = round(float(user_data.get('total_ref_earnings', 0.0)), 2)
    claimed_tasks = user_data.get('claimed_ref_tasks', [])
    if not isinstance(claimed_tasks, list):
        claimed_tasks = []

    # التأكد من كتابة الحقول المفقودة فقط إذا لم تكن موجودة
    auto_updates = {}
    if 'pending_ref_earnings' not in user_data:
        auto_updates['pending_ref_earnings'] = pending_earnings
    if 'total_ref_earnings' not in user_data:
        auto_updates['total_ref_earnings'] = total_earnings
    if auto_updates and user_doc.exists:
        user_ref.update(auto_updates)

    # حساب الأصدقاء المؤهلين
    min_upgrades = int(friends_config.get('min_upgrades_for_task', 3))
    friends_query = db.collection('users').where('referred_by', '==', user_id_str).stream()

    total_friends_count = 0
    eligible_task_friends_count = 0

    for doc in friends_query:
        total_friends_count += 1
        f_data = doc.to_dict() or {}
        if get_user_upgrades_count(f_data) >= min_upgrades:
            eligible_task_friends_count += 1

    return {
        "player": {
            "balance": balance,
            "pending_ref_earnings": pending_earnings,
            "total_ref_earnings": total_earnings,
            "invited_friends_count": total_friends_count,
            "eligible_task_friends_count": eligible_task_friends_count,
            "claimed_ref_tasks": claimed_tasks
        },
        "friends_config": friends_config
    }


def get_friends_list_db(user_id_str):
    """جلب قائمة الأصدقاء المفصلة مع الأرباح المجمعة وعدد الترقيات لكل صديق"""
    db = get_db()
    referred_users = {}

    # 1. جلب المستخدمين المسجلين برابط اللاعب
    users_query = db.collection('users').where('referred_by', '==', user_id_str).stream()
    for doc in users_query:
        referred_users[doc.id] = doc.to_dict() or {}

    # 2. جلب البيانات من المجموعات الفرعية (friends)
    sub_friends = {}
    sub_query = db.collection('users').document(user_id_str).collection('friends').stream()
    for doc in sub_query:
        sub_friends[doc.id] = doc.to_dict() or {}

    # 3. لدعم السجلات القديمة (referrals) إن وجدت
    old_ref_query = db.collection('users').document(user_id_str).collection('referrals').stream()
    for doc in old_ref_query:
        f_id = doc.id
        old_d = doc.to_dict() or {}
        if f_id not in sub_friends:
            sub_friends[f_id] = old_d
        else:
            current_val = float(sub_friends[f_id].get('earned_from_him', 0.0))
            old_val = float(old_d.get('earned_from_friend') or old_d.get('earned_amount') or 0.0)
            sub_friends[f_id]['earned_from_him'] = current_val + old_val

    friends_list = []
    all_friend_ids = set(referred_users.keys()).union(set(sub_friends.keys()))

    for f_id in all_friend_ids:
        main_data = referred_users.get(f_id, {})
        sub_data = sub_friends.get(f_id, {})
        total_upgrades = get_user_upgrades_count(main_data)

        f_name = (main_data.get('first_name') or
                  main_data.get('name') or
                  sub_data.get('first_name') or
                  sub_data.get('name') or
                  'صديق')

        earned_val = (sub_data.get('earned_from_him') if sub_data.get('earned_from_him') is not None else
                      sub_data.get('earned_from_friend') if sub_data.get('earned_from_friend') is not None else
                      main_data.get('ref_generated_amount', 0.0))

        try:
            generated_amount = round(float(earned_val), 2)
        except (ValueError, TypeError):
            generated_amount = 0.0

        friends_list.append({
            "id": f_id,
            "name": f_name,
            "upgrades_count": total_upgrades,
            "generated": generated_amount
        })

    friends_list.sort(key=lambda x: x['generated'], reverse=True)
    return friends_list


def claim_ref_earnings_db(user_id_str):
    """سحب أرباح الأصدقاء المعلقة إلى الرصيد الرئيسي مع خصم رسوم التحويل"""
    db = get_db()
    user_ref = db.collection('users').document(user_id_str)
    friends_config = get_friends_config()
    fee_percentage = float(friends_config.get('claim_fee_percent', 1.5)) / 100.0

    @firestore.transactional
    def run_claim_earnings_transaction(transaction, u_ref):
        snapshot = u_ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"success": False, "error": "حساب المستخدم غير موجود"}

        u_data = snapshot.to_dict() or {}
        pending_earnings = float(u_data.get('pending_ref_earnings', 0.0))
        current_balance = float(u_data.get('balance', 0.0))

        if pending_earnings <= 0:
            return {"success": False, "error": "لا توجد أرباح معلقة للسحب"}

        net_amount = pending_earnings * (1.0 - fee_percentage)
        new_balance = round(current_balance + net_amount, 2)

        # تحديث الرصيد وتصفير الأرباح المعلقة باستخدام update فقط
        transaction.update(u_ref, {
            'balance': new_balance,
            'pending_ref_earnings': 0.0
        })

        return {
            "success": True,
            "new_balance": new_balance,
            "net_amount": round(net_amount, 2),
            "pending_ref_earnings": 0.0
        }

    transaction = db.transaction()
    return run_claim_earnings_transaction(transaction, user_ref)


def claim_ref_task_db(user_id_str, task_id):
    """استلام مكافأة إنجاز دعوة الأصدقاء (المهام)"""
    db = get_db()
    task_id_str = str(task_id)
    friends_config = get_friends_config()
    ref_tasks = friends_config.get('ref_tasks', {})

    task_config = ref_tasks.get(task_id_str) or ref_tasks.get(int(task_id_str) if task_id_str.isdigit() else task_id_str)
    if not task_config:
        return {"success": False, "error": "المهمة غير موجودة في الإعدادات"}

    req_friends = int(task_config.get('reqFriends', 1))
    task_reward = float(task_config.get('reward', 0.0))
    min_upgrades = int(friends_config.get('min_upgrades_for_task', 3))

    # التحقق من عدد الأصدقاء المؤهلين
    friends_query = db.collection('users').where('referred_by', '==', user_id_str).stream()
    eligible_friends = 0
    for doc in friends_query:
        if get_user_upgrades_count(doc.to_dict() or {}) >= min_upgrades:
            eligible_friends += 1

    if eligible_friends < req_friends:
        return {
            "success": False,
            "error": f"يلزم {req_friends} أصدقاء قاموا بشراء {min_upgrades} ترقيات على الأقل!"
        }

    user_ref = db.collection('users').document(user_id_str)

    @firestore.transactional
    def run_claim_task_transaction(transaction, u_ref):
        snapshot = u_ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"success": False, "error": "حساب المستخدم غير موجود"}

        u_data = snapshot.to_dict() or {}
        claimed_tasks = u_data.get('claimed_ref_tasks', [])
        if not isinstance(claimed_tasks, list):
            claimed_tasks = []

        task_id_parsed = int(task_id_str) if task_id_str.isdigit() else task_id_str
        if task_id_str in claimed_tasks or task_id_parsed in claimed_tasks:
            return {"success": False, "error": "تم استلام هذه المكافأة مسبقاً"}

        current_balance = float(u_data.get('balance', 0.0))
        new_balance = round(current_balance + task_reward, 2)
        claimed_tasks.append(task_id_parsed)

        transaction.update(u_ref, {
            'balance': new_balance,
            'claimed_ref_tasks': claimed_tasks
        })

        return {
            "success": True,
            "new_balance": new_balance,
            "claimed_ref_tasks": claimed_tasks
        }

    transaction = db.transaction()
    return run_claim_task_transaction(transaction, user_ref)

# settings/settings_db.py
import logging
from google.cloud import firestore
import database

logger = logging.getLogger(__name__)

def get_db():
    """الحصول على كائن الاتصال بقاعدة البيانات Firestore"""
    if database.db is None:
        return database.initialize_firebase()
    return database.db

def get_user_settings_stats(uid: str) -> dict:
    """
    جلب إحصائيات مستويات المزرعة والمخازن والرصيد للمستخدم بصورة محسنة وآمنة.
    """
    default_stats = {"farm_levels_count": 0, "storage_levels_count": 0, "balance": 0}
    if not uid:
        return default_stats

    try:
        db = get_db()
        if not db:
            logger.error("Database connection failed in settings/settings_db.py")
            return default_stats

        user_doc = db.collection('users').document(str(uid)).get()
        if not user_doc.exists:
            return default_stats

        data = user_doc.to_dict() or {}
        
        # حساب إجمالي مستويات التعدين عبر الـ 9 مستويات
        farm_levels_count = 0
        upgrades = data.get('upgrades', {})
        if isinstance(upgrades, dict):
            for i in range(1, 10):
                lvl_val = upgrades.get(f'lvl{i}', 0)
                try:
                    farm_levels_count += max(0, int(lvl_val))
                except (ValueError, TypeError):
                    pass

        # حساب مستويات المخزن
        storage_levels_count = 0
        storage_val = data.get('storage_level', 0)
        try:
            storage_levels_count = max(0, int(storage_val))
        except (ValueError, TypeError):
            pass

        # حماية الرصيد وتنسيقه
        balance = 0
        raw_balance = data.get('balance', 0)
        try:
            balance = float(raw_balance) if isinstance(raw_balance, (int, float, str)) else 0
            if balance.is_integer():
                balance = int(balance)
        except (ValueError, TypeError):
            balance = 0

        return {
            "farm_levels_count": farm_levels_count,
            "storage_levels_count": storage_levels_count,
            "balance": balance
        }

    except Exception as e:
        logger.error(f"Error fetching settings stats for user {uid}: {e}")
        return default_stats


def get_top_mining_leaderboard(limit: int = 10) -> list:
    """
    جلب أفضل 10 مستخدمين حصدوا أكبر قدر من نقاط التعدين فقط بصورة آمنة ومضمونة.
    تستعلم حسب mined_points / mining_points مع دعم التراجع التلقائي لمنع إرجاع قائمة فارغة.
    """
    default_leaderboard = []
    try:
        db = get_db()
        if not db:
            logger.error("Database connection failed in get_top_mining_leaderboard")
            return default_leaderboard

        users_ref = db.collection('users')
        docs = []

        # 1. محاولة الجلب حسب حقول نقاط التعدين المحتملة بترتيب تنازلي
        order_fields = ['mined_points', 'mining_points', 'total_mined', 'mined_total', 'farm_mined', 'balance']
        
        for field in order_fields:
            try:
                query_docs = list(users_ref.order_by(field, direction=firestore.Query.DESCENDING).limit(limit * 2).get())
                if query_docs:
                    docs = query_docs
                    break
            except Exception as q_err:
                logger.warning(f"Firestore order_by('{field}') query failed or unindexed: {q_err}")

        # 2. إذا فشلت الاستعلامات المفهرسة، جلب قائمة مستخدمين بديلة ومسحها
        if not docs:
            try:
                docs = list(users_ref.limit(100).get())
            except Exception as fetch_err:
                logger.error(f"Failed to fetch users fallback limit(100): {fetch_err}")

        leaderboard = []
        for doc in docs:
            data = doc.to_dict() or {}
            
            # جلب نقاط التعدين مع فحص جميع الأسماء الممكنة للحقل (mined_points, mining_points, total_mined, إلخ)
            raw_mined = None
            for key in ['mined_points', 'mining_points', 'total_mined', 'mined_total', 'farm_mined', 'balance']:
                if key in data and data[key] is not None:
                    raw_mined = data[key]
                    break

            if raw_mined is None:
                raw_mined = 0.0

            try:
                mined_pts = float(raw_mined)
            except (ValueError, TypeError):
                mined_pts = 0.0

            first_name = str(data.get('first_name', '')).strip()
            last_name = str(data.get('last_name', '')).strip()
            username = str(data.get('username', '')).strip()

            if first_name and last_name:
                full_name = f"{first_name} {last_name}"
            elif first_name:
                full_name = first_name
            elif username:
                full_name = username
            else:
                full_name = f"لاعب #{str(doc.id)[-4:]}"

            leaderboard.append({
                "uid": str(doc.id),
                "first_name": full_name,
                "username": username,
                "mining_points": round(mined_pts, 2),
                "mined_points": round(mined_pts, 2)
            })

        # إعادة الفرز في الذاكرة للضمان تنازلياً وإرجاع أول N متصدرين
        leaderboard.sort(key=lambda x: x['mined_points'], reverse=True)
        return leaderboard[:limit]

    except Exception as e:
        logger.error(f"Error fetching mining leaderboard: {e}")
        return default_leaderboard


def redeem_promo_code(uid: str, code_input: str) -> dict:
    """
    تفعيل كود الهدايا والمكافآت مع حماية كاملة ضد التكرار والتلاعب وسباق الاستعلامات (Race Conditions)
    """
    if not uid or not code_input:
        return {"success": False, "message": "⚠️ البيانات المدخلة غير مكتملة."}

    clean_code = str(code_input).strip().upper()
    if not clean_code or len(clean_code) > 30:
        return {"success": False, "message": "⚠️ صيغة الكود غير صالحة."}

    db = get_db()
    if not db:
        logger.error("Database connection failed in redeem_promo_code")
        return {"success": False, "message": "❌ خطأ في الاتصال بقاعدة البيانات."}

    code_ref = db.collection('promo_codes').document(clean_code)
    user_ref = db.collection('users').document(str(uid))

    @firestore.transactional
    def _execute_redeem(transaction, code_ref_doc, user_ref_doc):
        code_doc = code_ref_doc.get(transaction=transaction)
        if not code_doc.exists:
            return {"success": False, "message": "❌ هذا الكود غير صحيح أو غير موجود!"}

        code_data = code_doc.to_dict() or {}
        coins = float(code_data.get('coins', 0))
        max_uses = int(code_data.get('max_uses', 1))
        used_count = int(code_data.get('used_count', 0))
        used_by = code_data.get('used_by', [])

        if not isinstance(used_by, list):
            used_by = []

        if coins <= 0:
            return {"success": False, "message": "⚠️ هذا الكود لا يحتوي على مكافأة صالحة."}

        if used_count >= max_uses:
            return {"success": False, "message": "⚠️ للأسف، اكتمل الحد الأقصى لاستخدام هذا الكود!"}

        if str(uid) in [str(u) for u in used_by]:
            return {"success": False, "message": "⚠️ لقد قمت باستخدام هذا الكود من قبل!"}

        user_doc = user_ref_doc.get(transaction=transaction)
        if not user_doc.exists:
            return {"success": False, "message": "❌ لم يتم العثور على حساب المستخدم."}

        # 1. تحديث بيانات الكود برفع عدد الاستخدامات وإضافة ID المستخدم القائم بالتفعيل
        transaction.update(code_ref_doc, {
            'used_count': firestore.Increment(1),
            'used_by': firestore.ArrayUnion([str(uid)])
        })

        # 2. زيادة رصيد المستخدم بأمان
        transaction.update(user_ref_doc, {
            'balance': firestore.Increment(coins),
            'zn_balance': firestore.Increment(coins),
            'total_earned': firestore.Increment(coins)
        })

        return {
            "success": True,
            "message": f"🎉 مبروك! تم إضافة {coins:,.0f} ZN إلى رصيدك بنجاح.",
            "coins": coins
        }

    transaction = db.transaction()
    try:
        return _execute_redeem(transaction, code_ref, user_ref)
    except Exception as e:
        logger.error(f"Error executing redeem_promo_code transaction for user {uid}, code {clean_code}: {e}")
        return {"success": False, "message": "❌ حدث خطأ أثناء معالجة الكود، يرجى المحاولة لاحقاً."}

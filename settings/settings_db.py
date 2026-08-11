# settings/settings_db.py
import logging
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

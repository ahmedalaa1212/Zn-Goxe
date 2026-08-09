import time
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from database import get_db

# ==================== الإعدادات الافتراضية الخاصة بالمزرعة ====================
DEFAULT_FARM_SETTINGS = {
    "daily_rewards": [
        100, 150, 200, 250, 300, 350, 400, 450, 500, 550,
        600, 600, 650, 650, 700, 700, 750, 750, 800, 800,
        850, 850, 900, 900, 950, 950, 1000, 1000, 1100, 1250
    ],
    "mining_config": {
        "daily_boost_reward": 0.5,        # زيادة السرعة اليومية
        "daily_boost_target_speed": 15.0, # الحد الأقصى لسرعة التعزيز
        "daily_boost_coin_reward": 50.0,  # قيمة المكافأة بالعملات بعد الوصول للحد الأقصى
        "cooldown_seconds": 15
    },
    "storage_capacities": {
        "0": 100.0, "1": 300.0, "2": 800.0, "3": 2000.0, "4": 5000.0,
        "5": 12000.0, "6": 28000.0, "7": 65000.0, "8": 150000.0, "9": 350000.0, "10": 800000.0
    },
    "upgrade_config": {
        "1": {"base_cost": 3500.0, "rate_bonus": 5.0, "price": 3500.0, "rate": 5.0},
        "2": {"base_cost": 11500.0, "rate_bonus": 15.0, "price": 11500.0, "rate": 15.0},
        "3": {"base_cost": 28000.0, "rate_bonus": 35.0, "price": 28000.0, "rate": 35.0},
        "4": {"base_cost": 68000.0, "rate_bonus": 80.0, "price": 68000.0, "rate": 80.0},
        "5": {"base_cost": 165000.0, "rate_bonus": 180.0, "price": 165000.0, "rate": 180.0},
        "6": {"base_cost": 390000.0, "rate_bonus": 400.0, "price": 390000.0, "rate": 400.0},
        "7": {"base_cost": 950000.0, "rate_bonus": 900.0, "price": 950000.0, "rate": 900.0},
        "8": {"base_cost": 2300000.0, "rate_bonus": 2000.0, "price": 2300000.0, "rate": 2000.0},
        "9": {"base_cost": 5500000.0, "rate_bonus": 4500.0, "price": 5500000.0, "rate": 4500.0}
    }
}

# ذاكرة مؤقتة لتقليل استهلاك قراءات الفايربيس (Cache)
_SETTINGS_CACHE = None
_SETTINGS_CACHE_TIME = 0
CACHE_TTL = 60  # كاش لمدة 60 ثانية


def get_game_settings(force_refresh=False):
    """جلب إعدادات المزرعة من Firestore مع تخزين مؤقت لتقليل القراءات"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    now = time.time()

    if not force_refresh and _SETTINGS_CACHE is not None and (now - _SETTINGS_CACHE_TIME < CACHE_TTL):
        return _SETTINGS_CACHE

    db = get_db()
    try:
        # 1. البحث أولاً في مستند المزرعة الخاص farm_settings
        doc = db.collection('settings').document('farm_settings').get()
        if doc.exists:
            _SETTINGS_CACHE = doc.to_dict() or DEFAULT_FARM_SETTINGS
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE

        # 2. إن لم يوجد، البحث في game_settings العام
        doc_alt = db.collection('settings').document('game_settings').get()
        if doc_alt.exists:
            _SETTINGS_CACHE = doc_alt.to_dict() or DEFAULT_FARM_SETTINGS
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
    except Exception as e:
        print(f"⚠️ خطأ أثناء جلب إعدادات المزرعة: {e}")

    _SETTINGS_CACHE = DEFAULT_FARM_SETTINGS
    _SETTINGS_CACHE_TIME = now
    return _SETTINGS_CACHE


def parse_daily_rewards(rewards_data):
    """تحليل قائمة المكافآت اليومية (30 يوم)"""
    if isinstance(rewards_data, list) and len(rewards_data) > 0:
        return [int(x) for x in rewards_data]
    if isinstance(rewards_data, dict):
        res = []
        for i in range(1, 31):
            val = rewards_data.get(f"day_{i}") or rewards_data.get(str(i)) or DEFAULT_FARM_SETTINGS["daily_rewards"][i-1]
            res.append(int(val))
        return res
    return DEFAULT_FARM_SETTINGS["daily_rewards"]


def get_base_storage_capacity(storage_level, settings=None):
    """حساب السعة التخزينية الأساسية للمخزن"""
    if not settings:
        settings = DEFAULT_FARM_SETTINGS
    try:
        lvl = int(storage_level)
    except (ValueError, TypeError):
        lvl = 0
    lvl = max(0, min(lvl, 10))

    caps = settings.get("storage_capacities") or settings.get("storage_config") or DEFAULT_FARM_SETTINGS["storage_capacities"]

    if str(lvl) in caps and isinstance(caps[str(lvl)], dict):
        return float(caps[str(lvl)].get("capacity", 100.0))

    val = caps.get(str(lvl)) or caps.get(lvl) or 100.0
    return float(val)


def calculate_user_max_cap(user_data, settings=None):
    """حساب أقصى سعة للمخزن المؤقت للمستخدم"""
    if not settings:
        settings = DEFAULT_FARM_SETTINGS
    stg_lvl = user_data.get("storage_level", 0)
    base_cap = get_base_storage_capacity(stg_lvl, settings)
    extra_cap = float(user_data.get("extra_storage", 0.0))
    return round(base_cap + extra_cap, 2)


def calculate_accrued_mined(user_data, now_dt, max_cap):
    """حساب الكمية المعدنة الحالية داخل المخزن المؤقت"""
    last_claim_str = user_data.get("last_claim_time")
    hourly_rate = float(user_data.get("hourly_rate", 0.0))
    if not last_claim_str or hourly_rate <= 0:
        return 0.0
    try:
        last_claim = datetime.fromisoformat(str(last_claim_str).replace('Z', '+00:00'))
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)
        seconds_passed = max(0.0, (now_dt - last_claim).total_seconds())
        mined = (hourly_rate / 3600.0) * seconds_passed
        return round(min(mined, max_cap), 2)
    except Exception:
        return 0.0


# ==================== عمليات قاعدة البيانات الخاصة بالمزرعة ====================

def get_or_create_user_farm_data(user_id_str):
    """جلب وتجهيز كافة بيانات المستخدم المزرعية مع التحديث التلقائي للحقول"""
    db = get_db()
    user_ref = db.collection('users').document(user_id_str)
    user_doc = user_ref.get()
    now = datetime.now(timezone.utc)
    game_settings = get_game_settings()

    if not user_doc.exists:
        user_data = {
            "tg_id": user_id_str,
            "telegram_id": user_id_str,
            "balance": 0.00,
            "ad_balance": 0.00,
            "usd_balance": 0.00,
            "hourly_rate": 0.00,
            "daily_boost_rate": 0.00,
            "unclaimed": 0.00,
            "storage_level": 0,
            "extra_storage": 0.00,
            "max_cap": get_base_storage_capacity(0, game_settings),
            "daily_day": 1,
            "daily_streak": 1,
            "last_claim_time": now.isoformat(),
            "last_daily_claim_date": None,
            "last_boost_date": None,
            "ads_watched": 0,
            "upgrades": {},
            "upgrades_count": 0,
            "referred_by": None,
            "pending_ref_earnings": 0.00,
            "total_ref_earnings": 0.00,
            "invited_friends_count": 0,
            "ref_generated_amount": 0.00,
            "claimed_ref_tasks": []
        }
        user_ref.set(user_data)
    else:
        user_data = user_doc.to_dict() or {}
        auto_fix = {}

        if "daily_boost_rate" not in user_data: auto_fix["daily_boost_rate"] = 0.00
        if "ads_watched" not in user_data: auto_fix["ads_watched"] = 0
        if "upgrades" not in user_data: auto_fix["upgrades"] = {}
        if "pending_ref_earnings" not in user_data: auto_fix["pending_ref_earnings"] = 0.00
        if "total_ref_earnings" not in user_data: auto_fix["total_ref_earnings"] = 0.00
        if "upgrades_count" not in user_data:
            upgrades_dict = user_data.get("upgrades", {})
            auto_fix["upgrades_count"] = sum(int(v) for v in upgrades_dict.values() if isinstance(v, (int, float))) if isinstance(upgrades_dict, dict) else 0

        if auto_fix:
            user_ref.update(auto_fix)
            user_data.update(auto_fix)

    expected_max_cap = calculate_user_max_cap(user_data, game_settings)
    if user_data.get("max_cap") != expected_max_cap:
        user_data["max_cap"] = expected_max_cap
        user_ref.update({"max_cap": expected_max_cap})

    user_data["balance"] = round(float(user_data.get("balance", 0.0)), 2)
    user_data["unclaimed"] = calculate_accrued_mined(user_data, now, expected_max_cap)

    today_str = now.strftime('%Y-%m-%d')
    yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    last_daily_claim = user_data.get("last_daily_claim_date")
    raw_daily_day = int(user_data.get("daily_day") or user_data.get("daily_streak") or 1)

    if last_daily_claim == today_str:
        effective_daily_day = raw_daily_day
    elif last_daily_claim == yesterday_str:
        effective_daily_day = min(raw_daily_day + 1, 30) if raw_daily_day < 30 else 30
    else:
        effective_daily_day = 1

    user_data["daily_day"] = effective_daily_day
    user_data["daily_streak"] = effective_daily_day

    return user_data, game_settings, now


def claim_mined_tokens_db(user_id_str, cooldown_seconds=15):
    """تجميع الرصيد المعدن من المخزن مع احتساب نسبة الإحالة بشكل آمن"""
    db = get_db()
    user_ref = db.collection('users').document(user_id_str)
    game_settings = get_game_settings()

    mining_cfg = game_settings.get("mining_config", {})
    cooldown = int(mining_cfg.get("cooldown_seconds", cooldown_seconds))

    @firestore.transactional
    def run_claim_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)

        last_claim_str = user_data.get("last_claim_time")
        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(str(last_claim_str).replace('Z', '+00:00'))
                if last_claim.tzinfo is None:
                    last_claim = last_claim.replace(tzinfo=timezone.utc)
                seconds_passed = (now - last_claim).total_seconds()
                if seconds_passed < cooldown:
                    return {"success": False, "error": f"الرجاء الانتظار {cooldown} ثانية قبل التجميع مجدداً"}
            except Exception:
                pass

        max_cap = calculate_user_max_cap(user_data, game_settings)
        mined_amount = calculate_accrued_mined(user_data, now, max_cap)

        if mined_amount <= 0:
            return {"success": False, "error": "المخزن فارغ حالياً"}

        referred_by = user_data.get("referred_by")
        referrer_ref = None
        referrer_doc = None
        commission = 0.0

        if referred_by and str(referred_by).strip() != "" and str(referred_by) != "null":
            try:
                friends_cfg = game_settings.get("friends_config", {})
                comm_pct = float(friends_cfg.get("commission_percent", 10))
                commission = round(mined_amount * (comm_pct / 100.0), 2)
                if commission > 0:
                    referrer_ref = db.collection('users').document(str(referred_by))
                    referrer_doc = referrer_ref.get(transaction=transaction)
            except Exception as ref_read_err:
                print(f"⚠️ خطأ قراءة مستند المحيل: {ref_read_err}")

        current_balance = float(user_data.get("balance", 0.0))
        new_balance = round(current_balance + mined_amount, 2)
        now_iso = now.isoformat()

        transaction.update(ref, {
            "balance": new_balance,
            "last_claim_time": now_iso
        })

        if referrer_ref and referrer_doc and referrer_doc.exists and commission > 0:
            try:
                transaction.update(referrer_ref, {
                    "pending_ref_earnings": firestore.Increment(commission),
                    "total_ref_earnings": firestore.Increment(commission)
                })
                friend_sub_ref = referrer_ref.collection('friends').document(user_id_str)
                friend_name = user_data.get('first_name') or user_data.get('name') or 'صديق'
                transaction.set(friend_sub_ref, {
                    "earned_from_him": firestore.Increment(commission),
                    "name": friend_name
                }, merge=True)
            except Exception as ref_err:
                print(f"⚠️ خطأ تحديث عمولة الإحالة: {ref_err}")

        return {
            "success": True,
            "new_balance": new_balance,
            "last_claim_time": now_iso,
            "server_time": now_iso,
            "claimed_amount": mined_amount
        }

    transaction = db.transaction()
    return run_claim_transaction(transaction, user_ref)


def buy_upgrade_db(user_id_str, level):
    """شراء ترقية معدل التعدين لمستويات المزرعة (1-9)"""
    level_str = str(level)
    db = get_db()
    user_ref = db.collection('users').document(user_id_str)
    game_settings = get_game_settings()

    upgrade_configs = game_settings.get("upgrade_config") or DEFAULT_FARM_SETTINGS["upgrade_config"]
    if level_str not in upgrade_configs:
        return {"success": False, "error": "بيانات المستوى غير متوفرة"}

    level_cfg = upgrade_configs[level_str]
    cost = float(level_cfg.get("base_cost", level_cfg.get("price", 0)))
    rate_bonus = round(float(level_cfg.get("rate_bonus", level_cfg.get("rate", 0))), 2)

    @firestore.transactional
    def run_upgrade_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}
        current_balance = float(user_data.get("balance", 0.0))

        if current_balance < cost:
            return {"success": False, "error": f"رصيدك غير كافٍ لإتمام الترقية. السعر المطلوبة: {cost}"}

        upgrades = user_data.get("upgrades", {})
        if not isinstance(upgrades, dict):
            upgrades = {}

        lvl_key = f"lvl{level_str}"
        current_count = int(upgrades.get(lvl_key, 0))

        if current_count >= 10:
            return {"success": False, "error": "لقد وصلت للحد الأقصى لهذا المستوى (10/10)"}

        if int(level_str) > 1:
            prev_lvl = str(int(level_str) - 1)
            prev_key = f"lvl{prev_lvl}"
            prev_count = int(upgrades.get(prev_key, 0))
            if prev_count == 0:
                return {"success": False, "error": "يجب شراء المستوى السابق أولاً"}

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        max_cap = calculate_user_max_cap(user_data, game_settings)
        mined_amount = calculate_accrued_mined(user_data, now, max_cap)

        new_balance = round((current_balance + mined_amount) - cost, 2)
        current_hourly_rate = float(user_data.get("hourly_rate", 0.0))
        new_hourly_rate = round(current_hourly_rate + rate_bonus, 2)

        upgrades[lvl_key] = current_count + 1
        total_upgrades_count = sum(int(v) for v in upgrades.values() if isinstance(v, (int, float)))

        transaction.update(ref, {
            "balance": new_balance,
            "hourly_rate": new_hourly_rate,
            "upgrades": upgrades,
            "upgrades_count": total_upgrades_count,
            "last_claim_time": now_iso
        })

        return {
            "success": True,
            "new_balance": new_balance,
            "new_hourly_rate": new_hourly_rate,
            "upgrades": upgrades,
            "upgrades_count": total_upgrades_count,
            "server_time": now_iso
        }

    transaction = db.transaction()
    return run_upgrade_transaction(transaction, user_ref)


def claim_daily_reward_db(user_id_str):
    """استلام المكافأة اليومية للتسجيل (30 يوم)"""
    db = get_db()
    user_ref = db.collection('users').document(user_id_str)
    game_settings = get_game_settings()
    parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))

    @firestore.transactional
    def run_daily_claim_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)
        today_str = now.strftime('%Y-%m-%d')
        yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        last_daily_claim = user_data.get("last_daily_claim_date")

        if last_daily_claim == today_str:
            return {"success": False, "error": "لقد قمت باستلام المكافأة اليوم بالفعل"}

        raw_daily_day = int(user_data.get("daily_day") or user_data.get("daily_streak") or 1)

        if last_daily_claim == yesterday_str:
            effective_daily_day = min(raw_daily_day + 1, 30) if raw_daily_day < 30 else 30
        else:
            effective_daily_day = 1

        reward_index = min(max(effective_daily_day - 1, 0), 29)
        reward_amount = float(parsed_rewards[reward_index])

        current_balance = float(user_data.get("balance", 0.0))
        new_balance = round(current_balance + reward_amount, 2)
        new_ads_watched = int(user_data.get("ads_watched", 0)) + 1

        transaction.update(ref, {
            "balance": new_balance,
            "daily_day": effective_daily_day,
            "daily_streak": effective_daily_day,
            "last_daily_claim_date": today_str,
            "ads_watched": firestore.Increment(1)
        })

        return {
            "success": True,
            "new_balance": new_balance,
            "daily_day": effective_daily_day,
            "last_daily_claim_date": today_str,
            "ads_watched": new_ads_watched,
            "server_time": now.isoformat()
        }

    transaction = db.transaction()
    return run_daily_claim_transaction(transaction, user_ref)


def claim_daily_boost_db(user_id_str):
    """
    تفعيل التعزيز اليومي:
    - يضيف سرعة (+0.5/h) طالما daily_boost_rate أقل من 15.0
    - عند الوصول إلى 15.0 أو أكثر ينقل تلقائياً لإضافة 50 عملة ZN للرصيد فوراً
    """
    db = get_db()
    user_ref = db.collection('users').document(user_id_str)
    game_settings = get_game_settings()
    mining_cfg = game_settings.get("mining_config", DEFAULT_FARM_SETTINGS["mining_config"])

    daily_boost_reward = round(float(mining_cfg.get("daily_boost_reward", 0.5)), 2)
    target_speed = round(float(mining_cfg.get("daily_boost_target_speed", 15.0)), 2)
    coin_reward = round(float(mining_cfg.get("daily_boost_coin_reward", 50.0)), 2)

    @firestore.transactional
    def run_boost_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)
        today_str = now.strftime('%Y-%m-%d')

        last_boost = user_data.get("last_boost_date")
        if last_boost == today_str:
            return {"success": False, "error": "لقد حصلت على تعزيز اليوم بالفعل"}

        daily_boost_rate = float(user_data.get("daily_boost_rate", 0.0) or 0.0)
        current_hourly_rate = float(user_data.get("hourly_rate", 0.0) or 0.0)
        current_balance = float(user_data.get("balance", 0.0) or 0.0)
        current_ads = int(user_data.get("ads_watched", 0) or 0)
        new_ads = current_ads + 1

        if daily_boost_rate < target_speed:
            new_daily_boost_rate = round(daily_boost_rate + daily_boost_reward, 2)
            new_hourly_rate = round(current_hourly_rate + daily_boost_reward, 2)

            transaction.update(ref, {
                "hourly_rate": new_hourly_rate,
                "daily_boost_rate": new_daily_boost_rate,
                "last_boost_date": today_str,
                "ads_watched": firestore.Increment(1)
            })

            return {
                "success": True,
                "type": "speed",
                "new_rate": new_hourly_rate,
                "daily_boost_rate": new_daily_boost_rate,
                "ads_watched": new_ads,
                "last_boost_date": today_str,
                "server_time": now.isoformat()
            }
        else:
            new_balance = round(current_balance + coin_reward, 2)

            transaction.update(ref, {
                "balance": new_balance,
                "last_boost_date": today_str,
                "ads_watched": firestore.Increment(1)
            })

            return {
                "success": True,
                "type": "balance",
                "new_balance": new_balance,
                "new_rate": current_hourly_rate,
                "daily_boost_rate": daily_boost_rate,
                "ads_watched": new_ads,
                "last_boost_date": today_str,
                "server_time": now.isoformat()
            }

    transaction = db.transaction()
    return run_boost_transaction(transaction, user_ref)

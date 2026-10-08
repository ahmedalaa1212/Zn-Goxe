import time
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from database import get_db

# ==================== ثوابت وحدود الأمان القصوى (Sanity Checks Limits) ====================
MAX_SAFE_BALANCE = 1000000000.0     # الحد الأقصى المسموح به للرصيد (1 مليار ZN)
MAX_SAFE_HOURLY_RATE = 500.0        # الحد الأقصى لمعدل التعدين بالساعة (500 ZN/h)
MAX_SAFE_STORAGE_CAP = 5000.0       # الحد الأقصى لسعة المخزن (5000 ZN)
FUTURE_SKEW_TOLERANCE_SEC = 300     # التسامح المسموح لفرق التوقيت المستقبلي (5 دقائق)

def to_bool(val):
    """تحويل قيم البوليان بشكل صحيح وآمن من القراءات المختلفة"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    if isinstance(val, (int, float)):
        return val != 0
    return False


def safe_parse_datetime(dt_raw, default_dt=None):
    """معالجة آمنة لتحويل أي تاريخ أو ختم زمني إلى UTC مع حماية ضد التواريخ غير المنطقية"""
    if dt_raw is None:
        return default_dt
    try:
        if isinstance(dt_raw, (int, float)):
            # حماية ضد أختام زمنية سالبة أو مستقبلية شاذة جداً (بعد عام 2100)
            if dt_raw < 0 or dt_raw > 4102444800:
                return default_dt
            return datetime.fromtimestamp(dt_raw, tz=timezone.utc)
        elif isinstance(dt_raw, datetime):
            if dt_raw.tzinfo is None:
                return dt_raw.replace(tzinfo=timezone.utc)
            return dt_raw.astimezone(timezone.utc)
        else:
            s = str(dt_raw).strip().replace('Z', '+00:00')
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        return default_dt


# ==================== Caching لتوفير قراءات Firestore ====================
_SETTINGS_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 15

# ==================== الإعدادات الافتراضية الاقتصادية ====================
DEFAULT_GAME_SETTINGS = {
    "daily_rewards": [
        0.20, 0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.20, 1.50, 2.00,
        2.50, 3.00, 3.50, 4.00, 5.00, 6.00, 7.00, 8.00, 10.0, 12.0,
        14.0, 16.0, 18.0, 20.0, 24.0, 28.0, 32.0, 35.0, 38.0, 40.0
    ],
    "mining_config": {
        "daily_boost_reward": 0.10,
        "max_daily_boost_rate": 4.5,
        "boost_max_reward_coins": 35.0,
        "claim_cooldown_seconds": 15,
        "base_free_rate": 0.10,
        "max_upgrades_per_level": 15
    },
    "storage_capacities": {
        "0": {"capacity": 0.5, "cost_zn": 0.0, "cost_usd": 0.0},
        "1": {"capacity": 1.5, "cost_zn": 50.0, "cost_usd": 0.0},
        "2": {"capacity": 4.0, "cost_zn": 200.0, "cost_usd": 0.20},
        "3": {"capacity": 10.0, "cost_zn": 800.0, "cost_usd": 0.50},
        "4": {"capacity": 25.0, "cost_zn": 2500.0, "cost_usd": 1.00},
        "5": {"capacity": 60.0, "cost_zn": 7000.0, "cost_usd": 2.50},
        "6": {"capacity": 150.0, "cost_zn": 20000.0, "cost_usd": 5.00},
        "7": {"capacity": 400.0, "cost_zn": 50000.0, "cost_usd": 10.00},
        "8": {"capacity": 1000.0, "cost_zn": 120000.0, "cost_usd": 20.00}
    },
    "upgrade_config": {
        "1": {"cost_zn": 100.0, "cost_usd": 0.0, "rate_bonus": 0.20},
        "2": {"cost_zn": 400.0, "cost_usd": 0.25, "rate_bonus": 0.50},
        "3": {"cost_zn": 1500.0, "cost_usd": 0.60, "rate_bonus": 1.20},
        "4": {"cost_zn": 5000.0, "cost_usd": 1.25, "rate_bonus": 2.80},
        "5": {"cost_zn": 15000.0, "cost_usd": 3.00, "rate_bonus": 6.00},
        "6": {"cost_zn": 40000.0, "cost_usd": 6.00, "rate_bonus": 14.00},
        "7": {"cost_zn": 100000.0, "cost_usd": 12.00, "rate_bonus": 30.00},
        "8": {"cost_zn": 250000.0, "cost_usd": 25.00, "rate_bonus": 70.00}
    }
}


def create_default_user_data_dict(user_id_str, game_settings, now_dt):
    """إنشاء الهيكل الافتراضي لبيانات المستخدم بالتوقيت العالمي UTC"""
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    base_free_rate = float(mining_cfg.get("base_free_rate", 0.10))
    base_cap = get_base_storage_capacity(0, game_settings)
    now_iso = now_dt.isoformat()
    
    return {
        "tg_id": str(user_id_str),
        "telegram_id": str(user_id_str),
        "balance": 0.00000000,
        "usd_balance": 0.00000000,
        "total_mined": 0.00000000,
        "mined_points": 0.00000000,
        "hourly_rate": base_free_rate,
        "daily_boost_rate": 0.00,
        "base_unclaimed": 0.00000000,
        "unclaimed": 0.00000000,
        "storage_level": 0,
        "extra_storage": 0.00,
        "max_cap": base_cap,
        "daily_day": 1,
        "daily_streak": 1,
        "last_claim_time": now_iso,
        "last_daily_claim_date": None,
        "last_boost_date": None,
        "last_boost_time": None,
        "last_claim_ad_date": None,
        "ads_watched": 0,
        "upgrades": {},
        "upgrades_count": 0,
        "welcome_seen": False,
        "is_new_user": True,
        "bot_active": False
    }


def get_game_settings(force_refresh=False):
    """جلب أو إنشاء إعدادات المزرعة تلقائياً في Firebase إن لم تكن موجودة"""
    global _SETTINGS_CACHE
    now_ts = time.time()
    
    if not force_refresh and _SETTINGS_CACHE["data"] and (now_ts - _SETTINGS_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _SETTINGS_CACHE["data"]

    db = get_db()
    try:
        doc_ref = db.collection('settings').document('farm_settings')
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            _SETTINGS_CACHE = {"data": data, "timestamp": now_ts}
            return data
        else:
            doc_ref.set(DEFAULT_GAME_SETTINGS)
            _SETTINGS_CACHE = {"data": DEFAULT_GAME_SETTINGS, "timestamp": now_ts}
            return DEFAULT_GAME_SETTINGS
    except Exception as e:
        print(f"⚠️ خطأ أثناء جلب إعدادات المزرعة من Firebase: {e}")

    return _SETTINGS_CACHE["data"] or DEFAULT_GAME_SETTINGS


def parse_daily_rewards(rewards_data):
    """تحليل قائمة المكافآت اليومية بأمان لدعم قيم الفلوت"""
    if isinstance(rewards_data, list) and len(rewards_data) > 0:
        return [max(0.0, min(float(x), 1000.0)) for x in rewards_data]
    if isinstance(rewards_data, dict):
        res = []
        for i in range(1, 31):
            val = rewards_data.get(f"day_{i}")
            if val is None:
                val = rewards_data.get(str(i))
            if val is None:
                val = DEFAULT_GAME_SETTINGS["daily_rewards"][i-1]
            res.append(max(0.0, min(float(val), 1000.0)))
        return res
    return [float(x) for x in DEFAULT_GAME_SETTINGS["daily_rewards"]]


def get_base_storage_capacity(storage_level, settings=None):
    """حساب السعة التخزينية الأساسية للمخزن"""
    if not settings:
        settings = get_game_settings()
    try:
        lvl = int(storage_level)
    except (ValueError, TypeError):
        lvl = 0
    lvl = max(0, min(lvl, 8))

    caps = settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_capacities"]

    val = caps.get(str(lvl))
    if val is None:
        val = caps.get(lvl)

    if isinstance(val, dict):
        return min(float(val.get("capacity", 0.5)), MAX_SAFE_STORAGE_CAP)
    elif val is not None:
        return min(float(val), MAX_SAFE_STORAGE_CAP)
    return 0.5


def calculate_user_max_cap(user_data, settings=None):
    """حساب أقصى سعة للمخزن المؤقت للمستخدم مع تطبيق فحص الحدود القصوى"""
    if not settings:
        settings = get_game_settings()
    stg_lvl = user_data.get("storage_level", 0)
    base_cap = get_base_storage_capacity(stg_lvl, settings)
    extra_cap = max(0.0, float(user_data.get("extra_storage", 0.0)))
    total_cap = base_cap + extra_cap
    return min(round(total_cap, 4), MAX_SAFE_STORAGE_CAP)


def get_bot_expiration_dt(user_data):
    """استخراج تاريخ ووقت انتهاء باقة البوت/VIP إن وجد بشكل دقيق مع حماية التاريخ"""
    vip_info = user_data.get("vip_status")
    expires_at_raw = None

    if isinstance(vip_info, dict):
        expires_at_raw = vip_info.get("expires_at") or vip_info.get("vip_expires_at") or vip_info.get("bot_expires_at") or vip_info.get("expire_date") or vip_info.get("expires_date")
    
    if not expires_at_raw:
        expires_at_raw = user_data.get("bot_expires_at") or user_data.get("expires_at") or user_data.get("vip_expires_at") or user_data.get("vip_expire_date")

    return safe_parse_datetime(expires_at_raw)


def _calculate_interval_mined(hourly_rate, start_dt, end_dt, last_boost_str=None):
    """حساب الكمية المعدنة الدقيقة بين نقطتين زمنيتين مع معالجة التواريخ والسرعة الفائقة"""
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0.0
    
    # حماية ضد المعدلات السلبية أو المتضخمة جداً
    safe_rate = max(0.0, min(float(hourly_rate), MAX_SAFE_HOURLY_RATE))
    seconds_passed = (end_dt - start_dt).total_seconds()
    
    # منع التعدين لمقادير زمنية سلبية أو خيالية (أكثر من سنة غياب دفعة واحدة)
    if seconds_passed <= 0:
        return 0.0
    if seconds_passed > 31536000: # 365 يوم max
        seconds_passed = 31536000

    base_mined = (safe_rate / 3600.0) * seconds_passed

    boost_bonus = 0.0
    if last_boost_str:
        boost_start = safe_parse_datetime(last_boost_str)
        if boost_start:
            boost_end = boost_start + timedelta(hours=2) # مدة المعزز 2 ساعة
            overlap_start = max(start_dt, boost_start)
            overlap_end = min(end_dt, boost_end)

            if overlap_end > overlap_start:
                boosted_seconds = (overlap_end - overlap_start).total_seconds()
                boost_bonus = (0.10 / 3600.0) * boosted_seconds

    return base_mined + boost_bonus


def calculate_accrued_mined(user_data, now_dt, max_cap, ignore_cap=False):
    """حساب الكمية المعدنة الحالية بدقة مباشرة من تاريخ آخر تجميع حقيقي مع تطبيق سقف التخزين"""
    last_claim_str = user_data.get("last_claim_time")
    hourly_rate = min(float(user_data.get("hourly_rate", 0.10)), MAX_SAFE_HOURLY_RATE)

    last_claim = safe_parse_datetime(last_claim_str, now_dt)
    if not last_claim:
        last_claim = now_dt
    
    # معالجة حالة المستقبل (تلاعب بالساعة): إذا كان التاريخ أسبق من الآن بصورة شاذة
    if last_claim > (now_dt + timedelta(seconds=FUTURE_SKEW_TOLERANCE_SEC)):
        last_claim = now_dt

    mined = _calculate_interval_mined(hourly_rate, last_claim, now_dt, user_data.get("last_boost_time"))
    
    if ignore_cap:
        return round(mined, 8)
    return round(min(mined, max_cap), 8)


def dismiss_welcome_db(user_id_str):
    """تعيين حالة مشاهدة النافذة الترحيبية لمنع ظهورها مجدداً"""
    db = get_db()
    user_ref = db.collection('users').document(str(user_id_str))
    user_ref.set({"welcome_seen": True, "is_new_user": False}, merge=True)
    return {"success": True, "welcome_seen": True, "is_new_user": False}


def calculate_user_effective_stats(user_data, game_settings=None, now_dt=None):
    """فحص وتحديث صلاحية اشتراك الباقة أو البوت وتحديث حالة bot_active بناءً على vip_status وتاريخ الانتهاء"""
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    raw_bot_flag = to_bool(user_data.get("bot_active", user_data.get("has_bot", user_data.get("is_auto_bot_active", False))))
    
    vip_info = user_data.get("vip_status")
    if isinstance(vip_info, dict):
        vip_bot = to_bool(vip_info.get("auto_bot", vip_info.get("is_auto_bot_active", vip_info.get("bot_active", False))))
        raw_bot_flag = raw_bot_flag or vip_bot

    exp_dt = get_bot_expiration_dt(user_data)

    is_active = False
    if raw_bot_flag:
        if exp_dt is None or exp_dt > now_dt:
            is_active = True

    # تطبيق Sanity checks إضافية على الأرصدة
    user_data["balance"] = min(max(0.0, float(user_data.get("balance", 0.0))), MAX_SAFE_BALANCE)
    user_data["usd_balance"] = min(max(0.0, float(user_data.get("usd_balance", 0.0))), 1000000.0)
    user_data["hourly_rate"] = min(max(0.10, float(user_data.get("hourly_rate", 0.10))), MAX_SAFE_HOURLY_RATE)

    user_data["bot_active"] = is_active
    user_data["is_auto_bot_active"] = is_active
    return user_data


def get_or_create_user_farm_data(user_id_str):
    """جلب وتجهيز كافة بيانات المستخدم الخاصة بالمزرعة وحساب التعدين مباشرة من تاريخ آخر تجميع لمنع التراكم المكرر"""
    db = get_db()
    str_uid = str(user_id_str)
    user_ref = db.collection('users').document(str_uid)
    user_doc = user_ref.get()
    now = datetime.now(timezone.utc)
    game_settings = get_game_settings()
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    base_free_rate = float(mining_cfg.get("base_free_rate", 0.10))

    if not user_doc.exists:
        user_data = create_default_user_data_dict(str_uid, game_settings, now)
        user_ref.set(user_data)
    else:
        user_data = user_doc.to_dict() or {}
        auto_fix = {}
        
        if "welcome_seen" not in user_data:
            has_progress = bool(user_data.get("upgrades") or user_data.get("last_daily_claim_date") or user_data.get("last_boost_time"))
            auto_fix["welcome_seen"] = has_progress
            auto_fix["is_new_user"] = not has_progress

        if "usd_balance" not in user_data: auto_fix["usd_balance"] = 0.00
        if "mined_points" not in user_data:
            auto_fix["mined_points"] = float(user_data.get("mined_points", user_data.get("total_mined", 0.0)))
        if "total_mined" not in user_data:
            auto_fix["total_mined"] = float(user_data.get("mined_points", 0.0))
        
        current_hr = float(user_data.get("hourly_rate", 0.0))
        if current_hr < base_free_rate and not user_data.get("upgrades"):
            auto_fix["hourly_rate"] = base_free_rate
        elif current_hr > MAX_SAFE_HOURLY_RATE:
            auto_fix["hourly_rate"] = MAX_SAFE_HOURLY_RATE

        if "daily_boost_rate" not in user_data: auto_fix["daily_boost_rate"] = 0.00
        if "last_boost_time" not in user_data: auto_fix["last_boost_time"] = None
        if "base_unclaimed" not in user_data: auto_fix["base_unclaimed"] = 0.0
        if "ads_watched" not in user_data: auto_fix["ads_watched"] = 0
        if "storage_level" not in user_data: auto_fix["storage_level"] = 0
        if "upgrades" not in user_data: auto_fix["upgrades"] = {}
        if "last_claim_ad_date" not in user_data: auto_fix["last_claim_ad_date"] = None
        if "last_claim_time" not in user_data or not user_data.get("last_claim_time"):
            auto_fix["last_claim_time"] = now.isoformat()
        if "bot_active" not in user_data: auto_fix["bot_active"] = False
            
        if "upgrades_count" not in user_data:
            upgrades_dict = user_data.get("upgrades", {})
            auto_fix["upgrades_count"] = sum(int(v) for v in upgrades_dict.values() if isinstance(v, (int, float))) if isinstance(upgrades_dict, dict) else 0
        
        expected_max_cap = calculate_user_max_cap(user_data, game_settings)
        if user_data.get("max_cap") != expected_max_cap:
            auto_fix["max_cap"] = expected_max_cap

        if auto_fix:
            user_ref.update(auto_fix)
            user_data.update(auto_fix)

    # 1. تحديث وتدقيق صلاحية البوت/VIP والحدود الأقصى
    user_data = calculate_user_effective_stats(user_data, game_settings, now)

    expected_max_cap = calculate_user_max_cap(user_data, game_settings)
    user_data["max_cap"] = expected_max_cap
    user_data["balance"] = round(min(float(user_data.get("balance", 0.0)), MAX_SAFE_BALANCE), 8)
    user_data["usd_balance"] = round(float(user_data.get("usd_balance", 0.0)), 8)
    user_data["mined_points"] = round(float(user_data.get("mined_points", user_data.get("total_mined", 0.0))), 8)
    user_data["total_mined"] = user_data["mined_points"]

    # ====================================================================
    # منطق التجميع وحساب التعدين اللحظي (Backend Offline & Realtime Calculation)
    # ====================================================================
    last_claim_dt = safe_parse_datetime(user_data.get("last_claim_time"), now)
    if not last_claim_dt or last_claim_dt > (now + timedelta(seconds=FUTURE_SKEW_TOLERANCE_SEC)):
        last_claim_dt = now

    is_bot_active = user_data.get("bot_active", False)
    exp_dt = get_bot_expiration_dt(user_data)
    hourly_rate = min(float(user_data.get("hourly_rate", 0.10)), MAX_SAFE_HOURLY_RATE)
    last_boost_str = user_data.get("last_boost_time")

    auto_claimed_amount = 0.0
    db_updates = {}

    if is_bot_active or (exp_dt and exp_dt > last_claim_dt):
        bot_end_dt = min(now, exp_dt) if exp_dt else now
        bot_mined = _calculate_interval_mined(hourly_rate, last_claim_dt, bot_end_dt, last_boost_str)
        accumulated_offline = round(bot_mined, 8)
        threshold_80 = round(expected_max_cap * 0.8, 8)

        if accumulated_offline >= threshold_80:
            auto_claimed_amount = accumulated_offline
            user_data["balance"] = round(min(user_data["balance"] + auto_claimed_amount, MAX_SAFE_BALANCE), 8)
            user_data["mined_points"] = round(user_data["mined_points"] + auto_claimed_amount, 8)
            user_data["total_mined"] = user_data["mined_points"]
            user_data["base_unclaimed"] = 0.0
            user_data["unclaimed"] = 0.0
            user_data["last_claim_time"] = bot_end_dt.isoformat()

            db_updates["balance"] = user_data["balance"]
            db_updates["mined_points"] = user_data["mined_points"]
            db_updates["total_mined"] = user_data["total_mined"]
            db_updates["base_unclaimed"] = 0.0
            db_updates["unclaimed"] = 0.0
            db_updates["last_claim_time"] = user_data["last_claim_time"]

            if bot_end_dt < now:
                post_bot_mined = _calculate_interval_mined(hourly_rate, bot_end_dt, now, last_boost_str)
                user_data["unclaimed"] = round(min(post_bot_mined, expected_max_cap), 8)
                user_data["base_unclaimed"] = user_data["unclaimed"]
        else:
            total_mined_so_far = _calculate_interval_mined(hourly_rate, last_claim_dt, now, last_boost_str)
            unclaimed_val = round(min(total_mined_so_far, expected_max_cap), 8)
            user_data["unclaimed"] = unclaimed_val
            user_data["base_unclaimed"] = unclaimed_val

        is_currently_active = (exp_dt is None or exp_dt > now) if is_bot_active else False
        user_data["bot_active"] = is_currently_active
        user_data["is_auto_bot_active"] = is_currently_active
        if is_currently_active != is_bot_active:
            db_updates["bot_active"] = is_currently_active
            db_updates["is_auto_bot_active"] = is_currently_active
    else:
        unclaimed_val = calculate_accrued_mined(user_data, now, expected_max_cap)
        user_data["unclaimed"] = unclaimed_val
        user_data["base_unclaimed"] = unclaimed_val
        user_data["bot_active"] = False
        user_data["is_auto_bot_active"] = False

        if user_doc.exists and to_bool(user_doc.to_dict().get("bot_active", False)):
            db_updates["bot_active"] = False
            db_updates["is_auto_bot_active"] = False

    if db_updates:
        try:
            user_ref.update(db_updates)
        except Exception as e:
            print(f"⚠️ Error updating offline farm calculations in DB: {e}")

    if auto_claimed_amount > 0:
        referrer_id = user_data.get("referrer_id") or user_data.get("referred_by") or user_data.get("invited_by")
        if referrer_id:
            try:
                from friends.friends_db import add_referral_reward
                add_referral_reward(
                    referrer_id=referrer_id,
                    user_id=str_uid,
                    mined_amount=auto_claimed_amount,
                    user_upgrades_count=user_data.get("upgrades_count"),
                    user_name=user_data.get("first_name") or user_data.get("name") or user_data.get("username")
                )
            except Exception as ref_e:
                print(f"⚠️ Error adding referral reward on offline auto-claim: {ref_e}")

    user_data["auto_claimed_amount"] = auto_claimed_amount

    is_welcome_seen = to_bool(user_data.get("welcome_seen", False))
    user_data["welcome_seen"] = is_welcome_seen
    user_data["is_new_user"] = not is_welcome_seen

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


def claim_mined_tokens_db(user_id_str):
    """تجميع الرصيد المعدن بأسلوب المعاملات الآمنة (Firestore Transaction) لمنع Race Condition"""
    db = get_db()
    str_uid = str(user_id_str)
    user_ref = db.collection('users').document(str_uid)
    game_settings = get_game_settings()
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    cooldown_seconds = int(mining_cfg.get("claim_cooldown_seconds", 15))

    @firestore.transactional
    def run_claim_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        now = datetime.now(timezone.utc)
        today_utc_str = now.strftime('%Y-%m-%d')

        if not snapshot.exists:
            user_data = create_default_user_data_dict(str_uid, game_settings, now)
            transaction.set(ref, user_data)
        else:
            user_data = snapshot.to_dict() or {}

        last_claim_str = user_data.get("last_claim_time")
        if last_claim_str:
            last_claim = safe_parse_datetime(last_claim_str)
            if last_claim:
                seconds_passed = (now - last_claim).total_seconds()
                if seconds_passed < cooldown_seconds:
                    return {"success": False, "error": f"الرجاء الانتظار {cooldown_seconds} ثانية قبل التجميع مجدداً"}

        max_cap = calculate_user_max_cap(user_data, game_settings)
        mined_amount = calculate_accrued_mined(user_data, now, max_cap)

        if mined_amount <= 0:
            return {"success": False, "error": "المخزن فارغ حالياً"}

        current_balance = float(user_data.get("balance", 0.0))
        current_usd_balance = float(user_data.get("usd_balance", 0.0))
        current_mined_points = float(user_data.get("mined_points", user_data.get("total_mined", 0.0)))

        new_balance = round(min(current_balance + mined_amount, MAX_SAFE_BALANCE), 8)
        new_mined_points = round(current_mined_points + mined_amount, 8)
        now_iso = now.isoformat()

        transaction.update(ref, {
            "balance": new_balance,
            "mined_points": new_mined_points,
            "total_mined": new_mined_points,
            "last_claim_time": now_iso,
            "base_unclaimed": 0.0,
            "unclaimed": 0.0,
            "last_claim_ad_date": today_utc_str
        })

        referrer_id = user_data.get("referrer_id") or user_data.get("referred_by") or user_data.get("invited_by")
        upgrades_cnt = user_data.get("upgrades_count", 0)
        user_name = user_data.get("first_name") or user_data.get("name") or user_data.get("username")

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": round(current_usd_balance, 8),
            "total_mined": new_mined_points,
            "mined_points": new_mined_points,
            "last_claim_time": now_iso,
            "last_claim_ad_date": today_utc_str,
            "base_unclaimed": 0.0,
            "unclaimed": 0.0,
            "server_time": now_iso,
            "claimed_amount": mined_amount,
            "referrer_id": referrer_id,
            "upgrades_count": upgrades_cnt,
            "user_name": user_name
        }

    try:
        transaction = db.transaction()
        result = run_claim_transaction(transaction, user_ref)
    except Exception as e:
        return {"success": False, "error": f"تعذر تنفيذ التجميع: {str(e)}"}

    if result.get("success") and result.get("referrer_id") and result.get("claimed_amount", 0) > 0:
        try:
            from friends.friends_db import add_referral_reward
            add_referral_reward(
                referrer_id=result["referrer_id"],
                user_id=str_uid,
                mined_amount=result["claimed_amount"],
                user_upgrades_count=result.get("upgrades_count"),
                user_name=result.get("user_name")
            )
        except Exception as e:
            print(f"⚠️ Error adding referral reward on claim: {e}")

    return result


def buy_upgrade_db(user_id_str, level):
    """شراء ترقية سرعة التعدين مع فحص التدرج، حدود الرصيد المعقولة وFirestore Transactions"""
    level_str = str(level).strip()
    db = get_db()
    str_uid = str(user_id_str)
    user_ref = db.collection('users').document(str_uid)
    game_settings = get_game_settings()

    upgrade_configs = game_settings.get("upgrade_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
    if level_str not in upgrade_configs:
        return {"success": False, "error": "بيانات المستوى غير متوفرة"}

    level_cfg = upgrade_configs[level_str]
    cost_zn = float(level_cfg.get("cost_zn", level_cfg.get("base_cost", level_cfg.get("price", 0))))
    cost_usd = float(level_cfg.get("cost_usd", level_cfg.get("base_cost_usd", 0.0)))
    rate_bonus = round(float(level_cfg.get("rate_bonus", level_cfg.get("rate", 0))), 2)

    @firestore.transactional
    def run_upgrade_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        now = datetime.now(timezone.utc)

        if not snapshot.exists:
            user_data = create_default_user_data_dict(str_uid, game_settings, now)
            transaction.set(ref, user_data)
        else:
            user_data = snapshot.to_dict() or {}

        current_balance = float(user_data.get("balance", 0.0))
        current_usd_balance = float(user_data.get("usd_balance", 0.0))

        if current_balance < cost_zn:
            return {"success": False, "error": f"رصيد العملات غير كافٍ! سعر الترقية {cost_zn:,.0f} ZN"}

        if cost_usd > 0 and current_usd_balance < cost_usd:
            return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

        upgrades = user_data.get("upgrades", {})
        if not isinstance(upgrades, dict):
            upgrades = {}

        lvl_key = f"lvl{level_str}"
        current_count = int(upgrades.get(lvl_key, 0))

        if current_count >= 15:
            return {"success": False, "error": "لقد وصلت للحد الأقصى للشراء لهذا المستوى (15/15)"}

        if int(level_str) > 1:
            prev_lvl = str(int(level_str) - 1)
            prev_key = f"lvl{prev_lvl}"
            prev_count = int(upgrades.get(prev_key, 0))
            if prev_count == 0:
                return {"success": False, "error": "يجب شراء المستوى السابق أولاً"}

        max_cap = calculate_user_max_cap(user_data, game_settings)

        new_balance = round(max(0.0, current_balance - cost_zn), 8)
        new_usd_balance = round(max(0.0, current_usd_balance - cost_usd), 8)
        current_hourly_rate = float(user_data.get("hourly_rate", 0.10))
        
        # حماية ضد تجاوز الحد الأقصى لمعدل الساعات
        new_hourly_rate = round(min(current_hourly_rate + rate_bonus, MAX_SAFE_HOURLY_RATE), 4)

        upgrades[lvl_key] = current_count + 1
        total_upgrades_count = sum(int(v) for v in upgrades.values() if isinstance(v, (int, float)))

        last_claim_str = user_data.get("last_claim_time") or now.isoformat()

        transaction.update(ref, {
            "balance": new_balance,
            "usd_balance": new_usd_balance,
            "hourly_rate": new_hourly_rate,
            "upgrades": upgrades,
            "upgrades_count": total_upgrades_count
        })

        user_data_copy = dict(user_data)
        user_data_copy["hourly_rate"] = new_hourly_rate
        updated_unclaimed = calculate_accrued_mined(user_data_copy, now, max_cap)

        referrer_id = user_data.get("referrer_id") or user_data.get("referred_by") or user_data.get("invited_by")

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": new_usd_balance,
            "new_hourly_rate": new_hourly_rate,
            "last_claim_time": last_claim_str,
            "base_unclaimed": updated_unclaimed,
            "unclaimed": updated_unclaimed,
            "upgrades": upgrades,
            "upgrades_count": total_upgrades_count,
            "server_time": now.isoformat(),
            "referrer_id": referrer_id
        }

    try:
        transaction = db.transaction()
        res = run_upgrade_transaction(transaction, user_ref)
    except Exception as e:
        return {"success": False, "error": f"تعذر تنفيذ عملية الترقية: {str(e)}"}

    if res.get("success") and res.get("referrer_id"):
        try:
            ref_id = str(res["referrer_id"])
            upg_cnt = res["upgrades_count"]
            db.collection("users").document(ref_id).collection("friends").document(str_uid).set({
                "upgrades_count": upg_cnt,
                "tg_id": str_uid
            }, merge=True)
        except Exception as e:
            print(f"⚠️ Warning updating friend upgrades_count for referrer: {e}")

    return res


def buy_storage_db(user_id_str):
    """شراء ترقية سعة التخزين مع حماية أمان كاملة ومعاملات مجتمعة (Transaction)"""
    db = get_db()
    str_uid = str(user_id_str)
    user_ref = db.collection('users').document(str_uid)
    game_settings = get_game_settings()

    storage_cfgs = game_settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_capacities"]

    @firestore.transactional
    def run_storage_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        now = datetime.now(timezone.utc)

        if not snapshot.exists:
            user_data = create_default_user_data_dict(str_uid, game_settings, now)
            transaction.set(ref, user_data)
        else:
            user_data = snapshot.to_dict() or {}

        current_level = int(user_data.get("storage_level", 0))
        next_level = current_level + 1

        if next_level > 8 or str(next_level) not in storage_cfgs:
            return {"success": False, "error": "المخزن في أقصى مستوى بالفعل (MAX)"}

        next_cfg = storage_cfgs[str(next_level)]
        if isinstance(next_cfg, dict):
            cost_zn = float(next_cfg.get("cost_zn", next_cfg.get("cost", 0.0)))
            cost_usd = float(next_cfg.get("cost_usd", 0.0))
            new_capacity = float(next_cfg.get("capacity", 0.5))
        else:
            cost_zn = 0.0
            cost_usd = 0.0
            new_capacity = float(next_cfg)

        current_balance = float(user_data.get("balance", 0.0))
        current_usd_balance = float(user_data.get("usd_balance", 0.0))

        if current_balance < cost_zn:
            return {"success": False, "error": f"رصيدك غير كافٍ! سعر ترقية المخزن {cost_zn:,.0f} ZN"}

        if cost_usd > 0 and current_usd_balance < cost_usd:
            return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

        extra_cap = float(user_data.get("extra_storage", 0.0))
        new_max_cap = min(round(new_capacity + extra_cap, 4), MAX_SAFE_STORAGE_CAP)
        new_balance = round(max(0.0, current_balance - cost_zn), 8)
        new_usd_balance = round(max(0.0, current_usd_balance - cost_usd), 8)

        mined_amount = calculate_accrued_mined(user_data, now, new_max_cap)
        last_claim_str = user_data.get("last_claim_time") or now.isoformat()

        transaction.update(ref, {
            "balance": new_balance,
            "usd_balance": new_usd_balance,
            "storage_level": next_level,
            "max_cap": new_max_cap
        })

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": new_usd_balance,
            "storage_level": next_level,
            "max_cap": new_max_cap,
            "last_claim_time": last_claim_str,
            "base_unclaimed": mined_amount,
            "unclaimed": mined_amount,
            "server_time": now.isoformat()
        }

    try:
        transaction = db.transaction()
        return run_storage_transaction(transaction, user_ref)
    except Exception as e:
        return {"success": False, "error": f"تعذر إتمام ترقية المخزن: {str(e)}"}


def claim_daily_reward_db(user_id_str):
    """استلام المكافأة اليومية آمن ومحمي ضد النقر المكرر والسباق الزمني"""
    db = get_db()
    str_uid = str(user_id_str)
    user_ref = db.collection('users').document(str_uid)
    game_settings = get_game_settings()
    parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))

    @firestore.transactional
    def run_daily_claim_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        now = datetime.now(timezone.utc)

        if not snapshot.exists:
            user_data = create_default_user_data_dict(str_uid, game_settings, now)
            transaction.set(ref, user_data)
        else:
            user_data = snapshot.to_dict() or {}

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
        current_usd_balance = float(user_data.get("usd_balance", 0.0))
        new_balance = round(min(current_balance + reward_amount, MAX_SAFE_BALANCE), 8)
        new_ads_watched = int(user_data.get("ads_watched", 0)) + 1

        transaction.update(ref, {
            "balance": new_balance,
            "daily_day": effective_daily_day,
            "daily_streak": effective_daily_day,
            "last_daily_claim_date": today_str,
            "ads_watched": new_ads_watched
        })

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": round(current_usd_balance, 8),
            "reward_amount": reward_amount,
            "daily_day": effective_daily_day,
            "daily_streak": effective_daily_day,
            "last_daily_claim_date": today_str,
            "ads_watched": new_ads_watched,
            "server_time": now.isoformat()
        }

    try:
        transaction = db.transaction()
        return run_daily_claim_transaction(transaction, user_ref)
    except Exception as e:
        return {"success": False, "error": f"تعذر استلام المكافأة اليومية: {str(e)}"}


def claim_daily_boost_db(user_id_str):
    """تفعيل المعزز اليومي وتسجيل last_boost_time مع التحقق من فترة cooldown آمنة بـ Transaction"""
    db = get_db()
    str_uid = str(user_id_str)
    user_ref = db.collection('users').document(str_uid)
    game_settings = get_game_settings()

    @firestore.transactional
    def run_boost_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        now = datetime.now(timezone.utc)

        if not snapshot.exists:
            user_data = create_default_user_data_dict(str_uid, game_settings, now)
            transaction.set(ref, user_data)
        else:
            user_data = snapshot.to_dict() or {}

        now_iso = now.isoformat()
        today_str = now.strftime('%Y-%m-%d')
        last_boost_str = user_data.get("last_boost_time")

        if last_boost_str:
            last_boost = safe_parse_datetime(last_boost_str)
            if last_boost:
                elapsed_seconds = (now - last_boost).total_seconds()
                cooldown_seconds = 3 * 3600  # 3 ساعات فترة انتظار
                if elapsed_seconds < cooldown_seconds and elapsed_seconds >= 0:
                    remaining_seconds = int(cooldown_seconds - elapsed_seconds)
                    rem_hours = remaining_seconds // 3600
                    rem_mins = (remaining_seconds % 3600) // 60
                    time_str = f"{rem_hours} ساعة و {rem_mins} دقيقة" if rem_hours > 0 else f"{rem_mins} دقيقة"
                    return {
                        "success": False,
                        "error": f"الرجاء الانتظار {time_str} قبل تفعيل المعزز مجدداً",
                        "remaining_seconds": remaining_seconds
                    }

        max_cap = calculate_user_max_cap(user_data, game_settings)
        
        user_data_copy = dict(user_data)
        user_data_copy["last_boost_time"] = now_iso
        mined_amount = calculate_accrued_mined(user_data_copy, now, max_cap)

        current_balance = round(min(float(user_data.get("balance", 0.0)), MAX_SAFE_BALANCE), 8)
        current_usd_balance = round(float(user_data.get("usd_balance", 0.0)), 8)
        current_ads = int(user_data.get("ads_watched", 0) or 0)
        new_ads = current_ads + 1

        last_claim_str = user_data.get("last_claim_time") or now_iso

        transaction.update(ref, {
            "last_boost_time": now_iso,
            "last_boost_date": today_str,
            "ads_watched": new_ads
        })

        return {
            "success": True,
            "type": "speed",
            "boost_rate_bonus": 0.10,
            "boost_duration_hours": 2,
            "cooldown_hours": 3,
            "last_boost_time": now_iso,
            "last_boost_date": today_str,
            "last_claim_time": last_claim_str,
            "base_unclaimed": mined_amount,
            "unclaimed": mined_amount,
            "new_balance": current_balance,
            "new_usd_balance": current_usd_balance,
            "server_time": now_iso
        }

    try:
        transaction = db.transaction()
        return run_boost_transaction(transaction, user_ref)
    except Exception as e:
        return {"success": False, "error": f"تعذر تفعيل التعزيز: {str(e)}"}


def get_mining_leaderboard_db(limit=10):
    """جلب قائمة المتصدرين لأفضل المعدنين مع تنقية وتنظيف التواريخ والأرقام الشاَذة"""
    db = get_db()
    users_ref = db.collection('users')
    
    order_fields = ['mined_points', 'total_mined', 'mining_points']
    docs = []

    for field in order_fields:
        try:
            query = users_ref.order_by(field, direction=firestore.Query.DESCENDING).limit(limit)
            docs = list(query.stream())
            if docs:
                break
        except Exception as e:
            print(f"⚠️ Warning {field} query failed: {e}")

    if not docs:
        try:
            docs = list(users_ref.limit(100).stream())
        except Exception as inner_e:
            print(f"❌ Error getting leaderboard docs: {inner_e}")
            return []

    leaderboard = []
    for doc in docs:
        data = doc.to_dict() or {}
        name = data.get("first_name") or data.get("name") or data.get("username") or f"المستخدم {str(doc.id)[:4]}"
        
        mined_val = data.get("mined_points")
        if mined_val is None:
            mined_val = data.get("total_mined", 0.0)

        try:
            total_m = float(mined_val)
            if total_m > MAX_SAFE_BALANCE:
                total_m = MAX_SAFE_BALANCE
        except (ValueError, TypeError):
            total_m = 0.0

        leaderboard.append({
            "tg_id": str(doc.id),
            "name": name,
            "total_mined": round(total_m, 8),
            "mined_points": round(total_m, 8),
            "balance": round(min(float(data.get("balance", 0.0)), MAX_SAFE_BALANCE), 8),
            "hourly_rate": round(min(float(data.get("hourly_rate", 0.10)), MAX_SAFE_HOURLY_RATE), 4)
        })

    leaderboard.sort(key=lambda x: x['mined_points'], reverse=True)
    
    final_lb = []
    for rank, item in enumerate(leaderboard[:limit], start=1):
        item["rank"] = rank
        final_lb.append(item)

    return final_lb

# -*- coding: utf-8 -*-
"""
farm/farm_db.py - وحدة إدارة التعدين والمزرعة المربوطة بـ Supabase (PostgreSQL)
مُجهزة بمعاملات آمنة (Transactions) وتتبع دقيق للمسابقات وسجلات التجميع بالثانية ⚡
"""
import time
from datetime import datetime, timezone, timedelta
from psycopg2.extras import RealDictCursor, Json
from database import (
    get_db_connection, 
    get_setting, 
    set_setting, 
    get_user, 
    init_user, 
    format_iso, 
    safe_parse_datetime
)

# ==================== ثوابت وحدود الأمان القصوى ====================
MAX_SAFE_BALANCE = 1000000000.0     # الحد الأقصى المسموح به للرصيد (1 مليار ZN)
MAX_SAFE_HOURLY_RATE = 500.0        # الحد الأقصى لمعدل التعدين بالساعة (500 ZN/h)
MAX_SAFE_STORAGE_CAP = 5000.0       # الحد الأقصى لسعة المخزن (5000 ZN)
FUTURE_SKEW_TOLERANCE_SEC = 300     # التسامح المسموح لفرق التوقيت المستقبلي (5 دقائق)

def to_bool(val):
    """تحويل قيم البوليان بشكل صحيح وآمن من القراءات المختلفة"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "t")
    if isinstance(val, (int, float)):
        return val != 0
    return False


# ==================== Caching لتوفير الاتصالات ====================
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


def get_game_settings(force_refresh=False):
    """جلب أو إنشاء إعدادات المزرعة تلقائياً في Supabase إن لم تكن موجودة"""
    global _SETTINGS_CACHE
    now_ts = time.time()
    
    if not force_refresh and _SETTINGS_CACHE["data"] and (now_ts - _SETTINGS_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _SETTINGS_CACHE["data"]

    data = get_setting("farm_settings")
    if data and isinstance(data, dict):
        _SETTINGS_CACHE = {"data": data, "timestamp": now_ts}
        return data

    # إنشاء الإعدادات الافتراضية لأول مرة في Supabase لتظهر في لوحة المنصة
    set_setting("farm_settings", DEFAULT_GAME_SETTINGS)
    _SETTINGS_CACHE = {"data": DEFAULT_GAME_SETTINGS, "timestamp": now_ts}
    return DEFAULT_GAME_SETTINGS


def create_default_user_data_dict(user_id_str, game_settings, now_dt):
    """إنشاء الهيكل الافتراضي لبيانات المستخدم بالتوقيت العالمي UTC"""
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    base_free_rate = float(mining_cfg.get("base_free_rate", 0.10))
    base_cap = get_base_storage_capacity(0, game_settings)
    now_iso = format_iso(now_dt)
    
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
        "bot_active": False,
        "boost_claims_count": 0,
        "boost_history": [],
        "daily_claims_count": 0,
        "daily_history": []
    }


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
    
    safe_rate = max(0.0, min(float(hourly_rate), MAX_SAFE_HOURLY_RATE))
    seconds_passed = (end_dt - start_dt).total_seconds()
    
    if seconds_passed <= 0:
        return 0.0
    if seconds_passed > 31536000:
        seconds_passed = 31536000

    base_mined = (safe_rate / 3600.0) * seconds_passed

    boost_bonus = 0.0
    if last_boost_str:
        boost_start = safe_parse_datetime(last_boost_str)
        if boost_start:
            boost_end = boost_start + timedelta(hours=2)
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
    
    if last_claim > (now_dt + timedelta(seconds=FUTURE_SKEW_TOLERANCE_SEC)):
        last_claim = now_dt

    mined = _calculate_interval_mined(hourly_rate, last_claim, now_dt, user_data.get("last_boost_time"))
    
    if ignore_cap:
        return round(mined, 8)
    return round(min(mined, max_cap), 8)


def dismiss_welcome_db(user_id_str):
    """تعيين حالة مشاهدة النافذة الترحيبية لمنع ظهورها مجدداً"""
    str_uid = str(user_id_str)
    with get_db_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET welcome_seen = TRUE WHERE tg_id = %s;
            """, (str_uid,))
    return {"success": True, "welcome_seen": True, "is_new_user": False}


def calculate_user_effective_stats(user_data, game_settings=None, now_dt=None):
    """فحص وتحديث صلاحية اشتراك الباقة أو البوت وتحديث حالة bot_active"""
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    raw_bot_flag = to_bool(user_data.get("bot_active", user_data.get("has_bot", False)))
    
    vip_info = user_data.get("vip_status")
    if isinstance(vip_info, dict):
        vip_bot = to_bool(vip_info.get("auto_bot", vip_info.get("bot_active", False)))
        raw_bot_flag = raw_bot_flag or vip_bot

    exp_dt = get_bot_expiration_dt(user_data)

    is_active = False
    if raw_bot_flag:
        if exp_dt is None or exp_dt > now_dt:
            is_active = True

    user_data["balance"] = min(max(0.0, float(user_data.get("balance", 0.0))), MAX_SAFE_BALANCE)
    user_data["usd_balance"] = min(max(0.0, float(user_data.get("usd_balance", 0.0))), 1000000.0)
    user_data["hourly_rate"] = min(max(0.10, float(user_data.get("hourly_rate", 0.10))), MAX_SAFE_HOURLY_RATE)

    user_data["bot_active"] = is_active
    user_data["is_auto_bot_active"] = is_active
    return user_data


def get_or_create_user_farm_data(user_id_str):
    """جلب وتجهيز كافة بيانات المستخدم الخاصة بالمزرعة وتوليد الأرقام اللحظية بدون تعليق"""
    str_uid = str(user_id_str)
    now = datetime.now(timezone.utc)
    game_settings = get_game_settings()
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    base_free_rate = float(mining_cfg.get("base_free_rate", 0.10))

    user_data = get_user(str_uid)
    if not user_data:
        user_data = init_user(str_uid)
        if not user_data:
            user_data = create_default_user_data_dict(str_uid, game_settings, now)

    db_updates = {}
    
    if not user_data.get("welcome_seen"):
        has_progress = bool(user_data.get("upgrades") or user_data.get("last_daily_claim_date") or user_data.get("last_boost_time"))
        db_updates["welcome_seen"] = has_progress

    current_hr = float(user_data.get("hourly_rate", 0.0))
    if current_hr < base_free_rate and not user_data.get("upgrades"):
        db_updates["hourly_rate"] = base_free_rate
    elif current_hr > MAX_SAFE_HOURLY_RATE:
        db_updates["hourly_rate"] = MAX_SAFE_HOURLY_RATE

    if not user_data.get("last_claim_time"):
        db_updates["last_claim_time"] = format_iso(now)

    expected_max_cap = calculate_user_max_cap(user_data, game_settings)
    if user_data.get("max_cap") != expected_max_cap:
        db_updates["max_cap"] = expected_max_cap

    if db_updates:
        with get_db_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                set_clauses = [f"{k} = %s" for k in db_updates.keys()]
                params = list(db_updates.values())
                params.append(str_uid)
                cur.execute(f"UPDATE users SET {', '.join(set_clauses)} WHERE tg_id = %s", tuple(params))
        user_data.update(db_updates)

    user_data = calculate_user_effective_stats(user_data, game_settings, now)

    expected_max_cap = calculate_user_max_cap(user_data, game_settings)
    user_data["max_cap"] = expected_max_cap
    user_data["balance"] = round(min(float(user_data.get("balance", 0.0)), MAX_SAFE_BALANCE), 8)
    user_data["usd_balance"] = round(float(user_data.get("usd_balance", 0.0)), 8)
    user_data["mined_points"] = round(float(user_data.get("mined_points", user_data.get("total_mined", 0.0))), 8)
    user_data["total_mined"] = user_data["mined_points"]

    last_claim_dt = safe_parse_datetime(user_data.get("last_claim_time"), now)
    if not last_claim_dt or last_claim_dt > (now + timedelta(seconds=FUTURE_SKEW_TOLERANCE_SEC)):
        last_claim_dt = now

    is_bot_active = user_data.get("bot_active", False)
    exp_dt = get_bot_expiration_dt(user_data)
    hourly_rate = min(float(user_data.get("hourly_rate", 0.10)), MAX_SAFE_HOURLY_RATE)
    last_boost_str = user_data.get("last_boost_time")

    auto_claimed_amount = 0.0
    auto_claim_updates = {}

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
            user_data["last_claim_time"] = format_iso(bot_end_dt)

            auto_claim_updates["balance"] = user_data["balance"]
            auto_claim_updates["mined_points"] = user_data["mined_points"]
            auto_claim_updates["total_mined"] = user_data["total_mined"]
            auto_claim_updates["last_claim_time"] = user_data["last_claim_time"]

            if bot_end_dt < now:
                post_bot_mined = _calculate_interval_mined(hourly_rate, bot_end_dt, now, last_boost_str)
                user_data["unclaimed"] = round(min(post_bot_mined, expected_max_cap), 8)
                user_data["base_unclaimed"] = user_data["unclaimed"]
        else:
            total_mined_so_far = _calculate_interval_mined(hourly_rate, last_claim_dt, now, last_boost_str)
            unclaimed_val = round(min(total_mined_so_far, expected_max_cap), 8)
            user_data["unclaimed"] = unclaimed_val
            user_data["base_unclaimed"] = unclaimed_val
    else:
        unclaimed_val = calculate_accrued_mined(user_data, now, expected_max_cap)
        user_data["unclaimed"] = unclaimed_val
        user_data["base_unclaimed"] = unclaimed_val

    if auto_claim_updates:
        try:
            with get_db_connection() as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users SET balance = %s, mined_points = %s, total_mined = %s, last_claim_time = %s
                        WHERE tg_id = %s;
                    """, (user_data["balance"], user_data["mined_points"], user_data["total_mined"], user_data["last_claim_time"], str_uid))
        except Exception as e:
            print(f"⚠️ Error updating offline farm calculations: {e}")

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
    """تجميع الرصيد المعدن مع حماية ACID لمنع السباق وقفل الصفوف FOR UPDATE مع إصلاح مشكلة الـ 15 ثانية"""
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    cooldown_seconds = int(mining_cfg.get("claim_cooldown_seconds", 15))

    with get_db_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (str_uid,))
                user_data = cur.fetchone()
                now = datetime.now(timezone.utc)
                today_utc_str = now.strftime('%Y-%m-%d')

                if not user_data:
                    conn.rollback()
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                last_claim_str = user_data.get("last_claim_time")
                
                if last_claim_str:
                    last_claim = safe_parse_datetime(last_claim_str)
                    if last_claim:
                        seconds_passed = (now - last_claim).total_seconds()
                        if seconds_passed < cooldown_seconds:
                            conn.rollback()
                            rem = round(cooldown_seconds - seconds_passed, 1)
                            return {
                                "success": False, 
                                "error": f"الرجاء الانتظار {cooldown_seconds} ثانية قبل التجميع مجدداً",
                                "remaining_seconds": rem
                            }

                max_cap = calculate_user_max_cap(user_data, game_settings)
                mined_amount = calculate_accrued_mined(user_data, now, max_cap)

                if mined_amount <= 0:
                    conn.rollback()
                    return {"success": False, "error": "المخزن فارغ حالياً"}

                current_balance = float(user_data.get("balance", 0.0))
                current_usd_balance = float(user_data.get("usd_balance", 0.0))
                current_mined_points = float(user_data.get("mined_points", user_data.get("total_mined", 0.0)))

                new_balance = round(min(current_balance + mined_amount, MAX_SAFE_BALANCE), 8)
                new_mined_points = round(current_mined_points + mined_amount, 8)
                now_iso = format_iso(now)

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, mined_points = %s, total_mined = %s, last_claim_time = %s, last_claim_ad_date = %s
                    WHERE tg_id = %s;
                """, (new_balance, new_mined_points, new_mined_points, now_iso, today_utc_str, str_uid))

                conn.commit()

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
                    "claimed_amount": mined_amount
                }
        except Exception as e:
            conn.rollback()
            return {"success": False, "error": f"تعذر تنفيذ التجميع: {str(e)}"}


def buy_upgrade_db(user_id_str, level):
    """شراء ترقية سرعة التعدين مع فحص التدرج، حدود الرصيد والمعاملات الآمنة"""
    level_str = str(level).strip()
    str_uid = str(user_id_str)
    game_settings = get_game_settings()

    upgrade_configs = game_settings.get("upgrade_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
    if level_str not in upgrade_configs:
        return {"success": False, "error": "بيانات المستوى غير متوفرة"}

    level_cfg = upgrade_configs[level_str]
    cost_zn = float(level_cfg.get("cost_zn", 0))
    cost_usd = float(level_cfg.get("cost_usd", 0.0))
    rate_bonus = round(float(level_cfg.get("rate_bonus", 0)), 2)

    with get_db_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    conn.rollback()
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                current_balance = float(user_data.get("balance", 0.0))
                current_usd_balance = float(user_data.get("usd_balance", 0.0))

                if current_balance < cost_zn:
                    conn.rollback()
                    return {"success": False, "error": f"رصيد العملات غير كافٍ! سعر الترقية {cost_zn:,.0f} ZN"}

                if cost_usd > 0 and current_usd_balance < cost_usd:
                    conn.rollback()
                    return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

                upgrades = user_data.get("upgrades", {})
                if not isinstance(upgrades, dict):
                    upgrades = {}

                lvl_key = f"lvl{level_str}"
                current_count = int(upgrades.get(lvl_key, 0))

                if current_count >= 15:
                    conn.rollback()
                    return {"success": False, "error": "لقد وصلت للحد الأقصى للشراء لهذا المستوى (15/15)"}

                if int(level_str) > 1:
                    prev_lvl = str(int(level_str) - 1)
                    prev_key = f"lvl{prev_lvl}"
                    prev_count = int(upgrades.get(prev_key, 0))
                    if prev_count == 0:
                        conn.rollback()
                        return {"success": False, "error": "يجب شراء المستوى السابق أولاً"}

                max_cap = calculate_user_max_cap(user_data, game_settings)

                new_balance = round(max(0.0, current_balance - cost_zn), 8)
                new_usd_balance = round(max(0.0, current_usd_balance - cost_usd), 8)
                current_hourly_rate = float(user_data.get("hourly_rate", 0.10))
                
                new_hourly_rate = round(min(current_hourly_rate + rate_bonus, MAX_SAFE_HOURLY_RATE), 4)

                upgrades[lvl_key] = current_count + 1
                total_upgrades_count = sum(int(v) for v in upgrades.values() if isinstance(v, (int, float)))
                last_claim_str = user_data.get("last_claim_time") or format_iso(now)

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, usd_balance = %s, hourly_rate = %s, upgrades = %s, upgrades_count = %s
                    WHERE tg_id = %s;
                """, (new_balance, new_usd_balance, new_hourly_rate, Json(upgrades), total_upgrades_count, str_uid))

                conn.commit()

                user_data["hourly_rate"] = new_hourly_rate
                updated_unclaimed = calculate_accrued_mined(user_data, now, max_cap)

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
                    "server_time": format_iso(now)
                }
        except Exception as e:
            conn.rollback()
            return {"success": False, "error": f"تعذر تنفيذ عملية الترقية: {str(e)}"}


def buy_storage_db(user_id_str):
    """شراء ترقية سعة التخزين مع حماية المعاملات الآمنة"""
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    storage_cfgs = game_settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_capacities"]

    with get_db_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    conn.rollback()
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)

                current_level = int(user_data.get("storage_level", 0))
                next_level = current_level + 1

                if next_level > 8 or str(next_level) not in storage_cfgs:
                    conn.rollback()
                    return {"success": False, "error": "المخزن في أقصى مستوى بالفعل (MAX)"}

                next_cfg = storage_cfgs[str(next_level)]
                if isinstance(next_cfg, dict):
                    cost_zn = float(next_cfg.get("cost_zn", 0.0))
                    cost_usd = float(next_cfg.get("cost_usd", 0.0))
                    new_capacity = float(next_cfg.get("capacity", 0.5))
                else:
                    cost_zn = 0.0
                    cost_usd = 0.0
                    new_capacity = float(next_cfg)

                current_balance = float(user_data.get("balance", 0.0))
                current_usd_balance = float(user_data.get("usd_balance", 0.0))

                if current_balance < cost_zn:
                    conn.rollback()
                    return {"success": False, "error": f"رصيدك غير كافٍ! سعر ترقية المخزن {cost_zn:,.0f} ZN"}

                if cost_usd > 0 and current_usd_balance < cost_usd:
                    conn.rollback()
                    return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

                extra_cap = float(user_data.get("extra_storage", 0.0))
                new_max_cap = min(round(new_capacity + extra_cap, 4), MAX_SAFE_STORAGE_CAP)
                new_balance = round(max(0.0, current_balance - cost_zn), 8)
                new_usd_balance = round(max(0.0, current_usd_balance - cost_usd), 8)

                mined_amount = calculate_accrued_mined(user_data, now, new_max_cap)
                last_claim_str = user_data.get("last_claim_time") or format_iso(now)

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, usd_balance = %s, storage_level = %s, max_cap = %s
                    WHERE tg_id = %s;
                """, (new_balance, new_usd_balance, next_level, new_max_cap, str_uid))

                conn.commit()

                return {
                    "success": True,
                    "new_balance": new_balance,
                    "new_usd_balance": new_usd_balance,
                    "storage_level": next_level,
                    "max_cap": new_max_cap,
                    "last_claim_time": last_claim_str,
                    "base_unclaimed": mined_amount,
                    "unclaimed": mined_amount,
                    "server_time": format_iso(now)
                }
        except Exception as e:
            conn.rollback()
            return {"success": False, "error": f"تعذر إتمام ترقية المخزن: {str(e)}"}


def claim_daily_reward_db(user_id_str):
    """استلام المكافأة اليومية وتسجيل التاريخ والوقت بدقة وعداد المرات للمسابقات"""
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))

    with get_db_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    conn.rollback()
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                now_iso = format_iso(now)
                today_str = now.strftime('%Y-%m-%d')
                yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')

                last_daily_claim = user_data.get("last_daily_claim_date")

                if last_daily_claim == today_str:
                    conn.rollback()
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

                # تحديث عداد المكافآت اليومية وسجل التاريخ الكامل بالثانية للمسابقات
                daily_claims_cnt = int(user_data.get("daily_claims_count", 0)) + 1
                daily_hist = user_data.get("daily_history", [])
                if not isinstance(daily_hist, list):
                    daily_hist = []

                daily_hist.append({
                    "claimed_at": now_iso,
                    "date": today_str,
                    "day": effective_daily_day,
                    "reward": reward_amount
                })

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, daily_day = %s, daily_streak = %s, last_daily_claim_date = %s,
                        ads_watched = %s, daily_claims_count = %s, daily_history = %s
                    WHERE tg_id = %s;
                """, (new_balance, effective_daily_day, effective_daily_day, today_str, new_ads_watched, daily_claims_cnt, Json(daily_hist), str_uid))

                conn.commit()

                return {
                    "success": True,
                    "new_balance": new_balance,
                    "new_usd_balance": round(current_usd_balance, 8),
                    "reward_amount": reward_amount,
                    "daily_day": effective_daily_day,
                    "daily_streak": effective_daily_day,
                    "last_daily_claim_date": today_str,
                    "ads_watched": new_ads_watched,
                    "daily_claims_count": daily_claims_cnt,
                    "server_time": now_iso
                }
        except Exception as e:
            conn.rollback()
            return {"success": False, "error": f"تعذر استلام المكافأة اليومية: {str(e)}"}


def claim_daily_boost_db(user_id_str):
    """تفعيل المعزز اليومي مع تسجيل تاريخ وسجل الضغطات بالثانية والعداد للمسابقات"""
    str_uid = str(user_id_str)
    game_settings = get_game_settings()

    with get_db_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    conn.rollback()
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                now_iso = format_iso(now)
                today_str = now.strftime('%Y-%m-%d')
                last_boost_str = user_data.get("last_boost_time")

                if last_boost_str:
                    last_boost = safe_parse_datetime(last_boost_str)
                    if last_boost:
                        elapsed_seconds = (now - last_boost).total_seconds()
                        cooldown_seconds = 3 * 3600  # 3 ساعات انتظار
                        if elapsed_seconds < cooldown_seconds and elapsed_seconds >= 0:
                            remaining_seconds = int(cooldown_seconds - elapsed_seconds)
                            rem_hours = remaining_seconds // 3600
                            rem_mins = (remaining_seconds % 3600) // 60
                            time_str = f"{rem_hours} ساعة و {rem_mins} دقيقة" if rem_hours > 0 else f"{rem_mins} دقيقة"
                            conn.rollback()
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

                # تسجيل عدد مرات المعزز والسجل الزمني الدقيق
                boost_claims_cnt = int(user_data.get("boost_claims_count", 0)) + 1
                boost_hist = user_data.get("boost_history", [])
                if not isinstance(boost_hist, list):
                    boost_hist = []

                boost_hist.append({
                    "claimed_at": now_iso,
                    "date": today_str
                })

                cur.execute("""
                    UPDATE users 
                    SET last_boost_time = %s, ads_watched = %s, boost_claims_count = %s, boost_history = %s
                    WHERE tg_id = %s;
                """, (now_iso, new_ads, boost_claims_cnt, Json(boost_hist), str_uid))

                conn.commit()

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
                    "boost_claims_count": boost_claims_cnt,
                    "server_time": now_iso
                }
        except Exception as e:
            conn.rollback()
            return {"success": False, "error": f"تعذر تفعيل التعزيز: {str(e)}"}


def get_mining_leaderboard_db(limit=10):
    """جلب قائمة المتصدرين لأفضل المعدنين مباشرة من Supabase"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tg_id, first_name, mined_points, total_mined, balance, hourly_rate
                    FROM users
                    ORDER BY mined_points DESC, total_mined DESC
                    LIMIT %s;
                """, (limit,))
                rows = cur.fetchall()
                leaderboard = []
                for rank, row in enumerate(rows, start=1):
                    total_m = float(row.get("mined_points") or row.get("total_mined") or 0.0)
                    leaderboard.append({
                        "rank": rank,
                        "tg_id": str(row["tg_id"]),
                        "name": row.get("first_name") or f"المستخدم {str(row['tg_id'])[:4]}",
                        "total_mined": round(min(total_m, MAX_SAFE_BALANCE), 8),
                        "mined_points": round(min(total_m, MAX_SAFE_BALANCE), 8),
                        "balance": round(min(float(row.get("balance", 0.0)), MAX_SAFE_BALANCE), 8),
                        "hourly_rate": round(min(float(row.get("hourly_rate", 0.10)), MAX_SAFE_HOURLY_RATE), 4)
                    })
                return leaderboard
    except Exception as e:
        print(f"❌ Error getting leaderboard: {e}")
        return []

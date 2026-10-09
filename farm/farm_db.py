# -*- coding: utf-8 -*-
import json
import time
from datetime import datetime, timezone, timedelta
from psycopg2.extras import RealDictCursor, Json
from database import get_db_connection

# ==================== ثوابت وحدود الأمان القصوى ====================
MAX_SAFE_BALANCE = 1000000000.0     # الحد الأقصى المسموح به للرصيد (1 مليار ZN)
MAX_SAFE_HOURLY_RATE = 500.0        # الحد الأقصى لمعدل التعدين بالساعة (500 ZN/h)
MAX_SAFE_STORAGE_CAP = 5000.0       # الحد الأقصى لسعة المخزن (5000 ZN)
FUTURE_SKEW_TOLERANCE_SEC = 300     # التسامح المسموح لفرق التوقيت المستقبلي (5 دقائق)


def to_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    if isinstance(val, (int, float)):
        return val != 0
    return False


def safe_parse_datetime(dt_raw, default_dt=None):
    if dt_raw is None:
        return default_dt
    try:
        if isinstance(dt_raw, (int, float)):
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


# ==================== Caching للإعدادات ====================
_SETTINGS_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 15

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
    global _SETTINGS_CACHE
    now_ts = time.time()
    
    if not force_refresh and _SETTINGS_CACHE["data"] and (now_ts - _SETTINGS_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _SETTINGS_CACHE["data"]

    _SETTINGS_CACHE = {"data": DEFAULT_GAME_SETTINGS, "timestamp": now_ts}
    return DEFAULT_GAME_SETTINGS


def parse_daily_rewards(rewards_data):
    if isinstance(rewards_data, list) and len(rewards_data) > 0:
        return [max(0.0, min(float(x), 1000.0)) for x in rewards_data]
    if isinstance(rewards_data, dict):
        res = []
        for i in range(1, 31):
            val = rewards_data.get(f"day_{i}") or rewards_data.get(str(i)) or DEFAULT_GAME_SETTINGS["daily_rewards"][i-1]
            res.append(max(0.0, min(float(val), 1000.0)))
        return res
    return [float(x) for x in DEFAULT_GAME_SETTINGS["daily_rewards"]]


def get_base_storage_capacity(storage_level, settings=None):
    if not settings:
        settings = get_game_settings()
    try:
        lvl = int(storage_level)
    except (ValueError, TypeError):
        lvl = 0
    lvl = max(0, min(lvl, 8))

    caps = settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_capacities"]
    val = caps.get(str(lvl)) or caps.get(lvl)

    if isinstance(val, dict):
        return min(float(val.get("capacity", 0.5)), MAX_SAFE_STORAGE_CAP)
    elif val is not None:
        return min(float(val), MAX_SAFE_STORAGE_CAP)
    return 0.5


def calculate_user_max_cap(user_data, settings=None):
    if not settings:
        settings = get_game_settings()
    stg_lvl = user_data.get("storage_level", 0)
    base_cap = get_base_storage_capacity(stg_lvl, settings)
    extra_cap = max(0.0, float(user_data.get("extra_storage", 0.0)))
    total_cap = base_cap + extra_cap
    return min(round(total_cap, 4), MAX_SAFE_STORAGE_CAP)


def get_bot_expiration_dt(user_data):
    vip_info = user_data.get("vip_status")
    expires_at_raw = None

    if isinstance(vip_info, dict):
        expires_at_raw = vip_info.get("expires_at") or vip_info.get("vip_expires_at") or vip_info.get("bot_expires_at")
    
    if not expires_at_raw:
        expires_at_raw = user_data.get("bot_expires_at") or user_data.get("expires_at") or user_data.get("vip_expires_at")

    return safe_parse_datetime(expires_at_raw)


def _calculate_interval_mined(hourly_rate, start_dt, end_dt, last_boost_str=None):
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
    str_uid = str(user_id_str)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET welcome_seen = TRUE WHERE tg_id = %s", (str_uid,))
        return {"success": True, "welcome_seen": True, "is_new_user": False}
    except Exception as e:
        print(f"❌ خطأ dismiss_welcome_db: {e}")
        return {"success": False, "error": str(e)}


def calculate_user_effective_stats(user_data, game_settings=None, now_dt=None):
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    raw_bot_flag = to_bool(user_data.get("bot_active", user_data.get("has_bot", False)))
    vip_info = user_data.get("vip_status")
    if isinstance(vip_info, dict):
        raw_bot_flag = raw_bot_flag or to_bool(vip_info.get("auto_bot", False))

    exp_dt = get_bot_expiration_dt(user_data)
    is_active = raw_bot_flag and (exp_dt is None or exp_dt > now_dt)

    user_data["balance"] = min(max(0.0, float(user_data.get("balance", 0.0))), MAX_SAFE_BALANCE)
    user_data["usd_balance"] = min(max(0.0, float(user_data.get("usd_balance", 0.0))), 1000000.0)
    user_data["hourly_rate"] = min(max(0.10, float(user_data.get("hourly_rate", 0.10))), MAX_SAFE_HOURLY_RATE)
    user_data["bot_active"] = is_active
    user_data["is_auto_bot_active"] = is_active
    return user_data


def get_or_create_user_farm_data(user_id_str):
    str_uid = str(user_id_str)
    now = datetime.now(timezone.utc)
    game_settings = get_game_settings()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s", (str_uid,))
                user_row = cur.fetchone()

                if not user_row:
                    user_data = create_default_user_data_dict(str_uid, game_settings, now)
                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, balance, usd_balance, hourly_rate, storage_level, last_claim_time)
                        VALUES (%s, %s, %s, 0.0, 0.0, %s, 0, %s)
                        ON CONFLICT (tg_id) DO NOTHING;
                    """, (str_uid, str_uid, str_uid, user_data["hourly_rate"], now.isoformat()))
                else:
                    user_data = dict(user_row)

        if isinstance(user_data.get('upgrades'), str):
            try: user_data['upgrades'] = json.loads(user_data['upgrades'])
            except Exception: user_data['upgrades'] = {}

        user_data = calculate_user_effective_stats(user_data, game_settings, now)
        expected_max_cap = calculate_user_max_cap(user_data, game_settings)
        user_data["max_cap"] = expected_max_cap

        last_claim_dt = safe_parse_datetime(user_data.get("last_claim_time"), now) or now
        unclaimed_val = calculate_accrued_mined(user_data, now, expected_max_cap)
        user_data["unclaimed"] = unclaimed_val
        user_data["base_unclaimed"] = unclaimed_val
        user_data["auto_claimed_amount"] = 0.0

        today_str = now.strftime('%Y-%m-%d')
        yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        last_daily_claim = str(user_data.get("last_daily_claim_date") or '')
        raw_daily_day = int(user_data.get("daily_day") or 1)

        if last_daily_claim == today_str:
            effective_daily_day = raw_daily_day
        elif last_daily_claim == yesterday_str:
            effective_daily_day = min(raw_daily_day + 1, 30)
        else:
            effective_daily_day = 1

        user_data["daily_day"] = effective_daily_day
        user_data["daily_streak"] = effective_daily_day

        return user_data, game_settings, now

    except Exception as e:
        print(f"❌ خطأ get_or_create_user_farm_data: {e}")
        default_data = create_default_user_data_dict(str_uid, game_settings, now)
        return default_data, game_settings, now


def claim_mined_tokens_db(user_id_str):
    str_uid = str(user_id_str)
    now = datetime.now(timezone.utc)
    game_settings = get_game_settings()
    cooldown = int(game_settings.get("mining_config", {}).get("claim_cooldown_seconds", 15))

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()
                if not user_data:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_dict = dict(user_data)
                last_claim = safe_parse_datetime(user_dict.get("last_claim_time"))
                if last_claim and (now - last_claim).total_seconds() < cooldown:
                    return {"success": False, "error": f"الرجاء الانتظار {cooldown} ثانية قبل التجميع مجدداً"}

                max_cap = calculate_user_max_cap(user_dict, game_settings)
                mined_amount = calculate_accrued_mined(user_dict, now, max_cap)

                if mined_amount <= 0:
                    return {"success": False, "error": "المخزن فارغ حالياً"}

                new_balance = round(min(float(user_dict.get("balance", 0.0)) + mined_amount, MAX_SAFE_BALANCE), 8)
                new_mined_points = round(float(user_dict.get("mined_points", 0.0)) + mined_amount, 8)
                now_iso = now.isoformat()

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, mined_points = %s, total_mined = %s, last_claim_time = %s 
                    WHERE tg_id = %s
                """, (new_balance, new_mined_points, new_mined_points, now_iso, str_uid))

                return {
                    "success": True,
                    "new_balance": new_balance,
                    "new_usd_balance": round(float(user_dict.get("usd_balance", 0.0)), 8),
                    "total_mined": new_mined_points,
                    "mined_points": new_mined_points,
                    "last_claim_time": now_iso,
                    "base_unclaimed": 0.0,
                    "unclaimed": 0.0,
                    "claimed_amount": mined_amount
                }
    except Exception as e:
        print(f"❌ خطأ claim_mined_tokens_db: {e}")
        return {"success": False, "error": f"تعذر تنفيذ التجميع: {str(e)}"}


def buy_upgrade_db(user_id_str, level):
    level_str = str(level).strip()
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    upgrade_configs = game_settings.get("upgrade_config", DEFAULT_GAME_SETTINGS["upgrade_config"])

    if level_str not in upgrade_configs:
        return {"success": False, "error": "بيانات المستوى غير متوفرة"}

    level_cfg = upgrade_configs[level_str]
    cost_zn = float(level_cfg.get("cost_zn", 0.0))
    cost_usd = float(level_cfg.get("cost_usd", 0.0))
    rate_bonus = float(level_cfg.get("rate_bonus", 0.0))

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_row = cur.fetchone()
                if not user_row:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_row)
                current_balance = float(user_data.get("balance", 0.0))
                current_usd = float(user_data.get("usd_balance", 0.0))

                if current_balance < cost_zn:
                    return {"success": False, "error": f"رصيد العملات غير كافٍ! سعر الترقية {cost_zn:,.0f} ZN"}
                if cost_usd > 0 and current_usd < cost_usd:
                    return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

                upgrades = user_data.get("upgrades") or {}
                if isinstance(upgrades, str):
                    try: upgrades = json.loads(upgrades)
                    except Exception: upgrades = {}

                lvl_key = f"lvl{level_str}"
                current_count = int(upgrades.get(lvl_key, 0))
                if current_count >= 15:
                    return {"success": False, "error": "وصلت للحد الأقصى للشراء لهذا المستوى (15/15)"}

                new_balance = round(max(0.0, current_balance - cost_zn), 8)
                new_usd = round(max(0.0, current_usd - cost_usd), 8)
                new_rate = round(min(float(user_data.get("hourly_rate", 0.10)) + rate_bonus, MAX_SAFE_HOURLY_RATE), 4)

                upgrades[lvl_key] = current_count + 1
                total_upgrades = sum(int(v) for v in upgrades.values() if isinstance(v, (int, float)))

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, usd_balance = %s, hourly_rate = %s, upgrades = %s 
                    WHERE tg_id = %s
                """, (new_balance, new_usd, new_rate, Json(upgrades), str_uid))

                return {
                    "success": True,
                    "new_balance": new_balance,
                    "new_usd_balance": new_usd,
                    "new_hourly_rate": new_rate,
                    "upgrades": upgrades,
                    "upgrades_count": total_upgrades
                }
    except Exception as e:
        print(f"❌ خطأ buy_upgrade_db: {e}")
        return {"success": False, "error": str(e)}


def buy_storage_db(user_id_str):
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    storage_cfgs = game_settings.get("storage_capacities", DEFAULT_GAME_SETTINGS["storage_capacities"])

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_row = cur.fetchone()
                if not user_row:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_row)
                current_level = int(user_data.get("storage_level", 0))
                next_level = current_level + 1

                if next_level > 8 or str(next_level) not in storage_cfgs:
                    return {"success": False, "error": "المخزن في أقصى مستوى بالفعل (MAX)"}

                next_cfg = storage_cfgs[str(next_level)]
                cost_zn = float(next_cfg.get("cost_zn", 0.0))
                cost_usd = float(next_cfg.get("cost_usd", 0.0))
                new_capacity = float(next_cfg.get("capacity", 0.5))

                current_balance = float(user_data.get("balance", 0.0))
                current_usd = float(user_data.get("usd_balance", 0.0))

                if current_balance < cost_zn:
                    return {"success": False, "error": f"رصيدك غير كافٍ! سعر الترقية {cost_zn:,.0f} ZN"}
                if cost_usd > 0 and current_usd < cost_usd:
                    return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

                new_balance = round(max(0.0, current_balance - cost_zn), 8)
                new_usd = round(max(0.0, current_usd - cost_usd), 8)

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, usd_balance = %s, storage_level = %s 
                    WHERE tg_id = %s
                """, (new_balance, new_usd, next_level, str_uid))

                return {
                    "success": True,
                    "new_balance": new_balance,
                    "new_usd_balance": new_usd,
                    "storage_level": next_level,
                    "max_cap": new_capacity
                }
    except Exception as e:
        print(f"❌ خطأ buy_storage_db: {e}")
        return {"success": False, "error": str(e)}


def claim_daily_reward_db(user_id_str):
    str_uid = str(user_id_str)
    now = datetime.now(timezone.utc)
    today_str = now.strftime('%Y-%m-%d')
    game_settings = get_game_settings()
    parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_row = cur.fetchone()
                if not user_row:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_row)
                last_claim = str(user_data.get("last_daily_claim_date") or '')

                if last_claim == today_str:
                    return {"success": False, "error": "لقد قمت باستلام المكافأة اليوم بالفعل"}

                raw_daily_day = int(user_data.get("daily_day") or 1)
                reward_index = min(max(raw_daily_day - 1, 0), 29)
                reward_amount = float(parsed_rewards[reward_index])

                new_balance = round(min(float(user_data.get("balance", 0.0)) + reward_amount, MAX_SAFE_BALANCE), 8)

                cur.execute("""
                    UPDATE users 
                    SET balance = %s, last_daily_claim_date = %s 
                    WHERE tg_id = %s
                """, (new_balance, today_str, str_uid))

                return {
                    "success": True,
                    "new_balance": new_balance,
                    "reward_amount": reward_amount,
                    "daily_day": raw_daily_day,
                    "last_daily_claim_date": today_str
                }
    except Exception as e:
        print(f"❌ خطأ claim_daily_reward_db: {e}")
        return {"success": False, "error": str(e)}


def claim_daily_boost_db(user_id_str):
    str_uid = str(user_id_str)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    today_str = now.strftime('%Y-%m-%d')

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_boost_time = %s, last_boost_date = %s WHERE tg_id = %s", (now_iso, today_str, str_uid))

        return {
            "success": True,
            "type": "speed",
            "boost_rate_bonus": 0.10,
            "last_boost_time": now_iso,
            "last_boost_date": today_str
        }
    except Exception as e:
        print(f"❌ خطأ claim_daily_boost_db: {e}")
        return {"success": False, "error": str(e)}


def get_mining_leaderboard_db(limit=10):
    try:
        safe_limit = max(1, min(int(limit or 10), 50))
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tg_id, first_name, mined_points, balance, hourly_rate
                    FROM users
                    ORDER BY mined_points DESC
                    LIMIT %s
                """, (safe_limit,))
                rows = cur.fetchall()

                leaderboard = []
                for rank, row in enumerate(rows, start=1):
                    leaderboard.append({
                        "rank": rank,
                        "tg_id": str(row.get("tg_id")),
                        "name": str(row.get("first_name") or "لاعب"),
                        "mined_points": round(float(row.get("mined_points") or 0.0), 8),
                        "balance": round(float(row.get("balance") or 0.0), 8),
                        "hourly_rate": round(float(row.get("hourly_rate") or 0.10), 4)
                    })

                return leaderboard
    except Exception as e:
        print(f"❌ خطأ get_mining_leaderboard_db: {e}")
        return []

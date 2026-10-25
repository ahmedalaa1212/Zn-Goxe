# -*- coding: utf-8 -*-
"""
farm_db.py - موديول إدارة المزرعة والتعدين المربوط بـ Supabase (PostgreSQL)
مُعالج بالكامل لمشاكل السعة، باقات الـ VIP (×2)، وبوت التجميع التلقائي للأوفلاين ⚡
✅ Atomic Updates & COALESCE لمنع الأرصدة السالبة وقيم Null
✅ تجميع تلقائي مستمر بدون سقف مخزن طوال فترة إغلاق البوت للمشتركين في الباقات
✅ فك تشفير آمن لـ vip_status ومراقبة دقيقة لوقت انتهاء الباقة (expires_at)
✅ حماية صارمة لسرعة التعدين، منع تخطي المستويات، وتوزيع عمولات الإحالة (10% / 12% VIP)
"""
import time
import json
import copy
from datetime import datetime, timezone, timedelta
from psycopg2.extras import RealDictCursor, Json
from database import get_db_connection, format_iso

# استيراد دوال نظام الأصدقاء لتوزيع أرباح التعدين ومزامنة الترقيات
try:
    from friends.friends_db import (
        add_referral_reward,
        sync_friend_upgrades_db,
        get_friends_data_db,
        get_user_friends as _get_friends_list_From_friends_db,
        claim_ref_earnings_db
    )
except Exception as _imp_err:
    print(f"⚠️ تنبيه استيراد friends_db داخل farm_db: {_imp_err}")
    add_referral_reward = None
    sync_friend_upgrades_db = None
    get_friends_data_db = None
    _get_friends_list_From_friends_db = None
    claim_ref_earnings_db = None

# ==================== ثوابت وحدود الأمان القصوى (Sanity Checks Limits) ====================
MAX_SAFE_BALANCE = 1000000000.0     # الحد الأقصى المسموح به للرصيد (1 مليار ZN)
MAX_SAFE_HOURLY_RATE = 5000.0       # الحد الأقصى لمعدل التعدين بالساعة (يستوعب كافة الترقيات القصوى)
MAX_SAFE_STORAGE_CAP = 50000.0      # الحد الأقصى لسعة المخزن (يستوعب المستوى الأقصى مع الضعف ×2)
FUTURE_SKEW_TOLERANCE_SEC = 300     # التسامح المسموح لفرق التوقيت المستقبلي (5 دقائق)
MIN_OFFLINE_AUTO_CLAIM_SEC = 30     # الحد الأدنى لثواني الأوفلاين لتحويل الرصيد تلقائياً عند فتح البوت


def to_bool(val):
    """تحويل قيم البوليان بشكل صحيح وآمن من القراءات المختلفة"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "ok", "success")
    if isinstance(val, (int, float)):
        return val != 0
    return False


def parse_json_field(raw_val, default_factory=dict):
    """فك تشفير حقول JSON/JSONB بأمان تام حتى لو كانت مخزنة كنص مزدوج"""
    if raw_val is None:
        return default_factory()
    if isinstance(raw_val, (dict, list)):
        return copy.deepcopy(raw_val)
    if isinstance(raw_val, str):
        s = raw_val.strip()
        if not s:
            return default_factory()
        try:
            parsed = json.loads(s)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            if isinstance(parsed, type(default_factory())):
                return parsed
        except Exception:
            pass
    return default_factory()


def safe_parse_datetime(dt_raw, default_dt=None):
    """معالجة آمنة لتحويل أي تاريخ أو ختم زمني إلى UTC"""
    if dt_raw is None:
        return default_dt
    try:
        if isinstance(dt_raw, (int, float)):
            ts = dt_raw / 1000.0 if dt_raw > 10000000000 else dt_raw
            if ts < 0 or ts > 4102444800:
                return default_dt
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(dt_raw, datetime):
            if dt_raw.tzinfo is None:
                return dt_raw.replace(tzinfo=timezone.utc)
            return dt_raw.astimezone(timezone.utc)
        else:
            s = str(dt_raw).strip().replace(' ', 'T')
            if s.endswith('Z'):
                s = s[:-1] + '+00:00'
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        return default_dt


def _resolve_referrer_id(cur, user_data, str_uid):
    """استخراج معرف الداعي (المُحيل) سواء من جدول users أو جدول user_friends"""
    ref_id = user_data.get("ref_by") or user_data.get("referred_by")
    if ref_id:
        clean_ref = str(ref_id).strip().replace("ref_", "")
        if clean_ref and clean_ref.lower() not in ("none", "null") and clean_ref != str_uid:
            return clean_ref

    try:
        cur.execute("SELECT referrer_id FROM user_friends WHERE friend_id = %s LIMIT 1", (str_uid,))
        r = cur.fetchone()
        if r:
            val = r.get("referrer_id") if isinstance(r, dict) else r[0]
            if val and str(val).strip() != str_uid:
                return str(val).strip()
    except Exception:
        pass
    return None


def _dispatch_referral_commission(ref_id, str_uid, mined_amount, upgrades_count=None, user_name=None):
    """إرسال عمولة التعدين (10% عادي أو 12% VIP) للداعي بأمان دون تعطيل عملية الجمع"""
    if not ref_id or not mined_amount or float(mined_amount) <= 0:
        return
    if callable(add_referral_reward):
        try:
            add_referral_reward(
                referrer_id=ref_id,
                user_id=str_uid,
                mined_amount=float(mined_amount),
                user_upgrades_count=upgrades_count,
                user_name=user_name
            )
        except Exception as e:
            print(f"⚠️ خطأ أثناء إرسال عمولة الإحالة للداعي ({ref_id}): {e}")


# ==================== الذاكرة المؤقتة للإعدادات ====================
_SETTINGS_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 0  # بدون تأخير لضمان التحديث اللحظي

# ==================== باقات العروض المميزة الافتراضية ====================
DEFAULT_USDT_PACKAGES = {
    "VIP0": {
        "title": "باقة VIP0 (2 يوم)",
        "usdt": 2.0,
        "duration_days": 2,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP1": {
        "title": "باقة VIP1 (7 أيام)",
        "usdt": 2.5,
        "duration_days": 7,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2"
        ]
    },
    "VIP2": {
        "title": "باقة VIP2 (7 أيام)",
        "usdt": 2.0,
        "duration_days": 7,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP3": {
        "title": "باقة VIP3 (30 يوم)",
        "usdt": 5.5,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2"
        ]
    },
    "VIP4": {
        "title": "باقة VIP4 (30 يوم)",
        "usdt": 6.0,
        "duration_days": 30,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP5": {
        "title": "باقة VIP5 (30 يوم)",
        "usdt": 9.99,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    }
}

# ==================== الإعدادات الافتراضية الموحدة ====================
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
    "storage_config": {
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
    },
    "packages": DEFAULT_USDT_PACKAGES,
    "ton_usdt_rate": 5.5,
    "ton_wallet": ""
}


def _normalize_storage_config(raw_storage):
    """توحيد وضمان سلامة جدول سعات المخزن (المستويات 0 إلى 8) ومنع أي قيم تالفة كالرقم 6"""
    default_stg = copy.deepcopy(DEFAULT_GAME_SETTINGS["storage_config"])
    if not isinstance(raw_storage, dict) or len(raw_storage) == 0:
        return default_stg

    normalized = {}
    for lvl_str, def_val in default_stg.items():
        item = raw_storage.get(lvl_str) or raw_storage.get(int(lvl_str))
        if isinstance(item, dict):
            cap = float(item.get("capacity", item.get("cap", def_val["capacity"])) or def_val["capacity"])
            cost_zn = float(item.get("cost_zn", item.get("cost", item.get("price", def_val["cost_zn"]))) or 0.0)
            cost_usd = float(item.get("cost_usd", item.get("usd_cost", def_val["cost_usd"])) or 0.0)
            # إذا كانت السعة في الداتابيز تالفة أو أقل من الافتراضي في المستويات العليا (مثل مشكلة رقم 6 في مستوى 8) نعتمد القيمة الصحيحة
            if int(lvl_str) >= 5 and cap < def_val["capacity"]:
                cap = def_val["capacity"]
            normalized[lvl_str] = {
                "capacity": cap,
                "cost_zn": cost_zn,
                "cost_usd": cost_usd
            }
        else:
            normalized[lvl_str] = copy.deepcopy(def_val)
    return normalized


def get_game_settings(force_refresh=False):
    """جلب إعدادات المزرعة والمتجر من Supabase بنسخ عميق وتوحيد المفاتيح"""
    global _SETTINGS_CACHE
    now_ts = time.time()
    
    if not force_refresh and _SETTINGS_CACHE["data"] and (now_ts - _SETTINGS_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return copy.deepcopy(_SETTINGS_CACHE["data"])

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT key, value FROM settings WHERE key IN ('farm_settings', 'shop_settings')")
                rows = cur.fetchall()

                data = copy.deepcopy(DEFAULT_GAME_SETTINGS)
                found_farm = False
                found_shop = False
                db_packages = None
                db_storage = None

                for row in rows:
                    if row and row.get('value'):
                        if row['key'] == 'farm_settings':
                            found_farm = True
                        elif row['key'] == 'shop_settings':
                            found_shop = True
                            
                        val = parse_json_field(row['value'], dict)
                        
                        if isinstance(val, dict) and len(val) > 0:
                            if "storage_config" in val and isinstance(val["storage_config"], dict) and len(val["storage_config"]) > 0:
                                db_storage = copy.deepcopy(val["storage_config"])
                            elif db_storage is None and "storage_capacities" in val and isinstance(val["storage_capacities"], dict) and len(val["storage_capacities"]) > 0:
                                db_storage = copy.deepcopy(val["storage_capacities"])

                            if "packages" in val and isinstance(val["packages"], dict) and len(val["packages"]) > 0:
                                db_packages = copy.deepcopy(val["packages"])
                            elif db_packages is None and "usdt_packages" in val and isinstance(val["usdt_packages"], dict) and len(val["usdt_packages"]) > 0:
                                db_packages = copy.deepcopy(val["usdt_packages"])
                                
                            for k, v in val.items():
                                if k not in ["packages", "usdt_packages", "storage_config", "storage_capacities"]:
                                    data[k] = copy.deepcopy(v)

                data["storage_config"] = _normalize_storage_config(db_storage)

                if db_packages is not None:
                    data["packages"] = db_packages
                else:
                    data["packages"] = copy.deepcopy(DEFAULT_USDT_PACKAGES)

                data["storage_capacities"] = data["storage_config"]
                data["usdt_packages"] = data["packages"]

                if not found_farm:
                    farm_defaults = {
                        "daily_rewards": DEFAULT_GAME_SETTINGS["daily_rewards"],
                        "mining_config": DEFAULT_GAME_SETTINGS["mining_config"],
                        "storage_config": data["storage_config"],
                        "upgrade_config": DEFAULT_GAME_SETTINGS["upgrade_config"]
                    }
                    cur.execute("""
                        INSERT INTO settings (key, value) VALUES ('farm_settings', %s)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """, (Json(farm_defaults),))

                if not found_shop:
                    shop_defaults = {
                        "packages": DEFAULT_GAME_SETTINGS["packages"],
                        "ton_usdt_rate": DEFAULT_GAME_SETTINGS["ton_usdt_rate"],
                        "ton_wallet": DEFAULT_GAME_SETTINGS["ton_wallet"]
                    }
                    cur.execute("""
                        INSERT INTO settings (key, value) VALUES ('shop_settings', %s)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """, (Json(shop_defaults),))
                    
                if not found_farm or not found_shop:
                    conn.commit()

                _SETTINGS_CACHE = {"data": data, "timestamp": now_ts}
                return copy.deepcopy(data)

    except Exception as e:
        print(f"⚠️ خطأ جلب إعدادات المزرعة والمتجر من Supabase: {e}")

    fallback = copy.deepcopy(_SETTINGS_CACHE["data"] or DEFAULT_GAME_SETTINGS)
    fallback["storage_capacities"] = fallback.get("storage_config", DEFAULT_GAME_SETTINGS["storage_config"])
    fallback["usdt_packages"] = fallback.get("packages", DEFAULT_USDT_PACKAGES)
    return fallback


def parse_daily_rewards(rewards_data):
    if isinstance(rewards_data, list) and len(rewards_data) > 0:
        return [max(0.0, min(float(x), 1000.0)) for x in rewards_data]
    return [float(x) for x in DEFAULT_GAME_SETTINGS["daily_rewards"]]


def get_bot_expiration_dt(user_data):
    """استخراج تاريخ انتهاء الباقة/البوت بدقة سواء من vip_status أو أعمدة المستخدم"""
    vip_info = parse_json_field(user_data.get("vip_status"), dict)
    expires_at_raw = (
        vip_info.get("expires_at")
        or vip_info.get("vip_expires_at")
        or vip_info.get("bot_expires_at")
        or user_data.get("bot_expires_at")
        or user_data.get("vip_expires_at")
        or user_data.get("expires_at")
    )
    return safe_parse_datetime(expires_at_raw)


def get_vip_flags(user_data, settings=None, now_dt=None):
    """
    فحص شامل وموحد لحالة باقة المستخدم:
    يرجع (is_auto_bot_active, is_double_storage_active, exp_dt, is_expired, had_bot_before_expiry)
    """
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    if not settings:
        settings = DEFAULT_GAME_SETTINGS

    vip_info = parse_json_field(user_data.get("vip_status"), dict)
    user_data["vip_status"] = vip_info

    exp_dt = get_bot_expiration_dt(user_data)
    is_expired = (exp_dt is not None and exp_dt <= now_dt)

    # معرفة ما إذا كانت الباقة تتضمن بوت تجميع أو مضاعفة سعة
    pkg_id = str(vip_info.get("package_id") or vip_info.get("package") or vip_info.get("tier") or "").strip().upper()
    packages_cfg = settings.get("packages") or DEFAULT_USDT_PACKAGES
    pkg_features = {}
    if pkg_id and pkg_id in packages_cfg and isinstance(packages_cfg[pkg_id], dict):
        pkg_features = packages_cfg[pkg_id].get("features", {}) or {}

    raw_bot = (
        to_bool(vip_info.get("auto_bot", False))
        or to_bool(pkg_features.get("auto_bot", False))
        or to_bool(user_data.get("bot_active", False))
        or to_bool(user_data.get("has_bot", False))
        or to_bool(user_data.get("is_auto_bot_active", False))
    )

    raw_double = (
        to_bool(vip_info.get("double_storage", False))
        or to_bool(pkg_features.get("double_storage", False))
        or to_bool(user_data.get("is_double_storage_active", False))
        or to_bool(user_data.get("double_storage", False))
        or (int(user_data.get("vip_storage_multiplier") or 1) == 2)
    )

    if is_expired:
        return False, False, exp_dt, True, raw_bot

    return raw_bot, raw_double, exp_dt, False, raw_bot


def get_base_storage_capacity(storage_level, settings=None):
    if not settings:
        settings = get_game_settings()
    try:
        lvl = int(storage_level)
    except (ValueError, TypeError):
        lvl = 0
    lvl = max(0, min(lvl, 8))

    caps = settings.get("storage_config") or settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_config"]
    val = caps.get(str(lvl)) or caps.get(lvl)

    if isinstance(val, dict):
        return min(float(val.get("capacity", 0.5)), MAX_SAFE_STORAGE_CAP)
    elif val is not None:
        return min(float(val), MAX_SAFE_STORAGE_CAP)
    return 0.5


def calculate_user_max_cap(user_data, settings=None, now_dt=None):
    """حساب سعة المخزن الفعلية مع تطبيق ميزة الضعف ×2 لباقات VIP السارية فقط"""
    if not settings:
        settings = get_game_settings()
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    stg_lvl = user_data.get("storage_level", 0)
    base_cap = get_base_storage_capacity(stg_lvl, settings)
    extra_cap = max(0.0, float(user_data.get("extra_storage", 0.0) or 0.0))
    raw_cap = base_cap + extra_cap

    _, is_double, _, _, _ = get_vip_flags(user_data, settings, now_dt)

    total_cap = (raw_cap * 2.0) if is_double else raw_cap
    return min(round(total_cap, 4), MAX_SAFE_STORAGE_CAP)


def calculate_verified_hourly_rate(user_data, settings=None):
    """حساب وتأمين سرعة التعدين بناءً على ترقيات اللاعب الفعلية لمنع نقصان السرعة أو التلاعب"""
    if not settings:
        settings = DEFAULT_GAME_SETTINGS

    mining_cfg = settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    base_free_rate = float(mining_cfg.get("base_free_rate", 0.10))
    max_per_lvl = int(mining_cfg.get("max_upgrades_per_level", 15))
    upgrade_configs = settings.get("upgrade_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]

    upgrades = parse_json_field(user_data.get("upgrades"), dict)
    user_data["upgrades"] = upgrades

    calculated_rate = base_free_rate
    for lvl_num in range(1, 9):
        lvl_str = str(lvl_num)
        cnt = int(upgrades.get(f"lvl{lvl_str}", upgrades.get(lvl_str, 0)) or 0)
        cnt = max(0, min(cnt, max_per_lvl))
        lvl_cfg = upgrade_configs.get(lvl_str) or DEFAULT_GAME_SETTINGS["upgrade_config"].get(lvl_str, {})
        bonus = float(lvl_cfg.get("rate_bonus", lvl_cfg.get("rate", 0.0)) or 0.0)
        calculated_rate += (cnt * bonus)

    calculated_rate = round(calculated_rate, 4)
    stored_rate = float(user_data.get("hourly_rate") or base_free_rate)

    # نعتمد القيمة الأعلى بين المحسوبة والمخزنة (لحفظ أي مكافآت سرعة إضافية) مع سقف الأمان
    effective_rate = max(base_free_rate, calculated_rate, stored_rate)
    return min(round(effective_rate, 4), MAX_SAFE_HOURLY_RATE)


def _calculate_interval_mined(hourly_rate, start_dt, end_dt, last_boost_str=None):
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0.0
    
    safe_rate = max(0.0, min(float(hourly_rate or 0.0), MAX_SAFE_HOURLY_RATE))
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
    hourly_rate = min(float(user_data.get("hourly_rate") or 0.10), MAX_SAFE_HOURLY_RATE)

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
            conn.commit()
        return {"success": True, "welcome_seen": True, "is_new_user": False}
    except Exception as e:
        print(f"❌ خطأ dismiss_welcome_db: {e}")
        return {"success": False, "error": str(e)}


def calculate_user_effective_stats(user_data, game_settings=None, now_dt=None):
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    if not game_settings:
        game_settings = get_game_settings()

    user_data["vip_status"] = parse_json_field(user_data.get("vip_status"), dict)
    user_data["upgrades"] = parse_json_field(user_data.get("upgrades"), dict)

    is_bot_active, is_double_active, _, _, _ = get_vip_flags(user_data, game_settings, now_dt)
    verified_rate = calculate_verified_hourly_rate(user_data, game_settings)
    effective_max_cap = calculate_user_max_cap(user_data, game_settings, now_dt)

    user_data["balance"] = min(max(0.0, float(user_data.get("balance") or 0.0)), MAX_SAFE_BALANCE)
    user_data["usd_balance"] = min(max(0.0, float(user_data.get("usd_balance") or 0.0)), 1000000.0)
    user_data["hourly_rate"] = verified_rate
    user_data["max_cap"] = effective_max_cap

    user_data["bot_active"] = is_bot_active
    user_data["is_auto_bot_active"] = is_bot_active
    user_data["is_double_storage_active"] = is_double_active
    user_data["vip_storage_multiplier"] = 2 if is_double_active else 1
    return user_data


def get_or_create_user_farm_data(user_id_str):
    str_uid = str(user_id_str)
    now = datetime.now(timezone.utc)
    game_settings = get_game_settings()
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    base_free_rate = float(mining_cfg.get("base_free_rate", 0.10))

    ref_id_for_auto = None
    auto_claimed_amount = 0.0
    user_upgrades_cnt = 0
    user_name = "صديق"

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT *, 
                           COALESCE(balance, 0.0) as balance, 
                           COALESCE(usd_balance, 0.0) as usd_balance,
                           COALESCE(hourly_rate, 0.10) as hourly_rate
                    FROM users WHERE tg_id = %s FOR UPDATE
                """, (str_uid,))
                user_row = cur.fetchone()

                if not user_row:
                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, balance, usd_balance, hourly_rate, welcome_seen, created_at, last_claim_time)
                        VALUES (%s, %s, %s, 0.0, 0.0, %s, FALSE, %s, %s)
                        RETURNING *;
                    """, (str_uid, str_uid, str_uid, base_free_rate, now, now))
                    user_data = dict(cur.fetchone())
                else:
                    user_data = dict(user_row)

                # فك تشفير الحقول وتحديث إحصائيات اللاعب (السرعة والسعة والباقات) فوراً
                user_data["vip_status"] = parse_json_field(user_data.get("vip_status"), dict)
                user_data["upgrades"] = parse_json_field(user_data.get("upgrades"), dict)

                is_bot_active, is_double_active, exp_dt, is_expired, had_bot_before_expiry = get_vip_flags(user_data, game_settings, now)
                user_data = calculate_user_effective_stats(user_data, game_settings, now)
                expected_max_cap = user_data["max_cap"]

                # إذا كانت سرعة التعدين المحسوبة من الترقيات أعلى من المسجلة، نحدثها في الداتابيز
                db_hourly = float(user_row.get("hourly_rate") or 0.10) if user_row else base_free_rate
                if abs(user_data["hourly_rate"] - db_hourly) > 0.001:
                    cur.execute("UPDATE users SET hourly_rate = %s WHERE tg_id = %s", (user_data["hourly_rate"], str_uid))

                # إذا انتهت صلاحية الباقة وكان عمود bot_active لا يزال TRUE، نغلقه بعد حساب مستحقاته
                if is_expired and to_bool(user_row.get("bot_active") if user_row else False):
                    cur.execute("UPDATE users SET bot_active = FALSE WHERE tg_id = %s", (str_uid,))

                last_claim_dt = safe_parse_datetime(user_data.get("last_claim_time"), now)
                if not last_claim_dt or last_claim_dt > (now + timedelta(seconds=FUTURE_SKEW_TOLERANCE_SEC)):
                    last_claim_dt = now

                # 🤖 معالجة بوت التجميع التلقائي أثناء إغلاق اللعبة (Offline Auto-Claim بدون سقف 400)
                bot_effective_end = None
                if is_bot_active:
                    bot_effective_end = now
                elif is_expired and had_bot_before_expiry and exp_dt and exp_dt > last_claim_dt:
                    bot_effective_end = exp_dt

                if bot_effective_end and bot_effective_end > last_claim_dt:
                    offline_seconds = (bot_effective_end - last_claim_dt).total_seconds()
                    total_offline_mined = _calculate_interval_mined(
                        user_data.get("hourly_rate", 0.10),
                        last_claim_dt,
                        bot_effective_end,
                        user_data.get("last_boost_time")
                    )

                    # يجمع البوت في الرصيد طوال فترة غياب المستخدم بدون أي سقف مخزن
                    should_auto_claim = (
                        total_offline_mined > 0 and (
                            offline_seconds >= MIN_OFFLINE_AUTO_CLAIM_SEC
                            or total_offline_mined >= (expected_max_cap * 0.80)
                            or (is_expired and exp_dt is not None)
                        )
                    )

                    if should_auto_claim:
                        auto_claimed_amount = round(total_offline_mined, 8)
                        cur.execute("""
                            UPDATE users SET
                                balance = LEAST(%s, GREATEST(0.0, COALESCE(balance, 0.0) + %s)),
                                mined_points = COALESCE(mined_points, total_mined, 0.0) + %s,
                                total_mined = COALESCE(total_mined, mined_points, 0.0) + %s,
                                last_claim_time = %s
                            WHERE tg_id = %s
                            RETURNING balance, mined_points, total_mined, last_claim_time
                        """, (MAX_SAFE_BALANCE, auto_claimed_amount, auto_claimed_amount, auto_claimed_amount, bot_effective_end, str_uid))
                        upd = cur.fetchone()
                        if upd:
                            user_data["balance"] = float(upd["balance"])
                            user_data["mined_points"] = float(upd["mined_points"])
                            user_data["total_mined"] = float(upd["total_mined"])
                            user_data["last_claim_time"] = upd["last_claim_time"]

                        ref_id_for_auto = _resolve_referrer_id(cur, user_data, str_uid)
                        user_name = user_data.get("first_name") or user_data.get("name") or "صديق"
                        calc_upg = sum(int(v) for v in user_data["upgrades"].values() if isinstance(v, (int, float)))
                        user_upgrades_cnt = max(int(user_data.get("upgrades_count") or 0), calc_upg)

                # إخفاء رسالة الترحيب نهائياً إذا كانت لديه أرصدة مسبقة
                is_welcome_seen = to_bool(user_data.get("welcome_seen", False))
                if not is_welcome_seen and (float(user_data.get("total_mined") or 0) > 0 or float(user_data.get("balance") or 0) > 0):
                    is_welcome_seen = True
                    cur.execute("UPDATE users SET welcome_seen = TRUE WHERE tg_id = %s", (str_uid,))

            conn.commit()

        if ref_id_for_auto and auto_claimed_amount > 0:
            _dispatch_referral_commission(ref_id_for_auto, str_uid, auto_claimed_amount, user_upgrades_cnt, user_name)

        user_data["boost_history"] = parse_json_field(user_data.get("boost_history"), list)
        user_data["daily_history"] = parse_json_field(user_data.get("daily_history"), list)

        user_data["boost_claims_count"] = int(user_data.get("boost_claims_count") or 0)
        user_data["daily_claims_count"] = int(user_data.get("daily_claims_count") or 0)

        unclaimed_val = calculate_accrued_mined(user_data, now, expected_max_cap)
        user_data["unclaimed"] = unclaimed_val
        user_data["base_unclaimed"] = unclaimed_val
        user_data["auto_claimed_amount"] = auto_claimed_amount

        user_data["welcome_seen"] = is_welcome_seen
        user_data["is_new_user"] = not is_welcome_seen

        today_str = now.strftime('%Y-%m-%d')
        yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        last_daily_claim = user_data.get("last_daily_claim_date")
        raw_daily_day = int(user_data.get("daily_day", 1) or 1)

        if last_daily_claim == today_str:
            effective_daily_day = raw_daily_day
        elif last_daily_claim == yesterday_str:
            effective_daily_day = min(raw_daily_day + 1, 30) if raw_daily_day < 30 else 30
        else:
            effective_daily_day = 1

        user_data["daily_day"] = effective_daily_day
        user_data["daily_streak"] = effective_daily_day

        for k, v in list(user_data.items()):
            if isinstance(v, datetime):
                user_data[k] = format_iso(v)

        return user_data, game_settings, now

    except Exception as e:
        print(f"❌ خطأ get_or_create_user_farm_data: {e}")
        return {}, game_settings, now


def claim_mined_tokens_db(user_id_str):
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    cooldown_seconds = int(mining_cfg.get("claim_cooldown_seconds", 15))

    ref_id = None
    mined_amount = 0.0
    user_upgrades_cnt = 0
    user_name = "صديق"

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                today_utc_str = now.strftime('%Y-%m-%d')

                user_data = calculate_user_effective_stats(user_data, game_settings, now)
                is_bot_active = user_data["bot_active"]
                is_double_active = user_data["is_double_storage_active"]
                max_cap = user_data["max_cap"]

                last_claim_str = user_data.get("last_claim_time")
                if last_claim_str:
                    last_claim = safe_parse_datetime(last_claim_str)
                    if last_claim:
                        seconds_passed = (now - last_claim).total_seconds()
                        if 0 <= seconds_passed < cooldown_seconds:
                            rem = int(cooldown_seconds - seconds_passed) + 1
                            return {"success": False, "error": f"الرجاء الانتظار {rem} ثانية قبل التجميع مجدداً", "cooldown_remaining": rem}

                # إذا كان البوت التلقائي مفعلاً، لا نقص الرصيد المجمع عند سقف المخزن أبداً
                mined_amount = calculate_accrued_mined(user_data, now, max_cap, ignore_cap=is_bot_active)

                if mined_amount <= 0:
                    return {"success": False, "error": "المخزن فارغ حالياً"}

                now_iso = format_iso(now)

                cur.execute("""
                    UPDATE users SET
                        balance = LEAST(%s, GREATEST(0.0, COALESCE(balance, 0.0) + %s)),
                        mined_points = COALESCE(mined_points, total_mined, 0.0) + %s,
                        total_mined = COALESCE(total_mined, mined_points, 0.0) + %s,
                        last_claim_time = %s
                    WHERE tg_id = %s
                    RETURNING balance, usd_balance, mined_points
                """, (MAX_SAFE_BALANCE, mined_amount, mined_amount, mined_amount, now, str_uid))
                
                updated_row = cur.fetchone()
                db_new_balance = float(updated_row['balance'])
                db_usd_balance = float(updated_row['usd_balance'])
                db_new_mined_points = float(updated_row['mined_points'])

                ref_id = _resolve_referrer_id(cur, user_data, str_uid)
                user_name = user_data.get("first_name") or user_data.get("name") or "صديق"
                upgrades_dict = user_data.get("upgrades") or {}
                calc_upg = sum(int(v) for v in upgrades_dict.values() if isinstance(v, (int, float))) if isinstance(upgrades_dict, dict) else 0
                user_upgrades_cnt = max(int(user_data.get("upgrades_count") or 0), calc_upg)

            conn.commit()

        if ref_id and mined_amount > 0:
            _dispatch_referral_commission(ref_id, str_uid, mined_amount, user_upgrades_cnt, user_name)

        return {
            "success": True,
            "new_balance": db_new_balance,
            "new_usd_balance": db_usd_balance,
            "total_mined": db_new_mined_points,
            "mined_points": db_new_mined_points,
            "last_claim_time": now_iso,
            "last_claim_ad_date": today_utc_str,
            "base_unclaimed": 0.0,
            "unclaimed": 0.0,
            "max_cap": max_cap,
            "hourly_rate": user_data["hourly_rate"],
            "bot_active": is_bot_active,
            "is_auto_bot_active": is_bot_active,
            "is_double_storage_active": is_double_active,
            "server_time": now_iso,
            "claimed_amount": mined_amount
        }

    except Exception as e:
        print(f"❌ خطأ claim_mined_tokens_db: {e}")
        return {"success": False, "error": f"تعذر تنفيذ التجميع: {str(e)}"}


def buy_upgrade_db(user_id_str, level):
    level_str = str(level).strip()
    str_uid = str(user_id_str)
    game_settings = get_game_settings()

    mining_cfg = game_settings.get("mining_config", DEFAULT_GAME_SETTINGS["mining_config"])
    global_max_upgrades = int(mining_cfg.get("max_upgrades_per_level", 15))

    upgrade_configs = game_settings.get("upgrade_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
    if level_str not in upgrade_configs:
        return {"success": False, "error": "بيانات المستوى غير متوفرة"}

    level_cfg = upgrade_configs[level_str]
    cost_zn = float(level_cfg.get("cost_zn", level_cfg.get("price", 0.0)))
    cost_usd = float(level_cfg.get("cost_usd", level_cfg.get("usd_cost", 0.0)))
    rate_bonus = round(float(level_cfg.get("rate_bonus", level_cfg.get("rate", 0.0))), 2)
    max_limit = int(level_cfg.get("max", level_cfg.get("max_limit", global_max_upgrades)))

    ref_id = None
    pending_amount = 0.0
    total_upgrades_count = 0
    user_name = "صديق"

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                now_iso = format_iso(now)

                user_data = calculate_user_effective_stats(user_data, game_settings, now)
                current_max_cap = user_data["max_cap"]
                is_bot_active = user_data["bot_active"]
                pending_amount = calculate_accrued_mined(user_data, now, current_max_cap, ignore_cap=is_bot_active)

                current_balance = float(user_data.get("balance") or 0.0)
                current_usd_balance = float(user_data.get("usd_balance") or 0.0)

                total_zn = current_balance + pending_amount

                if total_zn < cost_zn:
                    return {"success": False, "error": f"رصيد العملات غير كافٍ! السعر {cost_zn:,.0f} ZN (مشمولاً المحصول)"}

                if cost_usd > 0 and current_usd_balance < cost_usd:
                    return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

                upgrades = user_data.get("upgrades") or {}

                # حماية قصوى: منع شراء مستوى أعلى قبل فتح المستوى السابق له على الأقل مرة واحدة
                lvl_num = int(level_str)
                if lvl_num > 1:
                    prev_key = f"lvl{lvl_num - 1}"
                    prev_count = int(upgrades.get(prev_key, upgrades.get(str(lvl_num - 1), 0)))
                    if prev_count <= 0:
                        return {"success": False, "error": f"يجب فتح المستوى {lvl_num - 1} أولاً قبل شراء المستوى {lvl_num}"}

                lvl_key = f"lvl{level_str}"
                current_count = int(upgrades.get(lvl_key, upgrades.get(level_str, 0)))

                if current_count >= max_limit:
                    return {"success": False, "error": f"لقد وصلت للحد الأقصى للشراء لهذا المستوى ({max_limit}/{max_limit})"}

                upgrades[lvl_key] = current_count + 1
                if level_str in upgrades and f"lvl{level_str}" != level_str:
                    del upgrades[level_str]

                total_upgrades_count = sum(int(v) for v in upgrades.values() if isinstance(v, (int, float)))
                user_data["upgrades"] = upgrades
                new_verified_hourly = calculate_verified_hourly_rate(
                    {"upgrades": upgrades, "hourly_rate": float(user_data.get("hourly_rate") or 0.10) + rate_bonus},
                    game_settings
                )

                cur.execute("""
                    UPDATE users SET
                        balance = LEAST(%s, GREATEST(0.0, COALESCE(balance, 0.0) + %s - %s)),
                        usd_balance = GREATEST(0.0, COALESCE(usd_balance, 0.0) - %s),
                        hourly_rate = %s,
                        upgrades = %s,
                        upgrades_count = %s,
                        last_claim_time = %s,
                        mined_points = COALESCE(mined_points, total_mined, 0.0) + %s,
                        total_mined = COALESCE(total_mined, mined_points, 0.0) + %s
                    WHERE tg_id = %s
                    RETURNING balance, usd_balance, hourly_rate
                """, (MAX_SAFE_BALANCE, pending_amount, cost_zn, cost_usd, new_verified_hourly, Json(upgrades), total_upgrades_count, now, pending_amount, pending_amount, str_uid))
                
                updated_row = cur.fetchone()
                db_new_balance = float(updated_row['balance'])
                db_usd_balance = float(updated_row['usd_balance'])
                db_new_hourly = float(updated_row['hourly_rate'])

                ref_id = _resolve_referrer_id(cur, user_data, str_uid)
                user_name = user_data.get("first_name") or user_data.get("name") or "صديق"

                cur.execute("""
                    UPDATE user_friends
                    SET upgrades_count = GREATEST(COALESCE(upgrades_count, 0), %s),
                        first_name = %s,
                        name = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE friend_id = %s;
                """, (total_upgrades_count, user_name, user_name, str_uid))

            conn.commit()

        if ref_id and pending_amount > 0:
            _dispatch_referral_commission(ref_id, str_uid, pending_amount, total_upgrades_count, user_name)
        elif callable(sync_friend_upgrades_db):
            sync_friend_upgrades_db(str_uid, total_upgrades_count)

        return {
            "success": True,
            "new_balance": db_new_balance,
            "new_usd_balance": db_usd_balance,
            "new_hourly_rate": db_new_hourly,
            "hourly_rate": db_new_hourly,
            "max_cap": current_max_cap,
            "upgrades": upgrades,
            "upgrades_count": total_upgrades_count,
            "bot_active": is_bot_active,
            "is_double_storage_active": user_data["is_double_storage_active"],
            "server_time": now_iso
        }

    except Exception as e:
        print(f"❌ خطأ buy_upgrade_db: {e}")
        return {"success": False, "error": f"تعذر إتمام عملية الترقية: {str(e)}"}


def buy_storage_db(user_id_str):
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    storage_cfgs = game_settings.get("storage_config") or game_settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_config"]

    ref_id = None
    pending_amount = 0.0
    user_upgrades_cnt = 0
    user_name = "صديق"

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                now_iso = format_iso(now)

                user_data = calculate_user_effective_stats(user_data, game_settings, now)
                current_level = int(user_data.get("storage_level", 0))
                next_level = current_level + 1

                if next_level > 8 or str(next_level) not in storage_cfgs:
                    return {"success": False, "error": "المخزن في أقصى مستوى بالفعل (MAX)"}

                next_cfg = storage_cfgs[str(next_level)]
                cost_zn = float(next_cfg.get("cost_zn", next_cfg.get("price", 0.0))) if isinstance(next_cfg, dict) else 0.0
                cost_usd = float(next_cfg.get("cost_usd", next_cfg.get("usd_cost", 0.0))) if isinstance(next_cfg, dict) else 0.0

                current_max_cap = user_data["max_cap"]
                is_bot_active = user_data["bot_active"]
                pending_amount = calculate_accrued_mined(user_data, now, current_max_cap, ignore_cap=is_bot_active)

                current_balance = float(user_data.get("balance") or 0.0)
                current_usd_balance = float(user_data.get("usd_balance") or 0.0)

                total_zn = current_balance + pending_amount

                if total_zn < cost_zn:
                    return {"success": False, "error": f"رصيدك غير كافٍ! السعر {cost_zn:,.0f} ZN (مشمولاً المحصول)"}

                if cost_usd > 0 and current_usd_balance < cost_usd:
                    return {"success": False, "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"}

                cur.execute("""
                    UPDATE users SET
                        balance = LEAST(%s, GREATEST(0.0, COALESCE(balance, 0.0) + %s - %s)),
                        usd_balance = GREATEST(0.0, COALESCE(usd_balance, 0.0) - %s),
                        storage_level = %s,
                        last_claim_time = %s,
                        mined_points = COALESCE(mined_points, total_mined, 0.0) + %s,
                        total_mined = COALESCE(total_mined, mined_points, 0.0) + %s
                    WHERE tg_id = %s
                    RETURNING balance, usd_balance
                """, (MAX_SAFE_BALANCE, pending_amount, cost_zn, cost_usd, next_level, now, pending_amount, pending_amount, str_uid))
                
                updated_row = cur.fetchone()
                db_new_balance = float(updated_row['balance'])
                db_usd_balance = float(updated_row['usd_balance'])

                user_data["storage_level"] = next_level
                new_max_cap = calculate_user_max_cap(user_data, game_settings, now)

                ref_id = _resolve_referrer_id(cur, user_data, str_uid)
                user_name = user_data.get("first_name") or user_data.get("name") or "صديق"
                user_upgrades_cnt = int(user_data.get("upgrades_count") or 0)

            conn.commit()

        if ref_id and pending_amount > 0:
            _dispatch_referral_commission(ref_id, str_uid, pending_amount, user_upgrades_cnt, user_name)

        return {
            "success": True,
            "new_balance": db_new_balance,
            "new_usd_balance": db_usd_balance,
            "storage_level": next_level,
            "max_cap": new_max_cap,
            "bot_active": is_bot_active,
            "is_double_storage_active": user_data["is_double_storage_active"],
            "server_time": now_iso
        }

    except Exception as e:
        print(f"❌ خطأ buy_storage_db: {e}")
        return {"success": False, "error": f"تعذر إتمام ترقية المخزن: {str(e)}"}


def claim_daily_reward_db(user_id_str):
    str_uid = str(user_id_str)
    game_settings = get_game_settings()
    parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                now_iso = format_iso(now)
                today_str = now.strftime('%Y-%m-%d')
                yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')

                last_daily_claim = user_data.get("last_daily_claim_date")

                if last_daily_claim == today_str:
                    return {"success": False, "error": "لقد قمت باستلام المكافأة اليوم بالفعل"}

                raw_daily_day = int(user_data.get("daily_day", 1) or 1)

                if last_daily_claim == yesterday_str:
                    effective_daily_day = min(raw_daily_day + 1, 30) if raw_daily_day < 30 else 30
                else:
                    effective_daily_day = 1

                reward_index = min(max(effective_daily_day - 1, 0), 29)
                reward_amount = float(parsed_rewards[reward_index])

                daily_history = parse_json_field(user_data.get("daily_history"), list)

                new_daily_entry = {
                    "timestamp": now_iso,
                    "date": today_str,
                    "time": now.strftime('%H:%M:%S'),
                    "day": effective_daily_day,
                    "reward_amount": reward_amount
                }
                daily_history.append(new_daily_entry)

                cur.execute("""
                    UPDATE users SET
                        balance = LEAST(%s, GREATEST(0.0, COALESCE(balance, 0.0) + %s)),
                        daily_day = %s,
                        daily_streak = %s,
                        last_daily_claim_date = %s,
                        ads_watched = COALESCE(ads_watched, 0) + 1,
                        daily_claims_count = COALESCE(daily_claims_count, 0) + 1,
                        daily_history = %s
                    WHERE tg_id = %s
                    RETURNING balance, usd_balance, ads_watched, daily_claims_count
                """, (MAX_SAFE_BALANCE, reward_amount, effective_daily_day, effective_daily_day, today_str, Json(daily_history), str_uid))
                
                updated_row = cur.fetchone()
                db_new_balance = float(updated_row['balance'])
                db_usd_balance = float(updated_row['usd_balance'])
                db_ads_watched = int(updated_row['ads_watched'])
                db_daily_count = int(updated_row['daily_claims_count'])

            conn.commit()

            return {
                "success": True,
                "new_balance": db_new_balance,
                "new_usd_balance": db_usd_balance,
                "reward_amount": reward_amount,
                "daily_day": effective_daily_day,
                "daily_streak": effective_daily_day,
                "last_daily_claim_date": today_str,
                "ads_watched": db_ads_watched,
                "daily_claims_count": db_daily_count,
                "server_time": now_iso
            }

    except Exception as e:
        print(f"❌ خطأ claim_daily_reward_db: {e}")
        return {"success": False, "error": f"تعذر استلام المكافأة اليومية: {str(e)}"}


def claim_daily_boost_db(user_id_str):
    str_uid = str(user_id_str)
    game_settings = get_game_settings()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return {"success": False, "error": "المستخدم غير موجود"}

                user_data = dict(user_data)
                now = datetime.now(timezone.utc)
                now_iso = format_iso(now)

                user_data = calculate_user_effective_stats(user_data, game_settings, now)

                last_boost_str = user_data.get("last_boost_time")
                if last_boost_str:
                    last_boost = safe_parse_datetime(last_boost_str)
                    if last_boost:
                        elapsed_seconds = (now - last_boost).total_seconds()
                        if 0 <= elapsed_seconds < 10800:
                            rem_mins = int((10800 - elapsed_seconds) // 60)
                            return {"success": False, "error": f"الرجاء الانتظار {rem_mins} دقيقة قبل تفعيل المعزز مجدداً"}

                boost_history = parse_json_field(user_data.get("boost_history"), list)

                new_boost_entry = {
                    "timestamp": now_iso,
                    "date": now.strftime('%Y-%m-%d'),
                    "time": now.strftime('%H:%M:%S'),
                    "reward_rate": 0.10
                }
                boost_history.append(new_boost_entry)

                cur.execute("""
                    UPDATE users SET
                        last_boost_time = %s,
                        ads_watched = COALESCE(ads_watched, 0) + 1,
                        boost_claims_count = COALESCE(boost_claims_count, 0) + 1,
                        boost_history = %s
                    WHERE tg_id = %s
                    RETURNING boost_claims_count
                """, (now, Json(boost_history), str_uid))
                
                updated_row = cur.fetchone()
                db_boost_count = int(updated_row['boost_claims_count'])

            conn.commit()

            return {
                "success": True,
                "boost_rate_bonus": 0.10,
                "boost_duration_hours": 2,
                "last_boost_time": now_iso,
                "boost_claims_count": db_boost_count,
                "max_cap": user_data["max_cap"],
                "hourly_rate": user_data["hourly_rate"],
                "bot_active": user_data["bot_active"],
                "is_double_storage_active": user_data["is_double_storage_active"],
                "server_time": now_iso
            }

    except Exception as e:
        print(f"❌ خطأ claim_daily_boost_db: {e}")
        return {"success": False, "error": f"تعذر تفعيل التعزيز: {str(e)}"}


def get_mining_leaderboard_db(limit=10):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tg_id, first_name, 
                           COALESCE(mined_points, total_mined, 0.0) as mined_points,
                           COALESCE(total_mined, mined_points, 0.0) as total_mined,
                           COALESCE(balance, 0.0) as balance, 
                           COALESCE(hourly_rate, 0.10) as hourly_rate
                    FROM users
                    ORDER BY COALESCE(mined_points, total_mined, 0.0) DESC
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall()

                leaderboard = []
                for rank, row in enumerate(rows, start=1):
                    d = dict(row)
                    total_m = float(d.get('mined_points') or 0.0)
                    leaderboard.append({
                        "rank": rank,
                        "tg_id": str(d.get('tg_id')),
                        "name": str(d.get('first_name') or 'لاعب'),
                        "total_mined": round(total_m, 8),
                        "mined_points": round(total_m, 8),
                        "balance": round(float(d.get('balance') or 0.0), 8),
                        "hourly_rate": round(float(d.get('hourly_rate') or 0.10), 4)
                    })
                return leaderboard
    except Exception as e:
        print(f"❌ خطأ get_mining_leaderboard_db: {e}")
        return []


def get_user_friends_db(user_id_str):
    if callable(get_friends_data_db) and callable(_get_friends_list_From_friends_db):
        summary = get_friends_data_db(user_id_str)
        friends_list = _get_friends_list_From_friends_db(user_id_str)
        return {
            "friends": friends_list,
            "total_referrals": len(friends_list),
            "eligible_referrals": summary.get("eligible_task_friends_count", 0),
            "referral_earnings": summary.get("total_ref_earnings", 0.0),
            "unclaimed_rewards": summary.get("pending_ref_earnings", 0.0),
            "invite_link": f"https://t.me/zngoxe_bot?start=ref_{user_id_str}"
        }
    return {
        "friends": [],
        "total_referrals": 0,
        "eligible_referrals": 0,
        "referral_earnings": 0.0,
        "unclaimed_rewards": 0.0,
        "invite_link": f"https://t.me/zngoxe_bot?start=ref_{user_id_str}"
    }


def claim_referral_rewards_db(user_id_str):
    if callable(claim_ref_earnings_db):
        return claim_ref_earnings_db(user_id_str)
    return {"success": False, "error": "خدمة سحب أرباح الأصدقاء غير متاحة حالياً"}

# -*- coding: utf-8 -*-
"""
friends/friends_db.py - إدارة نظام الأصدقاء والإحالات عبر Supabase (PostgreSQL / psycopg2)
يدعم الإنشاء التلقائي للجداول، المعاملات الذرية (FOR UPDATE)، والمزامنة الحية اللحظية مع Supabase
مع مطابقة صارمة لصلاحية باقات VIP ومنع احتساب الحسابات المحظورة.
"""
import time
import json
import threading
from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor, Json
import database

# قفل حماية إضافي على مستوى السيرفر لمنع تكرار الطلبات لنفس المستخدم
_USER_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _get_user_lock(tg_id):
    key = str(tg_id).strip()
    with _LOCKS_GUARD:
        if key not in _USER_LOCKS:
            _USER_LOCKS[key] = threading.RLock()
        return _USER_LOCKS[key]


# الإعدادات الافتراضية لنظام الأصدقاء
DEFAULT_FRIENDS_CONFIG = {
    "commission_percent": 10.0,       # نسبة أرباح الإحالة العادية (10%)
    "vip_commission_percent": 12.0,   # نسبة أرباح الإحالة لمشتركي باقات الإحالة VIP (12%)
    "claim_fee_percent": 1.5,         # نسبة عمولة السحب العادية (1.5%)
    "vip_claim_fee_percent": 0.0,     # نسبة عمولة السحب لمشتركي VIP (0%)
    "min_upgrades_for_task": 5,       # عدد الترقيات المطلوب لاحتساب الصديق مؤهل للمهام (للمستخدم العادي)
    "vip_min_upgrades_for_task": 3,   # عدد الترقيات المطلوب للمشتركين في باقات الإحالة VIP
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

# الباقات التي تمنح مميزات الإحالة (12% عمولة، 3 ترقيات، 0% رسوم سحب)
REFERRAL_VIP_PACKAGES = {"VIP0", "VIP2", "VIP4", "VIP5"}

_CONFIG_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 0  # قراءة لحظية مباشرة من Supabase بدون تأخير
_TABLES_READY = False
_TABLES_LOCK = threading.Lock()


def _clean_id(val):
    if val is None:
        return None
    s = str(val).strip()
    if s.startswith("ref_"):
        s = s.replace("ref_", "", 1).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not s or s.lower() in ("none", "null", "undefined", "nan", ""):
        return None
    return s


def _parse_json(val, default):
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed
        except Exception:
            return default
    return default


def _parse_timestamp(val):
    """تحليل وتوحيد قراءة التواريخ والطوابع الزمنية بأشكالها المختلفة"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        ts = float(val)
        if ts > 1e11:
            ts /= 1000.0
        return ts
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.timestamp()
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None
        try:
            ts = float(val_str)
            if ts > 1e11:
                ts /= 1000.0
            return ts
        except ValueError:
            pass
        try:
            clean_str = val_str.replace(" ", "T").replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val_str, fmt).replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                pass
    return None


def _is_row_banned(row_dict):
    if not isinstance(row_dict, dict):
        return False
    return bool(
        row_dict.get("is_banned")
        or row_dict.get("banned")
        or str(row_dict.get("status") or "").lower() == "banned"
    )


def _calculate_json_upgrades(upgrades_raw):
    """حساب مجموع الترقيات الفعلي من حقل upgrades (JSONB) فقط"""
    upgrades_json = _parse_json(upgrades_raw, {})
    calc_sum = 0
    if isinstance(upgrades_json, dict):
        for _, v in upgrades_json.items():
            if isinstance(v, (int, float)):
                calc_sum += max(0, int(v))
            elif isinstance(v, str) and v.strip().isdigit():
                calc_sum += int(v.strip())
            elif isinstance(v, dict):
                lvl = v.get("count") or v.get("level") or v.get("lvl") or 0
                try:
                    calc_sum += max(0, int(lvl))
                except (ValueError, TypeError):
                    pass
    elif isinstance(upgrades_json, list):
        calc_sum = len(upgrades_json)
    return calc_sum


def _calculate_upgrades_from_row(user_row):
    """حساب إجمالي ترقيات الصديق من عمود upgrades (JSONB) وعمود upgrades_count"""
    if not isinstance(user_row, dict):
        return 0

    stored_count = 0
    try:
        stored_count = int(float(user_row.get("upgrades_count") or 0))
    except (ValueError, TypeError):
        stored_count = 0

    calc_sum = _calculate_json_upgrades(user_row.get("upgrades"))
    return max(stored_count, calc_sum)


def init_friends_tables():
    """إنشاء وتجهيز جداول وأعمدة وإعدادات نظام الأصدقاء تلقائياً في Supabase"""
    global _TABLES_READY
    if _TABLES_READY:
        return

    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        try:
            with database.get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS settings (
                            key VARCHAR(128) PRIMARY KEY,
                            value JSONB DEFAULT '{}'::jsonb,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS user_friends (
                            id BIGSERIAL PRIMARY KEY,
                            referrer_id VARCHAR(128) NOT NULL,
                            friend_id VARCHAR(128) NOT NULL,
                            first_name VARCHAR(100) DEFAULT 'صديق',
                            name VARCHAR(100) DEFAULT 'صديق',
                            earned_from_him DOUBLE PRECISION DEFAULT 0.0,
                            upgrades_count INT DEFAULT 0,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT uq_referrer_friend UNIQUE (referrer_id, friend_id)
                        );

                        CREATE INDEX IF NOT EXISTS idx_user_friends_referrer ON user_friends(referrer_id);
                        CREATE INDEX IF NOT EXISTS idx_user_friends_friend ON user_friends(friend_id);

                        ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100) DEFAULT 'لاعب';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_by VARCHAR(128);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by VARCHAR(128);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS referrals_count INT DEFAULT 0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_ref_earnings DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_ref_earnings DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS claimed_ref_tasks JSONB DEFAULT '[]'::jsonb;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS upgrades JSONB DEFAULT '{}'::jsonb;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS upgrades_count INT DEFAULT 0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_status JSONB DEFAULT '{}'::jsonb;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_active BOOLEAN DEFAULT FALSE;
                    """)

                    cur.execute("SELECT value FROM settings WHERE key = 'friends_config' LIMIT 1;")
                    existing_row = cur.fetchone()
                    if not existing_row or not existing_row.get("value"):
                        cur.execute("""
                            INSERT INTO settings (key, value, updated_at)
                            VALUES ('friends_config', %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (key) DO UPDATE
                            SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
                        """, (Json(DEFAULT_FRIENDS_CONFIG),))
                    else:
                        current_cfg = _parse_json(existing_row.get("value"), {})
                        changed = False
                        if int(current_cfg.get("min_upgrades_for_task", 5)) == 3:
                            current_cfg["min_upgrades_for_task"] = 5
                            changed = True
                        if "vip_min_upgrades_for_task" not in current_cfg:
                            current_cfg["vip_min_upgrades_for_task"] = 3
                            changed = True

                        if changed:
                            cur.execute("""
                                UPDATE settings
                                SET value = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE key = 'friends_config';
                            """, (Json(current_cfg),))

            _TABLES_READY = True
        except Exception as e:
            print(f"⚠️ تنبيه أثناء تهيئة جداول الأصدقاء في Supabase: {e}")


init_friends_tables()


def get_active_vip_referral_details(tg_id, user_data=None):
    """
    فحص صارم ومطابق 100% للمتجر (shop_db.py):
    - لا تُعتبر الباقة نشطة إلا إذا كان `vip_status` يحتوي على `package_id` صالح وتاريخ `expires_at` في المستقبل.
    - إذا كانت الباقة منتهية الصلاحية أو غير موجودة، يتم إرجاع `is_vip: False` وتنظيف أعمدة `is_vip` و `vip_active` في قاعدة البيانات فوراً.
    - لا تُمنح مميزات الإحالة الخاصة بـ VIP إلا إذا كانت الباقة النشطة تتضمن مميزات الإحالة (referral_rate > 0 أو ضمن باقات الإحالة).
    """
    default_res = {
        "is_any_vip_active": False,
        "has_referral_vip": False,
        "package_id": None,
        "expires_at": None,
        "referral_rate": None,
        "ref_min_upgrades": None,
        "ref_withdraw_fee": None,
    }
    try:
        clean_uid = _clean_id(tg_id)
        if not clean_uid:
            return default_res

        now_ts = time.time()
        if user_data is None:
            user_data = database.get_user(clean_uid) or {}

        if not user_data or not isinstance(user_data, dict):
            return default_res

        vip_map = _parse_json(user_data.get("vip_status"), {})
        is_valid_active = False
        pkg_id = None
        exp_ts = None

        if isinstance(vip_map, dict) and vip_map:
            is_explicitly_inactive = (
                vip_map.get("is_active") is False
                or vip_map.get("active") is False
                or str(vip_map.get("status", "")).lower() == "inactive"
            )
            pkg_id = str(vip_map.get("package_id") or "").strip().upper()
            expires_raw = vip_map.get("expires_at")
            exp_ts = _parse_timestamp(expires_raw)

            # الشرط الصارم: وجود معرف باقة وتاريخ انتهاء صالح في المستقبل
            if not is_explicitly_inactive and pkg_id and exp_ts is not None and exp_ts > now_ts:
                is_valid_active = True

        # إذا لم تكن هناك باقة نشطة فعلياً في vip_status، نصفر أي علامات VIP قديمة عالقة في جدول users
        if not is_valid_active:
            if user_data.get("is_vip") or user_data.get("vip_active"):
                try:
                    with database.get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                UPDATE users
                                SET is_vip = FALSE,
                                    vip_active = FALSE,
                                    bot_active = FALSE,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE tg_id = %s
                                """,
                                (clean_uid,),
                            )
                except Exception:
                    pass
            return default_res

        # الباقة نشطة فعلياً في المتجر -> نتحقق هل هذه الباقة تشمل مميزات الإحالة؟
        raw_ref_rate = vip_map.get("referral_rate")
        try:
            ref_rate_val = float(raw_ref_rate) if raw_ref_rate is not None else 0.0
        except (ValueError, TypeError):
            ref_rate_val = 0.0

        has_ref_perks = (ref_rate_val > 0.0) or (pkg_id in REFERRAL_VIP_PACKAGES and raw_ref_rate is None)

        if not has_ref_perks:
            return {
                "is_any_vip_active": True,
                "has_referral_vip": False,
                "package_id": pkg_id,
                "expires_at": vip_map.get("expires_at"),
                "referral_rate": None,
                "ref_min_upgrades": None,
                "ref_withdraw_fee": None,
            }

        # تحويل النسبة إذا كانت عشرية (مثلاً 0.12 -> 12.0%)
        comm_percent = (ref_rate_val * 100.0) if (0.0 < ref_rate_val <= 1.0) else (ref_rate_val if ref_rate_val > 1.0 else 12.0)
        ref_min_upg = int(vip_map.get("ref_min_upgrades") or 3)
        ref_fee = float(vip_map.get("ref_withdraw_fee") if vip_map.get("ref_withdraw_fee") is not None else 0.0)

        return {
            "is_any_vip_active": True,
            "has_referral_vip": True,
            "package_id": pkg_id,
            "expires_at": vip_map.get("expires_at"),
            "referral_rate": round(comm_percent, 2),
            "ref_min_upgrades": max(1, ref_min_upg),
            "ref_withdraw_fee": max(0.0, ref_fee),
        }
    except Exception as e:
        print(f"⚠️ Error checking VIP referral details for {tg_id}: {e}")
        return default_res


def is_user_vip(tg_id, user_data=None):
    """إرجاع True فقط إذا كان المستخدم يملك باقة VIP نشطة حالياً وتمنح مميزات الإحالة"""
    details = get_active_vip_referral_details(tg_id, user_data=user_data)
    return bool(details.get("has_referral_vip"))


def get_friends_config(force_refresh=True):
    """جلب إعدادات نظام الأصدقاء مباشرة وبشكل لحظي من جدول settings في Supabase"""
    global _CONFIG_CACHE
    init_friends_tables()
    now_ts = time.time()

    if not force_refresh and CACHE_TTL_SECONDS > 0 and _CONFIG_CACHE["data"] and (now_ts - _CONFIG_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _CONFIG_CACHE["data"].copy()

    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT value FROM settings WHERE key = 'friends_config' LIMIT 1;")
                row = cur.fetchone()

                config = DEFAULT_FRIENDS_CONFIG.copy()
                if row and row.get("value"):
                    db_val = _parse_json(row.get("value"), {})
                    if isinstance(db_val, dict):
                        config.update(db_val)
                else:
                    cur.execute("""
                        INSERT INTO settings (key, value, updated_at)
                        VALUES ('friends_config', %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (key) DO NOTHING;
                    """, (Json(config),))

                try:
                    min_upg = int(float(config.get("min_upgrades_for_task", 5)))
                    config["min_upgrades_for_task"] = max(1, min_upg)
                except (ValueError, TypeError):
                    config["min_upgrades_for_task"] = 5

                if "vip_min_upgrades_for_task" not in config:
                    config["vip_min_upgrades_for_task"] = 3

                _CONFIG_CACHE = {"data": config, "timestamp": now_ts}
                return config.copy()
    except Exception as e:
        print(f"⚠️ Error getting friends config from Supabase: {e}")
        fallback = (_CONFIG_CACHE["data"] or DEFAULT_FRIENDS_CONFIG).copy()
        return fallback


def register_referral_db(referrer_id, friend_id, friend_name="صديق"):
    """تسجيل علاقة دعوة صديق جديد بأمان تام مع الحماية من الغش والإحالة الذاتية والعكسية"""
    init_friends_tables()
    ref_str = _clean_id(referrer_id)
    friend_str = _clean_id(friend_id)

    if not ref_str or not friend_str or ref_str == friend_str:
        return {"success": False, "error": "لا يمكنك دعوة نفسك"}

    if not ref_str.isdigit():
        return {"success": False, "error": "معرف الدعوة غير صالح"}

    safe_name = str(friend_name or "صديق").strip()[:100]

    try:
        with database.get_db_transaction() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. التأكد من عدم وجود إحالة عكسية أو حظر على الداعي
                cur.execute("SELECT ref_by, referred_by, is_banned, banned, status FROM users WHERE tg_id = %s LIMIT 1;", (ref_str,))
                ref_user = cur.fetchone()
                if ref_user:
                    if ref_user.get("ref_by") == friend_str or ref_user.get("referred_by") == friend_str:
                        return {"success": False, "error": "إحالة عكسية غير مسموحة"}
                    if _is_row_banned(dict(ref_user)):
                        return {"success": False, "error": "حساب الداعي غير نشط"}

                # 2. التأكد من وجود حساب للمُحيل وللصديق
                cur.execute("""
                    INSERT INTO users (tg_id, user_id, telegram_id, first_name, name)
                    VALUES (%s, %s, %s, 'لاعب', 'لاعب')
                    ON CONFLICT (tg_id) DO NOTHING;
                """, (ref_str, ref_str, ref_str))

                cur.execute("""
                    INSERT INTO users (tg_id, user_id, telegram_id, first_name, name, ref_by, referred_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tg_id) DO NOTHING;
                """, (friend_str, friend_str, friend_str, safe_name, safe_name, ref_str, ref_str))

                # 3. فحص بيانات الصديق الحالية
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (friend_str,))
                friend_row = dict(cur.fetchone() or {})
                existing_ref = _clean_id(friend_row.get("ref_by") or friend_row.get("referred_by"))

                if existing_ref and existing_ref != ref_str:
                    return {"success": False, "error": "هذا المستخدم مسجل مسبقاً عبر دعوة أخرى"}

                cur.execute("SELECT referrer_id FROM user_friends WHERE friend_id = %s LIMIT 1;", (friend_str,))
                uf_existing = cur.fetchone()
                if uf_existing:
                    if str(uf_existing.get("referrer_id")) == ref_str:
                        return {"success": True, "already_registered": True}
                    return {"success": False, "error": "المستخدم مرتبط بداعي آخر"}

                cur.execute("""
                    UPDATE users
                    SET ref_by = COALESCE(ref_by, %s),
                        referred_by = COALESCE(referred_by, %s)
                    WHERE tg_id = %s;
                """, (ref_str, ref_str, friend_str))

                upgrades_cnt = _calculate_upgrades_from_row(friend_row)
                real_name = friend_row.get("first_name") or friend_row.get("name") or safe_name

                cur.execute("""
                    INSERT INTO user_friends (referrer_id, friend_id, first_name, name, earned_from_him, upgrades_count, updated_at)
                    VALUES (%s, %s, %s, %s, 0.0, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (referrer_id, friend_id) DO UPDATE
                    SET upgrades_count = GREATEST(user_friends.upgrades_count, EXCLUDED.upgrades_count),
                        updated_at = CURRENT_TIMESTAMP;
                """, (ref_str, friend_str, real_name, real_name, upgrades_cnt))

                cur.execute("""
                    UPDATE users
                    SET referrals_count = (SELECT COUNT(*) FROM user_friends WHERE referrer_id = %s)
                    WHERE tg_id = %s;
                """, (ref_str, ref_str))

        return {"success": True, "referrer_id": ref_str, "friend_id": friend_str}
    except Exception as e:
        print(f"⚠️ Error registering referral ({ref_str} -> {friend_str}): {e}")
        return {"success": False, "error": "حدث خطأ أثناء تسجيل الدعوة"}


def sync_friend_upgrades_db(user_id, upgrades_count=None):
    """مزامنة وتحديث عدد ترقيات اللاعب فوراً في جدولي users و user_friends"""
    init_friends_tables()
    user_str = _clean_id(user_id)
    if not user_str:
        return False

    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT first_name, name, upgrades, upgrades_count, ref_by, referred_by FROM users WHERE tg_id = %s LIMIT 1;", (user_str,))
                row = cur.fetchone()
                if not row:
                    return False

                row_dict = dict(row)
                calc_upgrades = _calculate_upgrades_from_row(row_dict)
                if upgrades_count is not None:
                    calc_upgrades = max(calc_upgrades, int(upgrades_count))

                if int(row_dict.get("upgrades_count") or 0) != calc_upgrades:
                    cur.execute("UPDATE users SET upgrades_count = %s WHERE tg_id = %s;", (calc_upgrades, user_str))

                ref_id = _clean_id(row_dict.get("ref_by") or row_dict.get("referred_by"))
                u_name = row_dict.get("first_name") or row_dict.get("name") or "صديق"

                if ref_id and ref_id != user_str:
                    cur.execute("""
                        INSERT INTO user_friends (referrer_id, friend_id, first_name, name, earned_from_him, upgrades_count, updated_at)
                        VALUES (%s, %s, %s, %s, 0.0, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (referrer_id, friend_id) DO UPDATE
                        SET upgrades_count = %s,
                            first_name = EXCLUDED.first_name,
                            name = EXCLUDED.name,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (ref_id, user_str, u_name, u_name, calc_upgrades, calc_upgrades))
                else:
                    cur.execute("""
                        UPDATE user_friends
                        SET upgrades_count = %s,
                            first_name = %s,
                            name = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE friend_id = %s;
                    """, (calc_upgrades, u_name, u_name, user_str))
        return True
    except Exception as e:
        print(f"⚠️ Error syncing friend upgrades for {user_str}: {e}")
        return False


def get_user_friends(tg_id, limit=100):
    """
    جلب قائمة الأصدقاء والإحالات الخاصة بالمستخدم من Supabase بشكل لحظي
    مع فحص حالة الحظر لكل صديق لمنع احتساب الحسابات الوهمية المحظورة في المهام.
    """
    init_friends_tables()
    ref_str = _clean_id(tg_id)
    if not ref_str:
        return []

    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO user_friends (referrer_id, friend_id, first_name, name, earned_from_him, upgrades_count, updated_at)
                    SELECT %s, u.tg_id, COALESCE(u.first_name, u.name, 'صديق'), COALESCE(u.first_name, u.name, 'صديق'), 0.0, COALESCE(u.upgrades_count, 0), CURRENT_TIMESTAMP
                    FROM users u
                    WHERE (u.ref_by = %s OR u.referred_by = %s) AND u.tg_id != %s
                    ON CONFLICT (referrer_id, friend_id) DO NOTHING;
                """, (ref_str, ref_str, ref_str, ref_str))

                cur.execute("""
                    SELECT 
                        uf.friend_id AS tg_id,
                        uf.first_name AS uf_first_name,
                        uf.name AS uf_name,
                        u.first_name AS u_first_name,
                        u.name AS u_name,
                        COALESCE(uf.earned_from_him, 0.0) AS earned_from_him,
                        COALESCE(uf.upgrades_count, 0) AS uf_upgrades_count,
                        COALESCE(u.upgrades_count, 0) AS u_upgrades_count,
                        u.upgrades AS u_upgrades,
                        (COALESCE(u.is_banned, FALSE) OR COALESCE(u.banned, FALSE) OR (u.status = 'banned')) AS is_friend_banned
                    FROM user_friends uf
                    LEFT JOIN users u ON u.tg_id = uf.friend_id
                    WHERE uf.referrer_id = %s
                    ORDER BY uf.id DESC
                    LIMIT %s;
                """, (ref_str, int(limit)))
                rows = cur.fetchall() or []

                friends = []
                for r in rows:
                    r_dict = dict(r)
                    fid = str(r_dict.get("tg_id"))
                    is_friend_banned = bool(r_dict.get("is_friend_banned"))

                    uf_name = (r_dict.get("uf_name") or r_dict.get("uf_first_name") or "").strip()
                    u_name = (r_dict.get("u_first_name") or r_dict.get("u_name") or "").strip()
                    if uf_name and uf_name not in ("صديق", "لاعب"):
                        fname = uf_name
                    elif u_name:
                        fname = u_name
                    else:
                        fname = uf_name or "صديق"

                    earned = round(float(r_dict.get("earned_from_him") or 0.0), 6)

                    uf_upg = int(r_dict.get("uf_upgrades_count") or 0)
                    u_upg = int(r_dict.get("u_upgrades_count") or 0)
                    json_upg = _calculate_json_upgrades(r_dict.get("u_upgrades"))

                    live_upgrades = max(u_upg, json_upg) if (u_upg > 0 or json_upg > 0) else uf_upg
                    if live_upgrades != uf_upg:
                        cur.execute("""
                            UPDATE user_friends
                            SET upgrades_count = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE referrer_id = %s AND friend_id = %s;
                        """, (live_upgrades, ref_str, fid))

                    friends.append({
                        "tg_id": fid,
                        "name": fname,
                        "first_name": fname,
                        "generated": earned,
                        "earned_from_him": earned,
                        "upgrades_count": 0 if is_friend_banned else live_upgrades,
                        "is_banned": is_friend_banned
                    })

                return friends
    except Exception as e:
        print(f"❌ Error getting user friends for {tg_id}: {e}")
        return []


def add_referral_reward(referrer_id, user_id, mined_amount, user_upgrades_count=None, user_name=None):
    """إضافة أرباح التعدين للمُحيل وتحديث بيانات الصديق تلقائياً مع فحص صارم لباقة VIP وعدم الحظر"""
    init_friends_tables()
    ref_str = _clean_id(referrer_id)
    user_str = _clean_id(user_id)

    try:
        if not ref_str or not user_str or ref_str == user_str or float(mined_amount or 0) <= 0:
            return False

        config = get_friends_config()
        referrer_data = database.get_user(ref_str) or {}
        if not referrer_data or _is_row_banned(referrer_data):
            return False

        vip_details = get_active_vip_referral_details(ref_str, user_data=referrer_data)
        if vip_details.get("has_referral_vip"):
            comm_percent = float(vip_details.get("referral_rate") or config.get("vip_commission_percent", 12.0)) / 100.0
        else:
            comm_percent = float(config.get("commission_percent", 10.0)) / 100.0

        reward = round(float(mined_amount) * comm_percent, 6)
        if reward <= 0:
            return False

        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT first_name, name, upgrades, upgrades_count, is_banned, banned, status FROM users WHERE tg_id = %s LIMIT 1;", (user_str,))
                f_row = dict(cur.fetchone() or {})
                if _is_row_banned(f_row):
                    return False

                cur.execute("""
                    UPDATE users
                    SET pending_ref_earnings = COALESCE(pending_ref_earnings, 0.0) + %s,
                        total_ref_earnings = COALESCE(total_ref_earnings, 0.0) + %s
                    WHERE tg_id = %s
                      AND COALESCE(is_banned, FALSE) = FALSE
                      AND COALESCE(banned, FALSE) = FALSE;
                """, (reward, reward, ref_str))

                resolved_name = str(user_name or f_row.get("first_name") or f_row.get("name") or "صديق")[:100]
                resolved_upgrades = _calculate_upgrades_from_row(f_row)
                if user_upgrades_count is not None:
                    resolved_upgrades = max(resolved_upgrades, int(user_upgrades_count))

                cur.execute("""
                    INSERT INTO user_friends (referrer_id, friend_id, first_name, name, earned_from_him, upgrades_count, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (referrer_id, friend_id) DO UPDATE
                    SET earned_from_him = COALESCE(user_friends.earned_from_him, 0.0) + EXCLUDED.earned_from_him,
                        first_name = EXCLUDED.first_name,
                        name = EXCLUDED.name,
                        upgrades_count = GREATEST(user_friends.upgrades_count, EXCLUDED.upgrades_count),
                        updated_at = CURRENT_TIMESTAMP;
                """, (ref_str, user_str, resolved_name, resolved_name, reward, resolved_upgrades))

        return True
    except Exception as e:
        print(f"❌ Error adding referral reward for {referrer_id}: {e}")
        return False


def get_friends_list_db(tg_id):
    """جلب قائمة الأصدقاء للاستخدام في API الأصدقاء"""
    return get_user_friends(tg_id)


def get_friends_data_db(tg_id, start_param=None, user_name=None):
    """جلب ملخص إحصائيات الأصدقاء والمكافآت وإعدادات قائمة الأصدقاء مع مطابقة حقيقية لحالة باقة VIP"""
    init_friends_tables()
    tg_str = _clean_id(tg_id)
    if not tg_str:
        return {}

    try:
        ref_candidate = _clean_id(start_param) if start_param else None
        database.init_user(tg_str, ref_id=ref_candidate, first_name=user_name or "لاعب")

        user_data = {}
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s LIMIT 1;", (tg_str,))
                row = cur.fetchone()
                if row:
                    user_data = dict(row)

        if not user_data:
            user_data = database.get_user(tg_str) or {}

        friends = get_user_friends(tg_str)
        config = get_friends_config(force_refresh=True).copy()

        # فحص صارم للباقة النشطة في المتجر وما إذا كانت تمنح مميزات إحالة
        vip_details = get_active_vip_referral_details(tg_str, user_data=user_data)
        has_ref_vip = bool(vip_details.get("has_referral_vip"))

        base_min_upgrades = int(config.get("min_upgrades_for_task", 5))
        vip_min_upgrades = int(config.get("vip_min_upgrades_for_task", 3))

        if has_ref_vip:
            effective_commission = float(vip_details.get("referral_rate") or config.get("vip_commission_percent", 12.0))
            effective_claim_fee = float(
                vip_details.get("ref_withdraw_fee")
                if vip_details.get("ref_withdraw_fee") is not None
                else config.get("vip_claim_fee_percent", 0.0)
            )
            effective_min_upgrades = int(vip_details.get("ref_min_upgrades") or vip_min_upgrades)
        else:
            effective_commission = float(config.get("commission_percent", 10.0))
            effective_claim_fee = float(config.get("claim_fee_percent", 1.5))
            effective_min_upgrades = base_min_upgrades

        config["min_upgrades_for_task"] = base_min_upgrades
        config["vip_min_upgrades_for_task"] = vip_min_upgrades

        # احتساب الأصدقاء المؤهلين (غير المحظورين فقط) بناءً على الشرط الفعّال
        eligible_count = sum(
            1 for f in friends
            if not f.get("is_banned") and int(f.get("upgrades_count", 0) or 0) >= effective_min_upgrades
        )

        claimed_tasks = _parse_json(user_data.get("claimed_ref_tasks"), [])
        if not isinstance(claimed_tasks, list):
            claimed_tasks = []

        return {
            "balance": round(float(user_data.get("balance", 0.0) or 0.0), 6),
            "pending_ref_earnings": round(float(user_data.get("pending_ref_earnings", 0.0) or 0.0), 6),
            "total_ref_earnings": round(float(user_data.get("total_ref_earnings", 0.0) or 0.0), 6),
            "invited_friends_count": len(friends),
            "eligible_task_friends_count": eligible_count,
            "claimed_ref_tasks": [str(t) for t in claimed_tasks],
            "referral_code": tg_str,
            "is_vip": has_ref_vip,
            "active_vip_package": vip_details.get("package_id") if vip_details.get("is_any_vip_active") else None,
            "effective_commission": effective_commission,
            "effective_claim_fee": effective_claim_fee,
            "effective_min_upgrades": effective_min_upgrades,
            "friends_config": config,
            "friends": friends
        }
    except Exception as e:
        print(f"❌ Error getting friends data for {tg_id}: {e}")
        config = get_friends_config(force_refresh=False).copy()
        return {
            "balance": 0.0,
            "pending_ref_earnings": 0.0,
            "total_ref_earnings": 0.0,
            "invited_friends_count": 0,
            "eligible_task_friends_count": 0,
            "claimed_ref_tasks": [],
            "referral_code": str(tg_id),
            "is_vip": False,
            "active_vip_package": None,
            "effective_commission": 10.0,
            "effective_claim_fee": 1.5,
            "effective_min_upgrades": int(config.get("min_upgrades_for_task", 5)),
            "friends_config": config,
            "friends": []
        }


def claim_ref_earnings_db(tg_id):
    """سحب أرباح الإحالات المعلقة وتحويلها للرصيد الرئيسي داخل معاملة SQL ذرية آمنة (FOR UPDATE)"""
    init_friends_tables()
    tg_str = _clean_id(tg_id)
    if not tg_str:
        return {"success": False, "error": "معرف المستخدم غير صالح"}

    with _get_user_lock(tg_str):
        try:
            config = get_friends_config(force_refresh=True)
            with database.get_db_transaction() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (tg_str,))
                    user_row = cur.fetchone()
                    if not user_row:
                        return {"success": False, "error": "المستخدم غير موجود"}

                    data = dict(user_row)
                    if _is_row_banned(data):
                        return {"success": False, "error": "⛔ هذا الحساب محظور ولا يمكنه سحب الأرباح"}

                    pending = round(float(data.get("pending_ref_earnings") or 0.0), 6)
                    if pending <= 0:
                        return {"success": False, "error": "لا توجد أرباح معلقة للسحب"}

                    vip_details = get_active_vip_referral_details(tg_str, user_data=data)
                    has_ref_vip = bool(vip_details.get("has_referral_vip"))

                    if has_ref_vip:
                        claim_fee_percent = float(
                            vip_details.get("ref_withdraw_fee")
                            if vip_details.get("ref_withdraw_fee") is not None
                            else config.get("vip_claim_fee_percent", 0.0)
                        )
                    else:
                        claim_fee_percent = float(config.get("claim_fee_percent", 1.5))

                    fee_rate = max(0.0, min(100.0, claim_fee_percent)) / 100.0
                    fee_amount = round(pending * fee_rate, 6)
                    net_amount = round(pending - fee_amount, 6)
                    if net_amount <= 0:
                        return {"success": False, "error": "المبلغ المعلق صغير جداً للسحب"}

                    current_balance = round(float(data.get("balance") or 0.0), 6)
                    new_balance = round(current_balance + net_amount, 6)

                    cur.execute("""
                        UPDATE users
                        SET balance = %s,
                            pending_ref_earnings = 0.0,
                            last_active_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s;
                    """, (new_balance, tg_str))

            fee_msg = "معفي من الرسوم (0% VIP)" if has_ref_vip and claim_fee_percent == 0 else f"خصم {fee_amount} ZN رسوم ({claim_fee_percent}%)"
            return {
                "success": True,
                "claimed_amount": pending,
                "fee_amount": fee_amount,
                "net_amount": net_amount,
                "new_balance": new_balance,
                "is_vip": has_ref_vip,
                "effective_claim_fee": claim_fee_percent,
                "message": f"تم سحب {net_amount} ZN بنجاح إلى رصيدك ({fee_msg})"
            }
        except Exception as e:
            print(f"❌ Error claiming ref earnings for {tg_id}: {e}")
            return {"success": False, "error": "حدث خطأ أثناء تنفيذ عملية السحب"}


def claim_ref_task_db(tg_id, task_id, reward=0, req_friends=1):
    """
    استلام مكافأة مهمة دعوة الأصدقاء داخل معاملة SQL ذرية آمنة (FOR UPDATE):
    - يعتمد حصرياً على حالة باقة VIP الحقيقية ويستبعد الأصدقاء المحظورين.
    """
    init_friends_tables()
    tg_str = _clean_id(tg_id)
    task_key = str(task_id).strip()

    if not tg_str or not task_key:
        return {"success": False, "error": "بيانات المهمة غير صالحة"}

    with _get_user_lock(tg_str):
        try:
            config = get_friends_config(force_refresh=True)
            ref_tasks = config.get("ref_tasks") or DEFAULT_FRIENDS_CONFIG["ref_tasks"]

            task_info = ref_tasks.get(task_key)
            if not isinstance(task_info, dict):
                return {"success": False, "error": "هذه المهمة غير موجودة أو غير صالحة"}

            actual_req_friends = int(task_info.get("reqFriends", 1))
            actual_reward = round(float(task_info.get("reward", 0.0)), 6)

            if actual_reward <= 0 or actual_req_friends <= 0:
                return {"success": False, "error": "إعدادات المهمة غير صالحة"}

            friends = get_user_friends(tg_str)

            with database.get_db_transaction() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE;", (tg_str,))
                    user_row = cur.fetchone()
                    if not user_row:
                        return {"success": False, "error": "المستخدم غير موجود"}

                    snap_data = dict(user_row)
                    if _is_row_banned(snap_data):
                        return {"success": False, "error": "⛔ هذا الحساب محظور ولا يمكنه استلام المكافآت"}

                    vip_details = get_active_vip_referral_details(tg_str, user_data=snap_data)
                    has_ref_vip = bool(vip_details.get("has_referral_vip"))

                    base_min_upgrades = int(config.get("min_upgrades_for_task", 5))
                    vip_min_upgrades = int(config.get("vip_min_upgrades_for_task", 3))

                    if has_ref_vip:
                        effective_min_upgrades = int(vip_details.get("ref_min_upgrades") or vip_min_upgrades)
                    else:
                        effective_min_upgrades = base_min_upgrades

                    eligible_count = sum(
                        1 for f in friends
                        if not f.get("is_banned") and int(f.get("upgrades_count", 0) or 0) >= effective_min_upgrades
                    )

                    if eligible_count < actual_req_friends:
                        return {
                            "success": False,
                            "error": f"تحتاج إلى {actual_req_friends} أصدقاء مؤهلين (+{effective_min_upgrades} ترقيات لكل صديق) لاستلام هذه المكافأة"
                        }

                    claimed_tasks = _parse_json(snap_data.get("claimed_ref_tasks"), [])
                    if not isinstance(claimed_tasks, list):
                        claimed_tasks = []
                    claimed_str_list = [str(t) for t in claimed_tasks]

                    if task_key in claimed_str_list:
                        return {"success": False, "error": "تم استلام مكافأة هذه المهمة من قبل"}

                    current_balance = round(float(snap_data.get("balance") or 0.0), 6)
                    new_balance = round(current_balance + actual_reward, 6)
                    claimed_str_list.append(task_key)

                    cur.execute("""
                        UPDATE users
                        SET balance = %s,
                            claimed_ref_tasks = %s,
                            last_active_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s;
                    """, (new_balance, Json(claimed_str_list), tg_str))

            return {
                "success": True,
                "new_balance": new_balance,
                "claimed_ref_tasks": claimed_str_list,
                "is_vip": has_ref_vip,
                "effective_min_upgrades": effective_min_upgrades,
                "message": f"تم استلام مكافأة {actual_reward} ZN بنجاح"
            }
        except Exception as e:
            print(f"❌ Error claiming ref task for {tg_id}: {e}")
            return {"success": False, "error": "حدث خطأ أثناء استلام مكافأة المهمة"}

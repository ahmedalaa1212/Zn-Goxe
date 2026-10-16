import os
import time
import json
import threading
from datetime import datetime, timezone
import database

# قفل حماية لمنع العمليات المتزامنة (Race Conditions / Double Claim) لنفس المستخدم
_USER_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _get_user_lock(tg_id):
    key = str(tg_id)
    with _LOCKS_GUARD:
        if key not in _USER_LOCKS:
            _USER_LOCKS[key] = threading.RLock()
        return _USER_LOCKS[key]


# الإعدادات الافتراضية لنظام الأصدقاء (تم ضبط شرط الترقيات إلى 3 ترقيات)
DEFAULT_FRIENDS_CONFIG = {
    "commission_percent": 10.0,       # نسبة أرباح الإحالة العادية (10%)
    "vip_commission_percent": 12.0,   # نسبة أرباح الإحالة لمشتركي VIP (12%)
    "claim_fee_percent": 1.5,         # نسبة عمولة السحب العادية (1.5%)
    "vip_claim_fee_percent": 0.0,     # نسبة عمولة السحب لمشتركي VIP (0%)
    "min_upgrades_for_task": 3,       # عدد الترقيات المطلوب لاحتساب الصديق مؤهل للمهام (3 ترقيات)
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

# ذاكرة تخزين مؤقت مع توقيت صلاحية (TTL) لتوفير استهلاك قاعدة البيانات
_CONFIG_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 60
_SCHEMA_INITIALIZED = False
_SCHEMA_LOCK = threading.Lock()


# ==============================================================================
# اتصالات Supabase والإنشاء التلقائي للجداول والأعمدة
# ==============================================================================

def _get_supabase_client():
    """جلب عميل Supabase من ملف database بأمان"""
    if hasattr(database, "get_db"):
        db = database.get_db()
        if db is not None:
            return db
    if hasattr(database, "supabase") and database.supabase is not None:
        return database.supabase
    if hasattr(database, "client") and database.client is not None:
        return database.client
    raise RuntimeError("لم يتم العثور على اتصال Supabase صالح داخل database.py")


def _get_pg_connection():
    """جلب اتصال PostgreSQL مباشر (إن وجد) لإنشاء الجداول والأعمدة تلقائياً"""
    for attr in ("get_pg_conn", "get_connection", "get_conn"):
        if hasattr(database, attr):
            try:
                conn = getattr(database, attr)()
                if conn is not None:
                    return conn, True
            except Exception:
                pass

    db_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or os.environ.get("POSTGRES_URL")
        or getattr(database, "DATABASE_URL", None)
    )
    if db_url:
        try:
            import psycopg2
            conn = psycopg2.connect(db_url)
            return conn, True
        except Exception:
            pass
    return None, False


def init_friends_tables():
    """إنشاء وتجهيز كافة الجداول والأعمدة والدوال المطلوبة في Supabase تلقائياً"""
    global _SCHEMA_INITIALIZED
    if _SCHEMA_INITIALIZED:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_INITIALIZED:
            return

        conn, should_close = _get_pg_connection()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    # 1. جدول الإعدادات العامة
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.settings (
                            key TEXT PRIMARY KEY,
                            value JSONB NOT NULL DEFAULT '{}'::jsonb,
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        );
                    """)

                    # 2. جدول المستخدمين والتأكد من وجود كافة أعمدة الأصدقاء والـ VIP والترقيات
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.users (
                            tg_id TEXT PRIMARY KEY,
                            first_name TEXT DEFAULT 'لاعب',
                            name TEXT DEFAULT 'لاعب',
                            balance NUMERIC(20, 6) DEFAULT 0.0,
                            pending_ref_earnings NUMERIC(20, 6) DEFAULT 0.0,
                            total_ref_earnings NUMERIC(20, 6) DEFAULT 0.0,
                            referred_by TEXT,
                            upgrades_count INTEGER DEFAULT 0,
                            upgrades JSONB DEFAULT '{}'::jsonb,
                            claimed_ref_tasks JSONB DEFAULT '[]'::jsonb,
                            vip_status JSONB DEFAULT '{}'::jsonb,
                            is_vip BOOLEAN DEFAULT FALSE,
                            vip_active BOOLEAN DEFAULT FALSE,
                            plan TEXT,
                            vip_package TEXT,
                            vip_level TEXT,
                            vip_expires TEXT,
                            vip_expires_at TEXT,
                            expires_at TEXT,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        );
                    """)

                    alter_columns = [
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS first_name TEXT DEFAULT 'لاعب';",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS name TEXT DEFAULT 'لاعب';",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS balance NUMERIC(20, 6) DEFAULT 0.0;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS pending_ref_earnings NUMERIC(20, 6) DEFAULT 0.0;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS total_ref_earnings NUMERIC(20, 6) DEFAULT 0.0;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS referred_by TEXT;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS upgrades_count INTEGER DEFAULT 0;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS upgrades JSONB DEFAULT '{}'::jsonb;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS claimed_ref_tasks JSONB DEFAULT '[]'::jsonb;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS vip_status JSONB DEFAULT '{}'::jsonb;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS vip_active BOOLEAN DEFAULT FALSE;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS plan TEXT;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS vip_package TEXT;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS vip_level TEXT;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS vip_expires TEXT;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS vip_expires_at TEXT;",
                        "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS expires_at TEXT;"
                    ]
                    for stmt in alter_columns:
                        try:
                            cur.execute(stmt)
                        except Exception:
                            conn.rollback()

                    # 3. جدول سجل الأصدقاء والإحالات (بديل Subcollection الفايربيس)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.user_friends (
                            id BIGSERIAL PRIMARY KEY,
                            referrer_id TEXT NOT NULL,
                            friend_id TEXT NOT NULL,
                            first_name TEXT DEFAULT 'صديق',
                            name TEXT DEFAULT 'صديق',
                            earned_from_him NUMERIC(20, 6) DEFAULT 0.0,
                            upgrades_count INTEGER DEFAULT 0,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ DEFAULT NOW(),
                            CONSTRAINT uq_referrer_friend UNIQUE (referrer_id, friend_id)
                        );
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_friends_referrer ON public.user_friends(referrer_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_friends_friend ON public.user_friends(friend_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_referred_by ON public.users(referred_by);")

                    # 4. إدراج أو تحديث إعدادات الأصدقاء الافتراضية مع ضمان أن الترقيات المطلوبة = 3
                    cur.execute("""
                        INSERT INTO public.settings (key, value, updated_at)
                        VALUES ('friends_config', %s::jsonb, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = jsonb_set(public.settings.value, '{min_upgrades_for_task}', '3'::jsonb, true),
                            updated_at = NOW();
                    """, (json.dumps(DEFAULT_FRIENDS_CONFIG),))

                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                print(f"⚠️ Warning during auto-initializing Supabase schema: {e}")
            finally:
                if should_close:
                    try:
                        conn.close()
                    except Exception:
                        pass

        _SCHEMA_INITIALIZED = True


# تشغيل التهيئة التلقائية عند تحميل الموديول
init_friends_tables()


# ==============================================================================
# دوال مساعدة للتعامل المرن مع Supabase
# ==============================================================================

def _parse_json_field(val, default):
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return default
    return default


def _parse_timestamp(val):
    """دالة مساعدة لتحليل وتوحيد قراءة التواريخ والطوابع الزمنية بأشكالها المختلفة"""
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
            clean_str = val_str.replace('Z', '+00:00')
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


def _calculate_user_upgrades(user_row):
    """
    حساب العدد الفعلي لترقيات اللاعب من كافة الحقول المحتملة في جدول users
    لضمان قراءة الترقيات فور شرائها من المتجر أو المزرعة بدون أي تأخير.
    """
    if not isinstance(user_row, dict):
        return 0

    candidates = []

    # 1. الحقول الرقمية المباشرة
    for col in ("upgrades_count", "total_upgrades", "upgrade_count"):
        raw_val = user_row.get(col)
        if raw_val is not None:
            try:
                candidates.append(int(float(raw_val)))
            except (ValueError, TypeError):
                pass

    # 2. حقل upgrades من نوع JSONB (سواء كان قاموس مستويات أو قائمة)
    upgrades_data = _parse_json_field(user_row.get("upgrades"), {})
    if isinstance(upgrades_data, dict):
        calc_sum = 0
        for k, v in upgrades_data.items():
            if isinstance(v, (int, float)):
                calc_sum += max(0, int(v))
            elif isinstance(v, dict):
                lvl = v.get("level") or v.get("count") or v.get("lvl") or 0
                try:
                    calc_sum += max(0, int(lvl))
                except (ValueError, TypeError):
                    pass
        candidates.append(calc_sum)
    elif isinstance(upgrades_data, list):
        candidates.append(len(upgrades_data))

    # 3. مستويات السرعة/التعدين إذا كانت مخزنة كأعمدة مستقلة (تبدأ من المستوى 1 افتراضياً)
    level_sum = 0
    for lvl_col in ("mining_level", "speed_level", "storage_level", "power_level", "rig_level"):
        val = user_row.get(lvl_col)
        if val is not None:
            try:
                lvl_int = int(float(val))
                if lvl_int > 1:
                    level_sum += (lvl_int - 1)
            except (ValueError, TypeError):
                pass
    if level_sum > 0:
        candidates.append(level_sum)

    return max(candidates) if candidates else 0


def _fetch_user_row(tg_id):
    """جلب بيانات المستخدم من جدول users في Supabase مع دعم البحث بـ tg_id أو id"""
    tg_str = str(tg_id).strip()
    if not tg_str:
        return None

    sb = _get_supabase_client()
    try:
        res = sb.table("users").select("*").eq("tg_id", tg_str).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass

    try:
        res = sb.table("users").select("*").eq("id", tg_str).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass

    return None


def _ensure_user_exists(tg_id, name=None):
    """التأكد من وجود سجل للمستخدم في جدول users وإنشاؤه تلقائياً إذا لم يكن موجوداً"""
    existing = _fetch_user_row(tg_id)
    if existing is not None:
        return existing

    tg_str = str(tg_id).strip()
    clean_name = (name or "لاعب").strip()[:64]
    new_user = {
        "tg_id": tg_str,
        "first_name": clean_name,
        "name": clean_name,
        "balance": 0.0,
        "pending_ref_earnings": 0.0,
        "total_ref_earnings": 0.0,
        "upgrades_count": 0,
        "claimed_ref_tasks": []
    }
    try:
        sb = _get_supabase_client()
        res = sb.table("users").upsert(new_user, on_conflict="tg_id").execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception as e:
        print(f"⚠️ Warning creating user {tg_str} in Supabase: {e}")

    return new_user


def _update_user_row(tg_id, update_dict):
    """تحديث بيانات المستخدم في جدول users بأمان"""
    tg_str = str(tg_id).strip()
    sb = _get_supabase_client()
    try:
        res = sb.table("users").update(update_dict).eq("tg_id", tg_str).execute()
        if res.data:
            return True
    except Exception as e:
        # في حال كان جدول المستخدمين يعتمد على عمود id بدلاً من tg_id
        try:
            res = sb.table("users").update(update_dict).eq("id", tg_str).execute()
            if res.data:
                return True
        except Exception:
            print(f"❌ Error updating user {tg_str}: {e}")
    return False


# ==============================================================================
# الدوال الأساسية لنظام الأصدقاء والـ VIP
# ==============================================================================

def is_user_vip(tg_id, user_data=None):
    """التحقق مما إذا كان المستخدم يمتلك اشتراك VIP نشط بجميع الأشكال والتنسيقات في Supabase"""
    try:
        now_ts = time.time()
        if user_data is None:
            user_data = _fetch_user_row(tg_id) or {}

        if not user_data:
            return False

        # 1. فحص كائن vip_status (JSONB أو نص أو بوليان)
        vip_map = user_data.get("vip_status")
        if isinstance(vip_map, str) and vip_map.strip().startswith("{"):
            vip_map = _parse_json_field(vip_map, {})

        if isinstance(vip_map, dict) and vip_map:
            is_explicitly_inactive = (
                vip_map.get("is_active") is False
                or vip_map.get("active") is False
                or str(vip_map.get("status", "")).lower() == "inactive"
            )
            if not is_explicitly_inactive:
                expires_raw = (
                    vip_map.get("expires_at")
                    or vip_map.get("expiration_date")
                    or vip_map.get("expires")
                    or vip_map.get("end_date")
                    or vip_map.get("valid_until")
                )
                exp_ts = _parse_timestamp(expires_raw)
                if exp_ts is not None:
                    if exp_ts > now_ts:
                        return True
                else:
                    package_id = (
                        vip_map.get("package_id")
                        or vip_map.get("vip_package")
                        or vip_map.get("plan")
                        or vip_map.get("level")
                    )
                    if vip_map.get("is_active") is True or vip_map.get("active") is True or package_id:
                        return True
        elif isinstance(vip_map, bool) and vip_map:
            return True
        elif isinstance(vip_map, str) and (
            vip_map.lower() in ["true", "active"] or vip_map.upper().startswith("VIP")
        ):
            return True

        # 2. فحص الحقول المباشرة في سجل المستخدم
        if user_data.get("vip_active") is True or user_data.get("is_vip") is True:
            direct_expires = (
                user_data.get("vip_expires")
                or user_data.get("vip_expires_at")
                or user_data.get("expires_at")
            )
            exp_ts = _parse_timestamp(direct_expires)
            if exp_ts is None or exp_ts > now_ts:
                return True

        direct_plan = (
            user_data.get("plan")
            or user_data.get("vip_package")
            or user_data.get("vip_level")
        )
        if isinstance(direct_plan, str) and (
            direct_plan.upper().startswith("VIP") or direct_plan.lower() in ["active", "true"]
        ):
            direct_expires = (
                user_data.get("vip_expires")
                or user_data.get("vip_expires_at")
                or user_data.get("expires_at")
            )
            exp_ts = _parse_timestamp(direct_expires)
            if exp_ts is None or exp_ts > now_ts:
                return True

        direct_expires = user_data.get("vip_expires") or user_data.get("vip_expires_at")
        exp_ts = _parse_timestamp(direct_expires)
        if exp_ts is not None and exp_ts > now_ts:
            return True

        return False
    except Exception as e:
        print(f"⚠️ Error checking VIP status for {tg_id}: {e}")
        return False


def get_friends_config(force_refresh=False):
    """جلب إعدادات نظام الأصدقاء من جدول settings في Supabase مع التأكد من أن شرط الترقية = 3"""
    global _CONFIG_CACHE
    now_ts = time.time()

    if not force_refresh and _CONFIG_CACHE["data"] and (now_ts - _CONFIG_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _CONFIG_CACHE["data"].copy()

    try:
        sb = _get_supabase_client()
        res = sb.table("settings").select("value").eq("key", "friends_config").limit(1).execute()

        config = DEFAULT_FRIENDS_CONFIG.copy()
        if res.data and len(res.data) > 0:
            raw_val = _parse_json_field(res.data[0].get("value"), {})
            if isinstance(raw_val, dict):
                config.update(raw_val)

            # إجبار شرط الترقيات على 3 ترقيات وتحديثه في قاعدة البيانات إذا كان قديماً (1)
            if int(config.get("min_upgrades_for_task", 3)) != 3:
                config["min_upgrades_for_task"] = 3
                try:
                    sb.table("settings").upsert({
                        "key": "friends_config",
                        "value": config,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }, on_conflict="key").execute()
                except Exception:
                    pass
        else:
            config["min_upgrades_for_task"] = 3
            try:
                sb.table("settings").upsert({
                    "key": "friends_config",
                    "value": config,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }, on_conflict="key").execute()
            except Exception:
                pass

        _CONFIG_CACHE = {"data": config, "timestamp": now_ts}
        return config.copy()
    except Exception as e:
        print(f"⚠️ Error getting friends config from Supabase: {e}")
        fallback = (_CONFIG_CACHE["data"] or DEFAULT_FRIENDS_CONFIG).copy()
        fallback["min_upgrades_for_task"] = 3
        return fallback


def register_referral_db(referrer_id, friend_id, friend_name="صديق"):
    """
    تسجيل إحالة صديق جديد بأمان تام مع الحماية من:
    1. دعوة النفس (Self-referral)
    2. تكرار تسجيل نفس الصديق أو تغيير الداعي السابق
    3. الإحالة الدائرية العكسية (A يدعو B ثم B يدعو A)
    """
    try:
        if not referrer_id or not friend_id:
            return {"success": False, "error": "بيانات الإحالة غير مكتملة"}

        ref_str = str(referrer_id).strip()
        if ref_str.startswith("ref_"):
            ref_str = ref_str.replace("ref_", "", 1).strip()

        friend_str = str(friend_id).strip()

        if not ref_str or not friend_str or ref_str == friend_str:
            return {"success": False, "error": "لا يمكنك دعوة نفسك"}

        if not ref_str.isdigit() and len(ref_str) < 3:
            return {"success": False, "error": "كود الدعوة غير صالح"}

        sb = _get_supabase_client()

        # التأكد من وجود المستخدم الصديق والمُحيل
        friend_row = _ensure_user_exists(friend_str, friend_name)
        _ensure_user_exists(ref_str)

        # منع تغيير المُحيل إذا كان الصديق مسجلاً بالفعل عبر شخص آخر
        existing_ref = str(friend_row.get("referred_by") or "").strip()
        if existing_ref and existing_ref != ref_str:
            return {"success": False, "error": "هذا المستخدم مسجل مسبقاً عبر دعوة أخرى"}

        # منع الإحالة الدائرية (التأكد أن الصديق لم يقم بدعوة المُحيل سابقاً)
        referrer_row = _fetch_user_row(ref_str) or {}
        if str(referrer_row.get("referred_by") or "").strip() == friend_str:
            return {"success": False, "error": "إحالة عكسية غير مسموحة"}

        # التحقق مما إذا كان مسجلاً مسبقاً في جدول user_friends
        existing_link = (
            sb.table("user_friends")
            .select("*")
            .eq("friend_id", friend_str)
            .limit(1)
            .execute()
        )
        if existing_link.data and len(existing_link.data) > 0:
            saved_ref = str(existing_link.data[0].get("referrer_id", ""))
            if saved_ref == ref_str:
                return {"success": True, "already_registered": True}
            return {"success": False, "error": "المستخدم مرتبط بداعي آخر"}

        real_name = (
            friend_name
            if (friend_name and friend_name != "صديق")
            else (friend_row.get("first_name") or friend_row.get("name") or "صديق")
        )
        upgrades_cnt = _calculate_user_upgrades(friend_row)

        # حفظ العلاقة في جدول user_friends وتحديث عمود referred_by في جدول users
        sb.table("user_friends").upsert({
            "referrer_id": ref_str,
            "friend_id": friend_str,
            "first_name": real_name,
            "name": real_name,
            "earned_from_him": 0.0,
            "upgrades_count": upgrades_cnt,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }, on_conflict="referrer_id,friend_id").execute()

        if not existing_ref:
            _update_user_row(friend_str, {"referred_by": ref_str})

        return {"success": True, "referrer_id": ref_str, "friend_id": friend_str}
    except Exception as e:
        print(f"⚠️ Error registering referral ({referrer_id} -> {friend_id}): {e}")
        return {"success": False, "error": "حدث خطأ أثناء تسجيل الدعوة"}


def sync_friend_upgrades_db(user_id, upgrades_count=None):
    """
    دالة لتحديث عدد ترقيات الصديق فوراً عند شرائه أي ترقية جديدة
    (يتم استدعاؤها تلقائياً عند عرض الأصدقاء ويمكن استدعاؤها من المتجر أيضاً)
    """
    try:
        user_str = str(user_id).strip()
        if not user_str:
            return False

        user_row = _fetch_user_row(user_str) or {}
        real_upgrades = (
            int(upgrades_count)
            if upgrades_count is not None
            else _calculate_user_upgrades(user_row)
        )

        # تحديث جدول المستخدمين إذا كانت القيمة المحسوبة أكبر
        if int(user_row.get("upgrades_count") or 0) != real_upgrades:
            _update_user_row(user_str, {"upgrades_count": real_upgrades})

        # تحديث جدول الأصدقاء user_friends
        sb = _get_supabase_client()
        sb.table("user_friends").update({
            "upgrades_count": real_upgrades,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("friend_id", user_str).execute()
        return True
    except Exception as e:
        print(f"⚠️ Error syncing friend upgrades for {user_id}: {e}")
        return False


def get_user_friends(tg_id, limit=100):
    """
    جلب قائمة الأصدقاء الخاصة بالمستخدم من Supabase مع:
    1. مزامنة أي صديق مسجل في users.referred_by ولم يُضف بعد إلى user_friends.
    2. قراءة عدد الترقيات الحقيقي والحي لكل صديق من جدول users مباشرةً.
    """
    try:
        ref_str = str(tg_id).strip()
        if not ref_str:
            return []

        sb = _get_supabase_client()

        # 1. جلب الأصدقاء المسجلين في جدول user_friends
        uf_res = (
            sb.table("user_friends")
            .select("*")
            .eq("referrer_id", ref_str)
            .limit(limit)
            .execute()
        )
        uf_rows = uf_res.data or []
        friends_by_id = {str(r.get("friend_id")): r for r in uf_rows if r.get("friend_id")}

        # 2. فحص جدول users للبحث عن أي مستخدم لديه referred_by == tg_id (لضمان عدم ضياع أي إحالة)
        try:
            referred_users_res = (
                sb.table("users")
                .select("*")
                .eq("referred_by", ref_str)
                .limit(limit)
                .execute()
            )
            referred_users = referred_users_res.data or []
        except Exception:
            referred_users = []

        live_user_map = {}
        for u in referred_users:
            uid = str(u.get("tg_id") or u.get("id") or "").strip()
            if uid and uid != ref_str:
                live_user_map[uid] = u
                if uid not in friends_by_id:
                    # مزامنة الصديق المكتشف تلقائياً في جدول user_friends
                    u_name = u.get("first_name") or u.get("name") or "صديق"
                    u_upgrades = _calculate_user_upgrades(u)
                    new_uf = {
                        "referrer_id": ref_str,
                        "friend_id": uid,
                        "first_name": u_name,
                        "name": u_name,
                        "earned_from_him": 0.0,
                        "upgrades_count": u_upgrades,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    friends_by_id[uid] = new_uf
                    try:
                        sb.table("user_friends").upsert(new_uf, on_conflict="referrer_id,friend_id").execute()
                    except Exception:
                        pass

        if not friends_by_id:
            return []

        # 3. جلب البيانات الحية لباقي الأصدقاء من جدول users لقراءة أحدث الترقيات والأسماء
        missing_live_ids = [fid for fid in friends_by_id.keys() if fid not in live_user_map]
        if missing_live_ids:
            try:
                batch_res = sb.table("users").select("*").in_("tg_id", missing_live_ids).execute()
                for u in (batch_res.data or []):
                    uid = str(u.get("tg_id") or u.get("id") or "").strip()
                    if uid:
                        live_user_map[uid] = u
            except Exception as fetch_err:
                print(f"⚠️ Warning fetching live friend profiles: {fetch_err}")

        # 4. تجميع القائمة النهائية وتحديث الترقيات المتغيرة
        friends_list = []
        for friend_id, uf_data in friends_by_id.items():
            real_user = live_user_map.get(friend_id, {})

            stored_upgrades = int(uf_data.get("upgrades_count", 0) or 0)
            live_upgrades = _calculate_user_upgrades(real_user) if real_user else stored_upgrades
            real_upgrades_count = max(stored_upgrades, live_upgrades)

            real_name = (
                real_user.get("first_name")
                or real_user.get("name")
                or uf_data.get("first_name")
                or uf_data.get("name")
                or "صديق"
            )
            earned_val = round(float(uf_data.get("earned_from_him", 0.0) or 0.0), 6)

            # إذا زادت ترقيات الصديق في جدول users، نقوم بمزامنتها في جدول user_friends
            if real_upgrades_count != stored_upgrades:
                try:
                    sb.table("user_friends").update({
                        "upgrades_count": real_upgrades_count,
                        "first_name": real_name,
                        "name": real_name,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("referrer_id", ref_str).eq("friend_id", friend_id).execute()
                except Exception:
                    pass

            friends_list.append({
                "tg_id": friend_id,
                "name": real_name,
                "first_name": real_name,
                "generated": earned_val,
                "earned_from_him": earned_val,
                "upgrades_count": real_upgrades_count
            })

        return friends_list
    except Exception as e:
        print(f"❌ Error getting user friends for {tg_id}: {e}")
        return []


def add_referral_reward(referrer_id, user_id, mined_amount, user_upgrades_count=None, user_name=None):
    """إضافة أرباح التعدين للمُحيل وتحديث سجل الصديق تلقائياً في Supabase مع مراعاة نسبة VIP (12%)"""
    try:
        if not referrer_id or not user_id or float(mined_amount or 0) <= 0:
            return False

        ref_str = str(referrer_id).strip()
        user_str = str(user_id).strip()
        if ref_str == user_str:
            return False

        with _get_user_lock(ref_str):
            config = get_friends_config()
            sb = _get_supabase_client()

            referrer_data = _ensure_user_exists(ref_str)
            if is_user_vip(ref_str, referrer_data):
                comm_percent = float(config.get("vip_commission_percent", 12.0)) / 100.0
            else:
                comm_percent = float(config.get("commission_percent", 10.0)) / 100.0

            reward = round(float(mined_amount) * comm_percent, 6)
            if reward <= 0:
                return False

            # 1. تحديث الأرباح المعلقة والإجمالية للمُحيل
            cur_pending = float(referrer_data.get("pending_ref_earnings", 0.0) or 0.0)
            cur_total = float(referrer_data.get("total_ref_earnings", 0.0) or 0.0)

            _update_user_row(ref_str, {
                "pending_ref_earnings": round(cur_pending + reward, 6),
                "total_ref_earnings": round(cur_total + reward, 6)
            })

            # 2. تحديث سجل الصديق في جدول user_friends
            uf_res = (
                sb.table("user_friends")
                .select("*")
                .eq("referrer_id", ref_str)
                .eq("friend_id", user_str)
                .limit(1)
                .execute()
            )

            friend_row = _fetch_user_row(user_str) or {}
            resolved_name = (
                user_name
                or friend_row.get("first_name")
                or friend_row.get("name")
                or "صديق"
            )
            resolved_upgrades = (
                int(user_upgrades_count)
                if user_upgrades_count is not None
                else _calculate_user_upgrades(friend_row)
            )

            if uf_res.data and len(uf_res.data) > 0:
                existing_uf = uf_res.data[0]
                old_earned = float(existing_uf.get("earned_from_him", 0.0) or 0.0)
                old_upgrades = int(existing_uf.get("upgrades_count", 0) or 0)
                sb.table("user_friends").update({
                    "earned_from_him": round(old_earned + reward, 6),
                    "first_name": resolved_name,
                    "name": resolved_name,
                    "upgrades_count": max(old_upgrades, resolved_upgrades),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("referrer_id", ref_str).eq("friend_id", user_str).execute()
            else:
                sb.table("user_friends").upsert({
                    "referrer_id": ref_str,
                    "friend_id": user_str,
                    "first_name": resolved_name,
                    "name": resolved_name,
                    "earned_from_him": reward,
                    "upgrades_count": resolved_upgrades,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }, on_conflict="referrer_id,friend_id").execute()

            return True
    except Exception as e:
        print(f"❌ Error adding referral reward for {referrer_id}: {e}")
        return False


def get_friends_list_db(tg_id):
    """جلب قائمة الأصدقاء للاستخدام في API الأصدقاء"""
    return get_user_friends(tg_id)


def get_friends_data_db(tg_id, start_param=None, user_name=None):
    """جلب ملخص إحصائيات الأصدقاء والمكافآت وإعدادات قائمة الأصدقاء مع شرط 3 ترقيات"""
    try:
        tg_str = str(tg_id).strip()
        user_data = _ensure_user_exists(tg_str, user_name)

        # إذا دخل المستخدم عبر رابط دعوة (start_param = ref_XXXX) ولم يُربط بعد، يتم ربطه تلقائياً
        if start_param and isinstance(start_param, str) and start_param.startswith("ref_"):
            ref_candidate = start_param.replace("ref_", "", 1).strip()
            if ref_candidate and ref_candidate != tg_str and not user_data.get("referred_by"):
                register_referral_db(ref_candidate, tg_str, user_name or user_data.get("first_name") or "صديق")
                user_data = _fetch_user_row(tg_str) or user_data

        friends = get_user_friends(tg_str)

        config = get_friends_config().copy()
        vip_status = is_user_vip(tg_str, user_data)

        # شرط الترقيات ثابت 3 ترقيات للجميع كما هو مطلوب
        config["min_upgrades_for_task"] = 3
        min_upgrades = 3

        if vip_status:
            effective_commission = float(config.get("vip_commission_percent", 12.0))
            effective_claim_fee = float(config.get("vip_claim_fee_percent", 0.0))
        else:
            effective_commission = float(config.get("commission_percent", 10.0))
            effective_claim_fee = float(config.get("claim_fee_percent", 1.5))

        # حساب الأصدقاء المؤهلين للمهام الذين أتموا 3 ترقيات أو أكثر
        eligible_count = sum(1 for f in friends if int(f.get("upgrades_count", 0) or 0) >= min_upgrades)

        claimed_tasks = _parse_json_field(user_data.get("claimed_ref_tasks"), [])
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
            "is_vip": vip_status,
            "effective_commission": effective_commission,
            "effective_claim_fee": effective_claim_fee,
            "friends_config": config
        }
    except Exception as e:
        print(f"❌ Error getting friends data for {tg_id}: {e}")
        config = get_friends_config().copy()
        config["min_upgrades_for_task"] = 3
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
    """سحب أرباح الإحالات المعلقة وتحويلها للرصيد الرئيسي بأمان ضد التكرار والغش"""
    tg_str = str(tg_id).strip()
    if not tg_str:
        return {"success": False, "error": "معرف المستخدم غير صالح"}

    with _get_user_lock(tg_str):
        try:
            user_data = _fetch_user_row(tg_str)
            if not user_data:
                return {"success": False, "error": "المستخدم غير موجود"}

            pending = round(float(user_data.get("pending_ref_earnings", 0.0) or 0.0), 6)
            if pending <= 0:
                return {"success": False, "error": "لا توجد أرباح معلقة للسحب"}

            config = get_friends_config()
            vip_status = is_user_vip(tg_str, user_data)

            claim_fee_percent = (
                float(config.get("vip_claim_fee_percent", 0.0))
                if vip_status
                else float(config.get("claim_fee_percent", 1.5))
            )
            fee_rate = max(0.0, min(100.0, claim_fee_percent)) / 100.0

            fee_amount = round(pending * fee_rate, 6)
            net_amount = round(pending - fee_amount, 6)
            if net_amount <= 0:
                return {"success": False, "error": "المبلغ المعلق صغير جداً للسحب"}

            current_balance = round(float(user_data.get("balance", 0.0) or 0.0), 6)
            new_balance = round(current_balance + net_amount, 6)

            updated = _update_user_row(tg_str, {
                "balance": new_balance,
                "pending_ref_earnings": 0.0
            })
            if not updated:
                return {"success": False, "error": "تعذر تحديث الرصيد، يرجى المحاولة مرة أخرى"}

            fee_msg = "معفي من الرسوم (0% VIP)" if vip_status else f"خصم {fee_amount} ZN رسوم ({claim_fee_percent}%)"
            return {
                "success": True,
                "claimed_amount": pending,
                "fee_amount": fee_amount,
                "net_amount": net_amount,
                "new_balance": new_balance,
                "message": f"تم سحب {net_amount} ZN بنجاح إلى رصيدك ({fee_msg})"
            }
        except Exception as e:
            print(f"❌ Error claiming ref earnings for {tg_id}: {e}")
            return {"success": False, "error": "حدث خطأ أثناء تنفيذ عملية السحب"}


def claim_ref_task_db(tg_id, task_id, reward=0, req_friends=1):
    """
    استلام مكافأة مهمة دعوة الأصدقاء مع حماية مشددة ضد الغش:
    - يتم تجاهل reward و req_friends القادمة من المتصفح والاعتماد حصراً على إعدادات السيرفر.
    - يشترط إتمام الصديق 3 ترقيات على الأقل لاحتسابه في المهمة.
    """
    tg_str = str(tg_id).strip()
    task_key = str(task_id).strip()

    if not tg_str or not task_key:
        return {"success": False, "error": "بيانات المهمة غير صالحة"}

    with _get_user_lock(tg_str):
        try:
            user_data = _fetch_user_row(tg_str)
            if not user_data:
                return {"success": False, "error": "المستخدم غير موجود"}

            config = get_friends_config()
            ref_tasks = config.get("ref_tasks") or DEFAULT_FRIENDS_CONFIG["ref_tasks"]

            # حماية ضد التلاعب: يجب أن تكون المهمة موجودة فعلياً في جدول المهام بالسيرفر
            task_info = ref_tasks.get(task_key)
            if not isinstance(task_info, dict):
                return {"success": False, "error": "هذه المهمة غير موجودة أو غير صالحة"}

            actual_req_friends = int(task_info.get("reqFriends", 1))
            actual_reward = round(float(task_info.get("reward", 0.0)), 6)

            if actual_reward <= 0 or actual_req_friends <= 0:
                return {"success": False, "error": "إعدادات المهمة غير صالحة"}

            # التحقق من عدم استلام المكافأة مسبقاً
            claimed_tasks = _parse_json_field(user_data.get("claimed_ref_tasks"), [])
            if not isinstance(claimed_tasks, list):
                claimed_tasks = []
            claimed_str_list = [str(t) for t in claimed_tasks]

            if task_key in claimed_str_list:
                return {"success": False, "error": "تم استلام مكافأة هذه المهمة من قبل"}

            # شرط التأهيل الثابت: 3 ترقيات على الأقل لكل صديق
            min_upgrades = 3
            friends = get_user_friends(tg_str)
            eligible_count = sum(1 for f in friends if int(f.get("upgrades_count", 0) or 0) >= min_upgrades)

            if eligible_count < actual_req_friends:
                return {
                    "success": False,
                    "error": f"تحتاج إلى {actual_req_friends} أصدقاء مؤهلين (+{min_upgrades} ترقيات لكل صديق) لاستلام هذه المكافأة"
                }

            current_balance = round(float(user_data.get("balance", 0.0) or 0.0), 6)
            new_balance = round(current_balance + actual_reward, 6)
            claimed_str_list.append(task_key)

            updated = _update_user_row(tg_str, {
                "balance": new_balance,
                "claimed_ref_tasks": claimed_str_list
            })
            if not updated:
                return {"success": False, "error": "فشل حفظ المكافأة، حاول مرة أخرى"}

            return {
                "success": True,
                "new_balance": new_balance,
                "claimed_ref_tasks": claimed_str_list,
                "message": f"تم استلام مكافأة {actual_reward} ZN بنجاح"
            }
        except Exception as e:
            print(f"❌ Error claiming ref task for {tg_id}: {e}")
            return {"success": False, "error": "حدث خطأ أثناء استلام مكافأة المهمة"}

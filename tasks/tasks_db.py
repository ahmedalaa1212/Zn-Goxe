# -*- coding: utf-8 -*-
"""
tasks/tasks_db.py - المحرك الأمني الكامل لإدارة المهام والحملات الإعلانية عبر Supabase (PostgreSQL)
مزود بحماية ضد تخطي الوقت (Timer Bypass)، ومنع تكرار الصرف (Row-Level Locking FOR UPDATE)،
والإنشاء التلقائي للجداول والإعدادات الديناميكية ⚡
"""
import uuid
import math
import datetime
import urllib.parse
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from database import (
    get_db_connection,
    get_db_transaction,
    format_iso,
    _sanitize_id
)

# ==================== الثوابت والإعدادات الافتراضية ====================
DEFAULT_TASKS_CONFIG = {
    "min_reward_website": 15.0,
    "min_reward_default": 10.0,
    "min_reward_youtube": 10.0,
    "min_reward_telegram": 10.0,
    "min_reward_instagram": 10.0,
    "min_reward_x": 10.0,
    "wait_seconds": 15,
    "conversion_fee_percent": 10.0,
    "review_seconds": 3,
    "cache_ttl_seconds": 0
}

# قائمة الكلمات المحظورة لحماية المنصة والمستخدمين
FORBIDDEN_KEYWORDS = [
    'porn', 'sexy', 'xnx', 'adult', 'gambling', 'casino', 'bet365', '1xbet',
    'sex', 'إباحي', 'جنس', 'قمار', 'hack', 'scam', 'phishing', 'exploit', 'malware',
    'javascript:', 'data:', 'vbscript:'
]

_tasks_schema_verified = False


# ==================== 0. التهيئة التلقائية للجداول والإعدادات ====================

def ensure_tasks_tables_and_settings():
    """
    فحص وإنشاء جداول المهام وأعمدة الأرصدة والإعدادات الافتراضية تلقائياً في Supabase
    لضمان عدم حدوث أي خطأ حتى لو تم تشغيل ملف المهام بشكل مستقل.
    """
    global _tasks_schema_verified
    if _tasks_schema_verified:
        return

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS ad_balance DOUBLE PRECISION DEFAULT 0.0;

                    CREATE TABLE IF NOT EXISTS settings (
                        key VARCHAR(128) PRIMARY KEY,
                        value JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS campaigns (
                        id VARCHAR(128) PRIMARY KEY,
                        creator_id VARCHAR(128) NOT NULL,
                        platform VARCHAR(64) NOT NULL,
                        url TEXT NOT NULL,
                        description TEXT NOT NULL,
                        reward DOUBLE PRECISION NOT NULL DEFAULT 10.0 CHECK (reward > 0),
                        users_needed INT NOT NULL DEFAULT 1 CHECK (users_needed >= 1),
                        users_completed INT NOT NULL DEFAULT 0 CHECK (users_completed >= 0),
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_campaigns_creator ON campaigns(creator_id);
                    CREATE INDEX IF NOT EXISTS idx_campaigns_active ON campaigns(users_completed, users_needed);

                    CREATE TABLE IF NOT EXISTS completed_tasks (
                        id BIGSERIAL PRIMARY KEY,
                        tg_id VARCHAR(128) NOT NULL,
                        task_id VARCHAR(128) NOT NULL,
                        platform VARCHAR(64) DEFAULT '',
                        completion_scope VARCHAR(32) NOT NULL DEFAULT 'ONCE',
                        completed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_user_task_scope UNIQUE (tg_id, task_id, completion_scope)
                    );

                    CREATE INDEX IF NOT EXISTS idx_completed_tasks_user ON completed_tasks(tg_id);
                    CREATE INDEX IF NOT EXISTS idx_completed_tasks_lookup ON completed_tasks(tg_id, task_id, completion_scope);

                    CREATE TABLE IF NOT EXISTS task_sessions (
                        tg_id VARCHAR(128) NOT NULL,
                        task_id VARCHAR(128) NOT NULL,
                        started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (tg_id, task_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_task_sessions_started ON task_sessions(started_at);
                """)
        _tasks_schema_verified = True
    except Exception as e:
        print(f"⚠️ [TASKS DB INIT] تنبيه أثناء التحقق من جداول المهام: {e}")


def _validate_positive_float(val, field_name="المبلغ", max_val=1e9) -> float:
    """فحص أمني صارم للأرقام العشرية لمنع ثغرات NaN و Infinity والأرقام السالبة"""
    try:
        num = float(val)
    except (ValueError, TypeError):
        raise ValueError(f"قيمة {field_name} غير صحيحة")

    if not math.isfinite(num) or num <= 0 or num > max_val:
        raise ValueError(f"قيمة {field_name} غير صالحة أو خارج النطاق المسموح")

    return round(num, 4)


def _get_completion_scope(platform: str, now_utc: datetime.datetime = None) -> str:
    """
    تحديد نطاق إكمال المهمة:
    - لمهام المواقع ('موقع' / 'website'): يكون النطاق هو تاريخ اليوم بـ UTC (YYYY-MM-DD) لتُفتح يومياً.
    - لباقي المنصات: يكون النطاق 'ONCE' لتُنفذ مرة واحدة فقط لكل مستخدم.
    """
    platform_clean = str(platform or '').strip().lower()
    if platform_clean in ['موقع', 'website']:
        if now_utc is None:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
        return now_utc.strftime('%Y-%m-%d')
    return 'ONCE'


# ==================== 1. إدارة الإعدادات الديناميكية ====================

def get_tasks_config() -> dict:
    """
    جلب الإعدادات الديناميكية والحد الأدنى للمكافآت لكل منصة مباشرة من جدول settings في Supabase.
    يدعم القراءة والإنشاء التلقائي لمفتاح 'task' أو حقل 'task' داخل مفتاح 'settings' لضمان التوافق التام.
    """
    ensure_tasks_tables_and_settings()
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT key, value FROM settings
                    WHERE key IN ('task', 'settings', 'app_settings')
                """)
                rows = cur.fetchall()
                rows_map = {r['key']: (r['value'] if isinstance(r['value'], dict) else {}) for r in rows}

                task_map = {}
                should_update_db = False

                # فحص وجود الإعدادات في مفتاح 'task' المباشر أو داخل 'settings' -> 'task'
                if 'task' in rows_map and isinstance(rows_map['task'], dict) and rows_map['task']:
                    raw_val = rows_map['task']
                    task_map = raw_val.get('task') if isinstance(raw_val.get('task'), dict) else dict(raw_val)
                elif 'settings' in rows_map and isinstance(rows_map['settings'].get('task'), dict):
                    task_map = dict(rows_map['settings']['task'])
                    should_update_db = True
                elif 'app_settings' in rows_map and isinstance(rows_map['app_settings'].get('task'), dict):
                    task_map = dict(rows_map['app_settings']['task'])
                    should_update_db = True
                else:
                    task_map = DEFAULT_TASKS_CONFIG.copy()
                    should_update_db = True

                # استكمال أي مفاتيح ناقصة بالقيم الافتراضية تلقائياً
                for key, default_val in DEFAULT_TASKS_CONFIG.items():
                    if key not in task_map or task_map[key] is None:
                        task_map[key] = default_val
                        should_update_db = True

                if should_update_db:
                    cur.execute("""
                        INSERT INTO settings (key, value, updated_at)
                        VALUES ('task', %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (Json(task_map),))

                    # تحديث مفتاح settings العام أيضاً لضمان توافق لوحة التحكم إن كانت تقرأ منه
                    settings_doc = rows_map.get('settings', {})
                    if not isinstance(settings_doc, dict):
                        settings_doc = {}
                    settings_doc['task'] = task_map
                    cur.execute("""
                        INSERT INTO settings (key, value, updated_at)
                        VALUES ('settings', %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (Json(settings_doc),))

        config = {
            "min_reward_website": max(0.1, float(task_map.get('min_reward_website', DEFAULT_TASKS_CONFIG["min_reward_website"]))),
            "min_reward_default": max(0.1, float(task_map.get('min_reward_default', DEFAULT_TASKS_CONFIG["min_reward_default"]))),
            "min_reward_youtube": max(0.1, float(task_map.get('min_reward_youtube', DEFAULT_TASKS_CONFIG["min_reward_youtube"]))),
            "min_reward_telegram": max(0.1, float(task_map.get('min_reward_telegram', DEFAULT_TASKS_CONFIG["min_reward_telegram"]))),
            "min_reward_instagram": max(0.1, float(task_map.get('min_reward_instagram', DEFAULT_TASKS_CONFIG["min_reward_instagram"]))),
            "min_reward_x": max(0.1, float(task_map.get('min_reward_x', DEFAULT_TASKS_CONFIG["min_reward_x"]))),
            "wait_seconds": max(1, int(task_map.get('wait_seconds', DEFAULT_TASKS_CONFIG["wait_seconds"]))),
            "conversion_fee_percent": min(99.0, max(0.0, float(task_map.get('conversion_fee_percent', DEFAULT_TASKS_CONFIG["conversion_fee_percent"])))),
            "review_seconds": max(1, int(task_map.get('review_seconds', DEFAULT_TASKS_CONFIG["review_seconds"]))),
            "cache_ttl_seconds": 0
        }
        return config

    except Exception as e:
        print(f"[TASKS DB ERROR] Error fetching task settings from Supabase: {e}")
        return DEFAULT_TASKS_CONFIG.copy()


def get_tasks_config_from_db() -> dict:
    """دالة مرادفة للتوافق المباشر مع استدعاءات tasks_api.py"""
    return get_tasks_config()


def get_min_reward_for_platform(platform: str, config: dict = None) -> float:
    """تحديد الحد الأدنى لتكلفة المهمة الواحدة بناءً على المنصة والإعدادات الديناميكية المحدثة لحظياً"""
    if config is None:
        config = get_tasks_config()

    platform_clean = str(platform or '').strip().lower()

    if platform_clean in ['موقع', 'website']:
        return float(config.get('min_reward_website', 15.0))
    elif platform_clean in ['يوتيوب', 'youtube']:
        return float(config.get('min_reward_youtube', 10.0))
    elif platform_clean in ['تيليجرام', 'telegram']:
        return float(config.get('min_reward_telegram', 10.0))
    elif platform_clean in ['انستغرام', 'instagram']:
        return float(config.get('min_reward_instagram', 10.0))
    elif platform_clean in ['x', 'twitter', 'منصة x']:
        return float(config.get('min_reward_x', 10.0))
    else:
        return float(config.get('min_reward_default', 10.0))


# ==================== 2. التحقق من إكمال المهام ====================

def is_task_completed_by_user(task: dict, user_completed_data: dict) -> bool:
    """
    التحقق الآمن من إكمال المستخدم للمهمة،
    مع فتح مهام زيارة المواقع مجدداً عند دخول يوم جديد بتوقيت UTC (00:00 UTC).
    """
    task_id = str(task.get('id', '')).strip()
    platform = str(task.get('platform', '')).strip().lower()
    is_website_task = platform in ['موقع', 'website']

    if not user_completed_data or not task_id:
        return False

    today_utc_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')

    if isinstance(user_completed_data, (list, set)):
        if task_id not in user_completed_data:
            return False
        if is_website_task:
            return False
        return True

    if isinstance(user_completed_data, dict):
        if task_id not in user_completed_data:
            return False

        record = user_completed_data[task_id]

        if is_website_task:
            if isinstance(record, str):
                return record == today_utc_str
            elif isinstance(record, dict):
                scope = record.get('scope') or record.get('completion_scope')
                if scope and scope != 'ONCE':
                    return str(scope) == today_utc_str
                task_date = record.get('date')
                if task_date:
                    return str(task_date) == today_utc_str
                ts = record.get('timestamp')
                if ts:
                    task_dt = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).strftime('%Y-%m-%d')
                    return task_dt == today_utc_str
            elif isinstance(record, (int, float)):
                task_dt = datetime.datetime.fromtimestamp(float(record), datetime.timezone.utc).strftime('%Y-%m-%d')
                return task_dt == today_utc_str
            return False
        else:
            return True

    return False


def get_user_completed_tasks_map(telegram_id_str: str) -> dict:
    """
    جلب خريطة المهام التي أكملها المستخدم من جدول completed_tasks في Supabase.
    تُرجع المهام الدائمة (ONCE) ومهام المواقع المكتملة في اليوم الحالي بتوقيت UTC.
    """
    ensure_tasks_tables_and_settings()
    clean_id = _sanitize_id(telegram_id_str)
    if not clean_id:
        return {}

    today_utc_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    completed_map = {}

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT task_id, platform, completion_scope, completed_at
                    FROM completed_tasks
                    WHERE tg_id = %s
                      AND (completion_scope = 'ONCE' OR completion_scope = %s)
                """, (clean_id, today_utc_str))
                rows = cur.fetchall()
                for r in rows:
                    t_id = str(r['task_id']).strip()
                    comp_dt = r.get('completed_at')
                    if isinstance(comp_dt, datetime.datetime):
                        if comp_dt.tzinfo is None:
                            comp_dt = comp_dt.replace(tzinfo=datetime.timezone.utc)
                        else:
                            comp_dt = comp_dt.astimezone(datetime.timezone.utc)
                        date_str = comp_dt.strftime('%Y-%m-%d')
                        ts_val = comp_dt.timestamp()
                    else:
                        date_str = today_utc_str
                        ts_val = datetime.datetime.now(datetime.timezone.utc).timestamp()

                    scope_val = str(r.get('completion_scope') or 'ONCE')
                    completed_map[t_id] = {
                        "date": scope_val if scope_val != 'ONCE' else date_str,
                        "timestamp": ts_val,
                        "scope": scope_val
                    }
    except Exception as e:
        print(f"[TASKS DB ERROR] Error fetching completed_tasks for user {clean_id}: {e}")

    return completed_map


# ==================== 3. جلب الحملات النشطة ====================

def invalidate_campaigns_cache():
    """دالة للتوافق مع استدعاءات النظام الأخرى - النظام يعمل مباشرة بدون كاش"""
    pass


def get_cached_raw_campaigns(cache_ttl: int = 0) -> list:
    """جلب كافة الحملات الإعلانية مباشرة وبشكل حي من جدول campaigns في Supabase"""
    ensure_tasks_tables_and_settings()
    try:
        campaigns = []
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, creator_id, platform, url, description, reward,
                           users_needed, users_completed, created_at
                    FROM campaigns
                    ORDER BY reward DESC, created_at DESC
                """)
                rows = cur.fetchall()
                for r in rows:
                    campaigns.append({
                        "id": str(r['id']),
                        "creator_id": str(r['creator_id']),
                        "platform": str(r['platform']),
                        "url": str(r['url']),
                        "description": str(r['description']),
                        "reward": float(r['reward'] or 0.0),
                        "users_needed": int(r['users_needed'] or 1),
                        "users_completed": int(r['users_completed'] or 0),
                        "created_at": format_iso(r.get('created_at'))
                    })
        return campaigns
    except Exception as e:
        print(f"[TASKS DB ERROR] Error reading campaigns from Supabase: {e}")
        return []


def get_active_campaigns(telegram_id_str: str) -> list:
    """
    جلب وتصفية قائمة الحملات الإعلانية النشطة والمتاحة للمستخدم لحظياً من Supabase،
    مع التحقق من حالة الإكمال واستبعاد الحملات المنتهية (إلا إن كان المستخدم هو المنشئ).
    """
    clean_id = _sanitize_id(telegram_id_str) or str(telegram_id_str).strip()
    user_completed_data = get_user_completed_tasks_map(clean_id)
    raw_campaigns = get_cached_raw_campaigns()
    result_campaigns = []

    for c in raw_campaigns:
        creator_id_str = str(c.get('creator_id') or '').strip()
        users_completed = int(c.get('users_completed', 0))
        users_needed = int(c.get('users_needed', 1))

        # استبعاد الحملات التي اكتملت إلا لو كان المستخدم هو ناشر الحملة نفسه
        if users_completed >= users_needed and creator_id_str != clean_id:
            continue

        c_copy = dict(c)
        c_copy['is_completed'] = is_task_completed_by_user(c, user_completed_data)
        result_campaigns.append(c_copy)

    return result_campaigns


# ==================== 4. بدء وإكمال المهمة (مع حماية المؤقت والغش) ====================

def start_user_task(telegram_id_str: str, task_id: str) -> dict:
    """
    تسجيل لحظة بدء المستخدم للمهمة في جدول task_sessions داخل السيرفر.
    تمنع هذه الخطوة أي تلاعب أو تخطي لمؤقت الانتظار عبر أدوات المطور أو السكريبتات.
    """
    ensure_tasks_tables_and_settings()
    clean_id = _sanitize_id(telegram_id_str)
    task_id_str = str(task_id or '').strip()

    if not clean_id or not task_id_str:
        raise ValueError("بيانات المستخدم أو المهمة غير مكتملة")

    config = get_tasks_config()
    wait_seconds = int(config.get('wait_seconds', 15))
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, creator_id, platform, users_needed, users_completed
                FROM campaigns
                WHERE id = %s
                LIMIT 1
            """, (task_id_str,))
            camp = cur.fetchone()

            if not camp:
                raise ValueError("المهمة غير موجودة أو تم إلغاؤها")

            if str(camp['creator_id']).strip() == clean_id:
                raise ValueError("لا يمكنك تنفيذ حملتك الإعلانية الخاصة")

            if int(camp['users_completed'] or 0) >= int(camp['users_needed'] or 1):
                raise ValueError("هذه المهمة مكتملة بالكامل واستوفت عدد الأعضاء المطلوب")

            scope = _get_completion_scope(camp['platform'], now_utc)
            cur.execute("""
                SELECT 1 FROM completed_tasks
                WHERE tg_id = %s AND task_id = %s AND completion_scope = %s
                LIMIT 1
            """, (clean_id, task_id_str, scope))
            if cur.fetchone():
                if scope != 'ONCE':
                    raise ValueError("لقد قمت بزيارة هذا الموقع اليوم، يمكنك زيارته مجدداً غداً!")
                raise ValueError("لقد قمت بإكمال هذه المهمة مسبقاً")

            cur.execute("""
                INSERT INTO task_sessions (tg_id, task_id, started_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tg_id, task_id) DO UPDATE
                SET started_at = CURRENT_TIMESTAMP
                RETURNING started_at
            """, (clean_id, task_id_str))
            session_row = cur.fetchone()

    return {
        "task_id": task_id_str,
        "wait_seconds": wait_seconds,
        "started_at": format_iso(session_row['started_at']) if session_row else format_iso(now_utc)
    }


def complete_user_task(telegram_id_str: str, task_id: str, enforce_timer: bool = True) -> tuple:
    """
    إكمال المهمة بمعاملة ذرية مغلقة (PostgreSQL Transaction + FOR UPDATE):
    1. قفل صف الحملة والتحقق من وجودها وعدم اكتمال عدد منفذيها.
    2. التحقق من عدم قيام صاحب الإعلان بتنفيذ مهمته بنفسه.
    3. التحقق من جلسة البدء (task_sessions) وانقضاء مدة الانتظار الفعلية لمنع تخطي المؤقت.
    4. التحقق من عدم تكرار الإكمال في نفس اليوم للمواقع أو مطلقاً للمنصات الأخرى عبر قيد UNIQUE.
    5. زيادة رصيد المستخدم (balance) وتحديث عداد الحملة ذرياً.
    """
    ensure_tasks_tables_and_settings()
    clean_id = _sanitize_id(telegram_id_str)
    task_id_str = str(task_id or '').strip()

    if not clean_id or not task_id_str:
        raise ValueError("معرف المستخدم أو المهمة غير صالح")

    config = get_tasks_config()
    wait_seconds = max(1, int(config.get('wait_seconds', 15)))
    # السماح بهامش ثانيتين لتعويض فرق سرعة الشبكة بين الموبايل والسيرفر
    min_required_seconds = max(1, wait_seconds - 2)
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    with get_db_transaction() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. قفل صف الحملة الإعلانية لمنع تخطي العدد المطلوب عند الطلبات المتزامنة
            cur.execute("""
                SELECT id, creator_id, platform, reward, users_needed, users_completed
                FROM campaigns
                WHERE id = %s
                FOR UPDATE
            """, (task_id_str,))
            target_campaign = cur.fetchone()

            if not target_campaign:
                raise ValueError("المهمة غير موجودة أو انتهت")

            if str(target_campaign['creator_id']).strip() == clean_id:
                raise ValueError("لا يمكنك تنفيذ حملتك الإعلانية الخاصة")

            users_completed = int(target_campaign['users_completed'] or 0)
            users_needed = int(target_campaign['users_needed'] or 1)

            if users_completed >= users_needed:
                raise ValueError("هذه المهمة مكتملة بالكامل واستوفت عدد الأعضاء المطلوب!")

            platform_str = str(target_campaign['platform'] or '').strip()
            scope = _get_completion_scope(platform_str, now_utc)

            # 2. التحقق من عدم إكمال المهمة مسبقاً
            cur.execute("""
                SELECT 1 FROM completed_tasks
                WHERE tg_id = %s AND task_id = %s AND completion_scope = %s
                LIMIT 1
            """, (clean_id, task_id_str, scope))
            if cur.fetchone():
                if scope != 'ONCE':
                    raise ValueError("لقد قمت بزيارة هذا الموقع اليوم، يمكنك زيارته غداً مجدداً!")
                raise ValueError("لقد قمت بإكمال هذه المهمة مسبقاً")

            # 3. التحقق الأمني من جلسة بدء المهمة وانقضاء وقت الانتظار الفعلي
            if enforce_timer:
                cur.execute("""
                    SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at)) AS elapsed_seconds
                    FROM task_sessions
                    WHERE tg_id = %s AND task_id = %s
                    FOR UPDATE
                """, (clean_id, task_id_str))
                session_row = cur.fetchone()

                if not session_row:
                    raise ValueError("يرجى الضغط على زر (ابدأ) وزيارة الرابط أولاً قبل التحقق من المهمة!")

                elapsed = float(session_row['elapsed_seconds'] or 0.0)
                if elapsed < min_required_seconds:
                    remaining = max(1, int(math.ceil(wait_seconds - elapsed)))
                    raise ValueError(f"لم يكتمل وقت تنفيذ المهمة بعد! يرجى الانتظار {remaining} ثانية إضافية.")

            reward_amount = _validate_positive_float(target_campaign['reward'], "مكافأة المهمة")

            # 4. التأكد من وجود المستخدم وقفل صفه لتحديث الرصيد بأمان
            cur.execute("""
                SELECT tg_id, COALESCE(balance, 0.0) AS balance, COALESCE(is_banned, FALSE) AS is_banned
                FROM users
                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                LIMIT 1
                FOR UPDATE
            """, (clean_id, clean_id, clean_id))
            user_row = cur.fetchone()

            if not user_row:
                cur.execute("""
                    INSERT INTO users (tg_id, user_id, telegram_id, first_name, name, balance, ad_balance)
                    VALUES (%s, %s, %s, 'لاعب', 'لاعب', 0.0, 0.0)
                    ON CONFLICT (tg_id) DO NOTHING
                """, (clean_id, clean_id, clean_id))
                cur.execute("""
                    SELECT tg_id, COALESCE(balance, 0.0) AS balance, COALESCE(is_banned, FALSE) AS is_banned
                    FROM users
                    WHERE tg_id = %s
                    FOR UPDATE
                """, (clean_id,))
                user_row = cur.fetchone()

            if user_row and user_row.get('is_banned'):
                raise ValueError("عذراً، هذا الحساب محظور من تنفيذ المهام")

            target_tg_id = user_row['tg_id'] if user_row else clean_id

            # 5. تسجيل الإكمال ذرياً (قيد UNIQUE يمنع أي تكرار متزامن)
            try:
                cur.execute("""
                    INSERT INTO completed_tasks (tg_id, task_id, platform, completion_scope, completed_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (clean_id, task_id_str, platform_str, scope))
            except psycopg2.IntegrityError:
                if scope != 'ONCE':
                    raise ValueError("لقد قمت بزيارة هذا الموقع اليوم، يمكنك زيارته غداً مجدداً!")
                raise ValueError("لقد قمت بإكمال هذه المهمة مسبقاً")

            # مسح الجلسة المؤقتة بعد الاستخدام
            cur.execute("""
                DELETE FROM task_sessions
                WHERE tg_id = %s AND task_id = %s
            """, (clean_id, task_id_str))

            # 6. تحديث عدد المنفذين في الحملة وإضافة المكافأة لرصيد المستخدم
            cur.execute("""
                UPDATE campaigns
                SET users_completed = users_completed + 1
                WHERE id = %s
            """, (task_id_str,))

            cur.execute("""
                UPDATE users
                SET balance = ROUND((COALESCE(balance, 0.0) + %s)::numeric, 4)::double precision,
                    last_active_at = CURRENT_TIMESTAMP
                WHERE tg_id = %s
                RETURNING balance
            """, (reward_amount, target_tg_id))
            updated_user = cur.fetchone()
            new_balance = float(updated_user['balance'] if updated_user else reward_amount)

    invalidate_campaigns_cache()
    return reward_amount, new_balance


# ==================== 5. إنشاء وإلغاء الحملة الإعلانية ====================

def create_ad_campaign(
    telegram_id_str: str,
    platform: str,
    url: str,
    description: str,
    reward: float,
    users_needed: int
) -> tuple:
    """
    خصم تكلفة الحملة الكلية من رصيد الإعلانات (ad_balance) وإنشاء الحملة في Supabase بمعاملة ذرية مغلقة.
    """
    ensure_tasks_tables_and_settings()
    clean_id = _sanitize_id(telegram_id_str)
    if not clean_id:
        raise ValueError("معرف المستخدم غير صالح")

    platform_str = str(platform or '').strip()
    url_str = str(url or '').strip()
    desc_str = str(description or '').strip()

    if not all([platform_str, url_str, desc_str]):
        raise ValueError("جميع البيانات مطلوبة لإنشاء الحملة")

    if len(url_str) > 2048 or len(desc_str) > 500:
        raise ValueError("الرابط أو الوصف يتجاوز الطول المسموح به")

    # فحص صحة الرابط وبروتوكول الأمان
    parsed_url = urllib.parse.urlparse(url_str)
    if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
        raise ValueError("الرابط يجب أن يكون صحيحاً ويبدأ بـ http:// أو https://")

    url_lower = url_str.lower()
    if any(bad_word in url_lower for bad_word in FORBIDDEN_KEYWORDS):
        raise ValueError("الرابط يحتوي على محتوى مخالف للسياسات وحماية الحسابات")

    if platform_str == 'يوتيوب' and not ('youtube.com' in url_lower or 'youtu.be' in url_lower):
        raise ValueError("رابط يوتيوب غير صحيح")
    if platform_str == 'تيليجرام' and 't.me' not in url_lower:
        raise ValueError("رابط تيليجرام غير صحيح")
    if platform_str == 'انستغرام' and 'instagram.com' not in url_lower:
        raise ValueError("رابط انستغرام غير صحيح")
    if platform_str in ('X', 'x') and not ('x.com' in url_lower or 'twitter.com' in url_lower):
        raise ValueError("رابط منصة X غير صحيح")

    reward_val = _validate_positive_float(reward, "مكافأة المهمة", max_val=1000000.0)

    try:
        if isinstance(users_needed, float) and not users_needed.is_integer():
            raise ValueError()
        users_needed_val = int(users_needed)
        if users_needed_val < 1 or users_needed_val > 1000000:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("عدد الأعضاء المطلوب غير صحيح")

    config = get_tasks_config()
    min_reward = get_min_reward_for_platform(platform_str, config=config)
    min_val_str = f"{int(min_reward)}" if float(min_reward).is_integer() else f"{min_reward}"

    if reward_val < min_reward:
        raise ValueError(f"عذراً، الحد الأدنى لتكلفة المهمة الواحدة لمنصة ({platform_str}) هو {min_val_str} عملة AdZ.")

    total_cost = round(reward_val * users_needed_val, 4)
    if not math.isfinite(total_cost) or total_cost < min_reward:
        raise ValueError(f"عذراً، الحد الأدنى لتكلفة إنشاء أي حملة إعلانية هو {min_val_str} عملة AdZ.")

    with get_db_transaction() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # قفل صف المستخدم لمنع إنشاء حملات متزامنة بنفس الرصيد
            cur.execute("""
                SELECT tg_id, COALESCE(ad_balance, 0.0) AS ad_balance, COALESCE(is_banned, FALSE) AS is_banned
                FROM users
                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                LIMIT 1
                FOR UPDATE
            """, (clean_id, clean_id, clean_id))
            user_row = cur.fetchone()

            if not user_row:
                raise ValueError("المستخدم غير موجود في قاعدة البيانات")

            if user_row.get('is_banned'):
                raise ValueError("عذراً، هذا الحساب محظور")

            current_ad_balance = float(user_row['ad_balance'] or 0.0)
            if current_ad_balance < total_cost:
                raise ValueError(f"رصيدك الإعلاني غير كافٍ. المطلوب: {total_cost} AdZ")

            target_tg_id = user_row['tg_id']
            camp_id = f"camp_{uuid.uuid4().hex[:12]}"

            cur.execute("""
                UPDATE users
                SET ad_balance = ROUND((COALESCE(ad_balance, 0.0) - %s)::numeric, 4)::double precision,
                    last_active_at = CURRENT_TIMESTAMP
                WHERE tg_id = %s
                RETURNING ad_balance
            """, (total_cost, target_tg_id))
            updated_user = cur.fetchone()
            new_ad_balance = float(updated_user['ad_balance'] or 0.0)

            cur.execute("""
                INSERT INTO campaigns (
                    id, creator_id, platform, url, description,
                    reward, users_needed, users_completed, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 0, CURRENT_TIMESTAMP)
                RETURNING id, creator_id, platform, url, description,
                          reward, users_needed, users_completed, created_at
            """, (camp_id, clean_id, platform_str, url_str, desc_str, reward_val, users_needed_val))
            camp_row = cur.fetchone()

            new_campaign = {
                "id": str(camp_row['id']),
                "creator_id": str(camp_row['creator_id']),
                "platform": str(camp_row['platform']),
                "url": str(camp_row['url']),
                "description": str(camp_row['description']),
                "reward": float(camp_row['reward']),
                "users_needed": int(camp_row['users_needed']),
                "users_completed": int(camp_row['users_completed']),
                "created_at": format_iso(camp_row['created_at'])
            }

    invalidate_campaigns_cache()
    return new_campaign, new_ad_balance


def cancel_ad_campaign(telegram_id_str: str, campaign_id: str) -> tuple:
    """
    إلغاء الحملة وإعادة المبلغ المتبقي للأعضاء غير المنفذين إلى رصيد الإعلانات ad_balance
    داخل معاملة ذرية مغلقة تمنع الاسترداد المزدوج (Double Refund).
    """
    ensure_tasks_tables_and_settings()
    clean_id = _sanitize_id(telegram_id_str)
    campaign_id_str = str(campaign_id or '').strip()

    if not clean_id or not campaign_id_str:
        raise ValueError("معرف الحملة أو المستخدم مفقود")

    with get_db_transaction() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # قفل صف الحملة فوراً لمنع إلغائها مرتين في نفس اللحظة
            cur.execute("""
                SELECT id, creator_id, reward, users_needed, users_completed
                FROM campaigns
                WHERE id = %s
                FOR UPDATE
            """, (campaign_id_str,))
            target_campaign = cur.fetchone()

            if not target_campaign:
                raise ValueError("الحملة غير موجودة أو تم إلغاؤها مسبقاً")

            if str(target_campaign['creator_id']).strip() != clean_id:
                raise ValueError("غير مصرح لك بإلغاء هذه الحملة")

            comp = int(target_campaign['users_completed'] or 0)
            need = int(target_campaign['users_needed'] or 1)
            cost_per_user = float(target_campaign['reward'] or 0.0)

            remaining_slots = max(0, need - comp)
            refund_amount = round(max(0.0, float(remaining_slots * cost_per_user)), 4)

            # قفل صف المستخدم لتحديث رصيد الإعلانات بأمان
            cur.execute("""
                SELECT tg_id, COALESCE(ad_balance, 0.0) AS ad_balance
                FROM users
                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                LIMIT 1
                FOR UPDATE
            """, (clean_id, clean_id, clean_id))
            user_row = cur.fetchone()

            if not user_row:
                raise ValueError("المستخدم غير موجود")

            target_tg_id = user_row['tg_id']

            # حذف الحملة وجلساتها المؤقتة
            cur.execute("DELETE FROM task_sessions WHERE task_id = %s", (campaign_id_str,))
            cur.execute("DELETE FROM campaigns WHERE id = %s", (campaign_id_str,))

            # إرجاع المتبقي إلى رصيد الإعلانات
            cur.execute("""
                UPDATE users
                SET ad_balance = ROUND((COALESCE(ad_balance, 0.0) + %s)::numeric, 4)::double precision,
                    last_active_at = CURRENT_TIMESTAMP
                WHERE tg_id = %s
                RETURNING ad_balance
            """, (refund_amount, target_tg_id))
            updated_user = cur.fetchone()
            new_ad_balance = float(updated_user['ad_balance'] or 0.0)

    invalidate_campaigns_cache()
    return refund_amount, new_ad_balance


# ==================== 6. تحويل الرصيد (ZN -> AdZ) ====================

def convert_balance_to_ad_balance(telegram_id_str: str, amount: float) -> tuple:
    """
    تحويل الرصيد الأساسي (ZN) إلى رصيد الإعلانات (AdZ) بعد خصم العمولة الديناميكية اللحظية
    باستخدام قفل الصفوف الذري (FOR UPDATE) لمنع التكرار أو الرصيد السالب.
    """
    ensure_tasks_tables_and_settings()
    clean_id = _sanitize_id(telegram_id_str)
    if not clean_id:
        raise ValueError("معرف المستخدم غير صالح")

    amount_val = _validate_positive_float(amount, "المبلغ المراد تحويله", max_val=1e9)

    config = get_tasks_config()
    fee_percent = min(99.0, max(0.0, float(config.get('conversion_fee_percent', 10.0))))

    with get_db_transaction() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # قفل صف المستخدم طوال عملية التحويل
            cur.execute("""
                SELECT tg_id,
                       COALESCE(balance, 0.0) AS balance,
                       COALESCE(ad_balance, 0.0) AS ad_balance,
                       COALESCE(is_banned, FALSE) AS is_banned
                FROM users
                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                LIMIT 1
                FOR UPDATE
            """, (clean_id, clean_id, clean_id))
            user_row = cur.fetchone()

            if not user_row:
                raise ValueError("المستخدم غير موجود")

            if user_row.get('is_banned'):
                raise ValueError("عذراً، هذا الحساب محظور")

            current_balance = float(user_row['balance'] or 0.0)
            if current_balance < amount_val:
                raise ValueError("رصيد ZN الحالي غير كافٍ لهذا التحويل")

            fee = round(amount_val * (fee_percent / 100.0), 4)
            received = round(max(0.0, amount_val - fee), 4)
            target_tg_id = user_row['tg_id']

            cur.execute("""
                UPDATE users
                SET balance = GREATEST(0.0, ROUND((COALESCE(balance, 0.0) - %s)::numeric, 4)::double precision),
                    ad_balance = ROUND((COALESCE(ad_balance, 0.0) + %s)::numeric, 4)::double precision,
                    last_active_at = CURRENT_TIMESTAMP
                WHERE tg_id = %s
                RETURNING balance, ad_balance
            """, (amount_val, received, target_tg_id))
            updated_row = cur.fetchone()

            new_balance = float(updated_row['balance'] or 0.0)
            new_ad_balance = float(updated_row['ad_balance'] or 0.0)

    return received, fee, fee_percent, new_balance, new_ad_balance


# تهيئة الجداول تلقائياً عند استيراد الملف
try:
    ensure_tasks_tables_and_settings()
except Exception as _init_err:
    print(f"⚠️ [TASKS DB] تنبيه التهيئة الأولية: {_init_err}")

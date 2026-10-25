import os
import json
import time
import traceback
from datetime import datetime, timezone
from threading import Lock
from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
import database

# استيراد دالّات قاعدة البيانات الأساسية للمزرعة
from farm.farm_db import (
    get_or_create_user_farm_data,
    claim_mined_tokens_db,
    buy_upgrade_db,
    buy_storage_db,
    claim_daily_reward_db,
    claim_daily_boost_db,
    dismiss_welcome_db,
    get_mining_leaderboard_db,
    parse_daily_rewards,
    calculate_user_max_cap,
    get_game_settings,
    DEFAULT_GAME_SETTINGS
)

# استيراد دوال نظام الأصدقاء الموحد (Supabase)
from friends.friends_db import (
    register_referral_db,
    sync_friend_upgrades_db,
    get_friends_data_db,
    get_user_friends as get_user_friends_list_db,
    claim_ref_earnings_db
)

farm_bp = Blueprint('farm', __name__)

# ==========================================
# 🚀 إضافة خوارزمية منع الكاش للتحديث اللحظي (القاعدة 7)
# ==========================================
@farm_bp.after_request
def add_cache_control_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# المستويات المتاحة للترقية هي 1 إلى 8 فقط
VALID_UPGRADE_LEVELS = {str(i) for i in range(1, 9)}

AD_KEYS = (
    "ad_watched", "ad_completed", "monetag_watched", "monetag_completed", 
    "monetix_watched", "monetix_completed", "watched", "reward"
)

# ==========================================
# 🛡️ نظام الحماية المتقدم ضد السبام والطلبات المتزامنة (Anti-Spam & Anti-Race Condition)
# ==========================================
_rate_limit_lock = Lock()
_user_last_request = {}
_active_user_mutations = set()


def is_rate_limited(user_id: str, endpoint: str, min_interval: float = 1.0, is_mutation: bool = False) -> bool:
    now_ts = time.time()
    key = f"{user_id}:{endpoint}"
    mutation_key = f"{user_id}:__mutation__"

    with _rate_limit_lock:
        # منع تنفيذ عمليتين ماليتين (مثل claim + upgrade) في نفس اللحظة لنفس المستخدم
        if is_mutation:
            last_mut_ts = _user_last_request.get(mutation_key, 0)
            if now_ts - last_mut_ts < 1.2:
                return True
            _user_last_request[mutation_key] = now_ts

        last_ts = _user_last_request.get(key, 0)
        if now_ts - last_ts < min_interval:
            return True
        _user_last_request[key] = now_ts

        if len(_user_last_request) > 10000:
            expired_keys = [k for k, v in _user_last_request.items() if now_ts - v > 300]
            for k in expired_keys:
                del _user_last_request[k]

        return False


def acquire_user_mutation_lock(user_id: str) -> bool:
    """قفل ذري لمنع تداخل الطلبات المتزامنة (Race Conditions) لنفس المستخدم"""
    with _rate_limit_lock:
        if user_id in _active_user_mutations:
            return False
        _active_user_mutations.add(user_id)
        return True


def release_user_mutation_lock(user_id: str):
    with _rate_limit_lock:
        _active_user_mutations.discard(user_id)


# ==========================================
# 🛠️ الدوال المساعدة (Helper Utilities)
# ==========================================
def to_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "success", "ok")
    if isinstance(val, (int, float)):
        return val != 0
    return False


def parse_vip_status(raw_vip) -> dict:
    """فك تشفير بيانات باقة VIP بأمان سواء كانت dict أو نص JSON"""
    if not raw_vip:
        return {}
    if isinstance(raw_vip, dict):
        return raw_vip
    if isinstance(raw_vip, str):
        try:
            parsed = json.loads(raw_vip)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def get_expiration_dt(raw_val):
    if not raw_val:
        return None
    try:
        if isinstance(raw_val, (int, float)):
            ts = raw_val / 1000.0 if raw_val > 10000000000 else raw_val
            if ts < 0 or ts > 4102444800:
                return None
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(raw_val, datetime):
            return raw_val.replace(tzinfo=timezone.utc) if raw_val.tzinfo is None else raw_val.astimezone(timezone.utc)
        s = str(raw_val).strip().replace(' ', 'T')
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception as e:
        print(f"⚠️ Error parsing expiration date in API: {e}")
        return None


def format_iso_utc(dt: datetime = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    s = dt.isoformat()
    if s.endswith('+00:00'):
        return s[:-6] + 'Z'
    if not s.endswith('Z') and '+' not in s[10:] and '-' not in s[10:]:
        return s + 'Z'
    return s


def is_ad_watched(data: dict) -> bool:
    """إغلاق ثغرة تخطي الإعلان عبر التحقق الصارم من مفاتيح المشاهدة"""
    if not data or not isinstance(data, dict):
        return False
    return any(to_bool(data.get(key)) for key in AD_KEYS)


def calculate_user_effective_stats(user_data: dict, game_settings: dict, now: datetime) -> dict:
    """حساب موحد ودقيق لسعة المخزن وحالة الباقات (ضعف السعة ×2 وبوت التجميع)"""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    if not game_settings:
        game_settings = get_game_settings()

    vip_status = parse_vip_status(user_data.get("vip_status"))
    user_data["vip_status"] = vip_status

    expires_at_raw = (
        vip_status.get("expires_at")
        or vip_status.get("vip_expires_at")
        or vip_status.get("bot_expires_at")
        or user_data.get("bot_expires_at")
        or user_data.get("vip_expires_at")
        or user_data.get("expires_at")
    )

    exp_dt = get_expiration_dt(expires_at_raw)
    is_expired = (exp_dt is not None and exp_dt <= now)

    is_double_storage_active = False
    is_auto_bot_active = False

    if not is_expired:
        if to_bool(vip_status.get("double_storage", False)) or to_bool(user_data.get("is_double_storage_active", False)):
            is_double_storage_active = True

        if (
            to_bool(vip_status.get("auto_bot", False))
            or to_bool(user_data.get("bot_active", False))
            or to_bool(user_data.get("has_bot", False))
            or to_bool(user_data.get("is_auto_bot_active", False))
        ):
            is_auto_bot_active = True

    # الاعتماد على الدالة الموحدة في farm_db لحساب السعة الفعلية
    effective_max_cap = calculate_user_max_cap(user_data, game_settings, now)

    user_data["max_cap"] = round(float(effective_max_cap), 4)
    user_data["is_double_storage_active"] = is_double_storage_active
    user_data["vip_storage_multiplier"] = 2 if is_double_storage_active else 1
    user_data["is_auto_bot_active"] = is_auto_bot_active
    user_data["bot_active"] = is_auto_bot_active

    return user_data


# ==========================================
# 📍 المسارات النقاط البرمجية (API Routes)
# ==========================================

@farm_bp.route('/player_data', methods=['GET', 'POST'])
@farm_bp.route('/farm/player_data', methods=['GET', 'POST'])
@farm_bp.route('/api/farm/player_data', methods=['GET', 'POST'])
def get_player_data():
    """جلب كافة بيانات اللاعب وإعدادات المزرعة الديناميكية مع تنفيذ تجميع الأوفلاين وربط الإحالة"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
    
    user_id_str = str(telegram_id)

    if is_rate_limited(user_id_str, "player_data", min_interval=0.4):
        return jsonify({"success": False, "error": "يرجى الانتظار بين الطلبات"}), 429

    try:
        body = request.get_json(silent=True) or {}
        start_param = body.get("start_param") or request.args.get("start_param")
        if start_param and str(start_param).startswith("ref_"):
            u_name = (user_info.get("first_name") if isinstance(user_info, dict) else None) or "صديق"
            register_referral_db(str(start_param), user_id_str, friend_name=u_name)

        user_data, game_settings, now = get_or_create_user_farm_data(user_id_str)
        user_data = calculate_user_effective_stats(user_data, game_settings, now)

        # مزامنة ترقيات اللاعب الحالية مع جدول الأصدقاء
        sync_friend_upgrades_db(user_id_str)

        auto_claimed_amount = float(user_data.get("auto_claimed_amount", 0.0))
        auto_claimed = auto_claimed_amount > 0
        welcome_seen = to_bool(user_data.get("welcome_seen", False))

        user_data["auto_claimed"] = auto_claimed
        user_data["auto_claimed_amount"] = round(auto_claimed_amount, 8)
        user_data["welcome_seen"] = welcome_seen
        user_data["is_new_user"] = not welcome_seen

        parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))
        upgrade_configs = game_settings.get("upgrade_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
        
        upgrade_costs = {
            int(k): {
                "cost_zn": float(v.get("cost_zn", v.get("base_cost", v.get("price", 0)))),
                "cost_usd": float(v.get("cost_usd", v.get("base_cost_usd", 0.0))),
                "rate": float(v.get("rate_bonus", v.get("rate", 0)))
            }
            for k, v in upgrade_configs.items()
            if str(k).isdigit()
        }
        
        raw_storage_configs = (
            game_settings.get("storage_config")
            or game_settings.get("storage_capacities")
            or DEFAULT_GAME_SETTINGS.get("storage_config", {})
        )
        storage_configs = {}
        for k, v in raw_storage_configs.items():
            if isinstance(v, dict):
                storage_configs[str(k)] = {
                    "capacity": float(v.get("capacity", v.get("cap", 0.5))),
                    "cost_zn": float(v.get("cost_zn", v.get("cost", v.get("price", 0.0)))),
                    "cost_usd": float(v.get("cost_usd", v.get("usd_cost", 0.0)))
                }
            else:
                default_lvl = DEFAULT_GAME_SETTINGS["storage_config"].get(str(k), {})
                storage_configs[str(k)] = {
                    "capacity": float(v or default_lvl.get("capacity", 0.5)),
                    "cost_zn": float(default_lvl.get("cost_zn", 0.0)),
                    "cost_usd": float(default_lvl.get("cost_usd", 0.0))
                }

        mining_cfg = game_settings.get("mining_config", {})

        monetag_id = (os.environ.get("MONETAG_ZONE_ID") or os.environ.get("MONETAG_ID") or "11322720").strip()
        monetix_id = (os.environ.get("MONETIX_BLOCK_ID") or os.environ.get("MONETIX_ZONE_ID") or os.environ.get("MONETIX_ID") or "MX-3AE08FE9").strip()

        return jsonify({
            "success": True, 
            "player": user_data, 
            "server_time": format_iso_utc(now),
            "cooldown_seconds": int(mining_cfg.get("claim_cooldown_seconds", 15)),
            "auto_claimed": auto_claimed,
            "auto_claimed_amount": round(auto_claimed_amount, 8),
            "bot_active": bool(user_data.get("bot_active", False)),
            "is_auto_bot_active": bool(user_data.get("is_auto_bot_active", False)),
            "is_double_storage_active": bool(user_data.get("is_double_storage_active", False)),
            "max_cap": float(user_data.get("max_cap", 0.5)),
            "monetag_zone_id": monetag_id,
            "monetix_block_id": monetix_id,
            "game_config": {
                "daily_rewards": parsed_rewards,
                "upgrade_costs": upgrade_costs,
                "storage_config": storage_configs,
                "daily_boost_reward": float(mining_cfg.get("daily_boost_reward", 0.10)),
                "max_daily_boost_rate": float(mining_cfg.get("max_daily_boost_rate", 4.5)),
                "boost_max_reward_coins": float(mining_cfg.get("boost_max_reward_coins", 35.0)),
                "max_upgrades_per_level": int(mining_cfg.get("max_upgrades_per_level", 15)),
                "boost_cooldown_seconds": 10800,
                "boost_duration_seconds": 7200,
                "monetag_zone_id": monetag_id,
                "monetix_block_id": monetix_id,
                "monetix_zone_id": monetix_id
            }
        }), 200
    except Exception as e:
        print(f"Error player_data: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500


@farm_bp.route('/cron_auto_claim', methods=['GET', 'POST'])
@farm_bp.route('/farm/cron_auto_claim', methods=['GET', 'POST'])
@farm_bp.route('/api/farm/cron_auto_claim', methods=['GET', 'POST'])
def cron_auto_claim():
    """وظيفة خلفية (Cron Job) لتفقد جميع المشتركين في بوت التجميع التلقائي عبر Supabase"""
    cron_secret = os.environ.get("CRON_SECRET", "").strip()
    provided_secret = (request.headers.get("X-Cron-Secret") or request.args.get("secret") or "").strip()
    
    if not cron_secret or provided_secret != cron_secret:
        return jsonify({"success": False, "error": "غير مصرح بالوصول - مفتاح الحماية غير متطابق أو غير مفعل"}), 403

    try:
        user_ids = []
        with database.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tg_id FROM users
                    WHERE COALESCE(bot_active, FALSE) = TRUE
                       OR (vip_status IS NOT NULL AND vip_status::text LIKE '%"auto_bot": true%')
                       OR (vip_status IS NOT NULL AND vip_status::text LIKE '%"auto_bot":true%');
                """)
                user_ids = [str(r[0]) for r in (cur.fetchall() or []) if r and r[0]]
        
        processed_count = 0
        auto_claimed_count = 0
        total_claimed_amount = 0.0

        for user_id in user_ids:
            processed_count += 1
            try:
                user_data, _, _ = get_or_create_user_farm_data(user_id)
                claimed_amt = float(user_data.get("auto_claimed_amount", 0.0))
                if claimed_amt > 0:
                    auto_claimed_count += 1
                    total_claimed_amount += claimed_amt
            except Exception as user_e:
                print(f"⚠️ Error processing auto-claim cron for user {user_id}: {user_e}")

        return jsonify({
            "success": True,
            "processed_users": processed_count,
            "auto_claimed_users": auto_claimed_count,
            "total_claimed_amount": round(total_claimed_amount, 8),
            "timestamp": format_iso_utc()
        }), 200
    except Exception as e:
        print(f"Error cron_auto_claim: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "خطأ أثناء تنفيذ المهمة الخلفية"}), 500


@farm_bp.route('/dismiss_welcome', methods=['POST'])
@farm_bp.route('/farm/dismiss_welcome', methods=['POST'])
@farm_bp.route('/api/farm/dismiss_welcome', methods=['POST'])
def dismiss_welcome():
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    if is_rate_limited(user_id_str, "dismiss_welcome", min_interval=1.0):
        return jsonify({"success": False, "error": "يرجى الانتظار قبل إعادة المحاولة"}), 429

    try:
        result = dismiss_welcome_db(user_id_str)
        return jsonify(result), 200
    except Exception as e:
        print(f"Error dismiss_welcome: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "خطأ في تسجيل حالة الترحيب"}), 500


@farm_bp.route('/claim', methods=['POST'])
@farm_bp.route('/farm/claim', methods=['POST'])
@farm_bp.route('/api/farm/claim', methods=['POST'])
def claim_mined_tokens():
    """تجميع المحصول المعدن بأمان تام"""
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)

    if is_rate_limited(user_id_str, "claim", min_interval=2.0, is_mutation=True):
        return jsonify({"success": False, "error": "تم استلام طلب التجميع بالفعل، يرجى الانتظار لحين اكتمال المعالجة"}), 429

    if not acquire_user_mutation_lock(user_id_str):
        return jsonify({"success": False, "error": "جاري تنفيذ عملية أخرى لحسابك، يرجى الانتظار"}), 429

    try:
        result = claim_mined_tokens_db(user_id_str)
        return jsonify(result), (200 if result.get("success") else 400)
    except Exception as e:
        print(f"Error claim: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء التجميع"}), 500
    finally:
        release_user_mutation_lock(user_id_str)


@farm_bp.route('/upgrade', methods=['POST'])
@farm_bp.route('/farm/upgrade', methods=['POST'])
@farm_bp.route('/api/farm/upgrade', methods=['POST'])
def buy_upgrade():
    """شراء ترقية سرعة التعدين ومزامنة عداد ترقيات الصديق فوراً"""
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)

    if is_rate_limited(user_id_str, "upgrade", min_interval=1.5, is_mutation=True):
        return jsonify({"success": False, "error": "جاري معالجة طلب الترقية، يرجى الانتظار"}), 429

    data = request.get_json(silent=True) or {}
    raw_level = data.get("level")
    level = str(raw_level).strip() if raw_level is not None else ""
    
    if not level or level not in VALID_UPGRADE_LEVELS:
        return jsonify({"success": False, "error": "مستوى غير صحيح"}), 400

    if not acquire_user_mutation_lock(user_id_str):
        return jsonify({"success": False, "error": "جاري تنفيذ عملية أخرى لحسابك، يرجى الانتظار"}), 429
        
    try:
        result = buy_upgrade_db(user_id_str, level)
        if result.get("success"):
            sync_friend_upgrades_db(user_id_str)
        return jsonify(result), (200 if result.get("success") else 400)
    except Exception as e:
        print(f"Error upgrade: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية الشراء"}), 500
    finally:
        release_user_mutation_lock(user_id_str)


@farm_bp.route('/upgrade_storage', methods=['POST'])
@farm_bp.route('/farm/upgrade_storage', methods=['POST'])
@farm_bp.route('/api/farm/upgrade_storage', methods=['POST'])
def buy_storage_upgrade():
    """ترقية مستوى المخزن وإرجاع السعة الجديدة فوراً للواجهة"""
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)

    if is_rate_limited(user_id_str, "upgrade_storage", min_interval=1.5, is_mutation=True):
        return jsonify({"success": False, "error": "جاري معالجة طلب ترقية المخزن، يرجى الانتظار"}), 429

    if not acquire_user_mutation_lock(user_id_str):
        return jsonify({"success": False, "error": "جاري تنفيذ عملية أخرى لحسابك، يرجى الانتظار"}), 429

    try:
        result = buy_storage_db(user_id_str)
        return jsonify(result), (200 if result.get("success") else 400)
    except Exception as e:
        print(f"Error upgrade storage: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء ترقية المخزن"}), 500
    finally:
        release_user_mutation_lock(user_id_str)


@farm_bp.route('/daily_claim', methods=['POST'])
@farm_bp.route('/farm/daily_claim', methods=['POST'])
@farm_bp.route('/api/farm/daily_claim', methods=['POST'])
def claim_daily():
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)

    if is_rate_limited(user_id_str, "daily_claim", min_interval=2.0, is_mutation=True):
        return jsonify({"success": False, "error": "يرجى الانتظار قبل استلام المكافأة اليومية مجدداً"}), 429

    data = request.get_json(silent=True) or {}
    
    if not is_ad_watched(data):
        return jsonify({
            "success": False, 
            "error": "يجب مشاهدة الإعلان بالكامل أولاً لاستلام المكافأة اليومية"
        }), 400

    if not acquire_user_mutation_lock(user_id_str):
        return jsonify({"success": False, "error": "جاري تنفيذ عملية أخرى لحسابك، يرجى الانتظار"}), 429

    try:
        result = claim_daily_reward_db(user_id_str)
        return jsonify(result), (200 if result.get("success") else 400)
    except Exception as e:
        print(f"Error daily claim: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة اليومية"}), 500
    finally:
        release_user_mutation_lock(user_id_str)


@farm_bp.route('/daily_boost', methods=['POST'])
@farm_bp.route('/farm/daily_boost', methods=['POST'])
@farm_bp.route('/api/farm/daily_boost', methods=['POST'])
def claim_daily_boost():
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)

    if is_rate_limited(user_id_str, "daily_boost", min_interval=3.0, is_mutation=True):
        return jsonify({"success": False, "error": "تم استلام طلب تفعيل التعزيز بالكامل، يرجى عدم تكرار الطلب"}), 429

    data = request.get_json(silent=True) or {}
    
    if not is_ad_watched(data):
        return jsonify({
            "success": False, 
            "error": "يجب مشاهدة الإعلان بالكامل أولاً لتفعيل معزز سرعة التعدين"
        }), 400

    if not acquire_user_mutation_lock(user_id_str):
        return jsonify({"success": False, "error": "جاري تنفيذ عملية أخرى لحسابك، يرجى الانتظار"}), 429

    try:
        result = claim_daily_boost_db(user_id_str)
        return jsonify(result), (200 if result.get("success") else 400)
    except Exception as e:
        print(f"Error daily boost: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء تفعيل التعزيز"}), 500
    finally:
        release_user_mutation_lock(user_id_str)


@farm_bp.route('/leaderboard', methods=['GET', 'POST'])
@farm_bp.route('/farm/leaderboard', methods=['GET', 'POST'])
@farm_bp.route('/api/farm/leaderboard', methods=['GET', 'POST'])
def get_leaderboard():
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    if is_rate_limited(user_id_str, "leaderboard", min_interval=1.0):
        return jsonify({"success": False, "error": "يرجى التمهل في طلب قائمة المتصدرين"}), 429

    try:
        leaderboard = get_mining_leaderboard_db(limit=10)
        return jsonify({"success": True, "leaderboard": leaderboard}), 200
    except Exception as e:
        print(f"Error getting leaderboard: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "خطأ في جلب قائمة المتصدرين"}), 500


# ==========================================
# 👥 قسم الأصدقاء والإحالات (Friends & Referrals)
# ==========================================

@farm_bp.route('/friends', methods=['GET', 'POST'])
@farm_bp.route('/farm/friends', methods=['GET', 'POST'])
@farm_bp.route('/api/farm/friends', methods=['GET', 'POST'])
def get_user_friends():
    """جلب قائمة الأصدقاء المدعوين وإحصائيات مكافآت الإحالة من نظام الأصدقاء الموحد"""
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    if is_rate_limited(user_id_str, "friends", min_interval=0.5):
        return jsonify({"success": False, "error": "يرجى التمهل في طلب قائمة الأصدقاء"}), 429

    try:
        summary = get_friends_data_db(user_id_str)
        friends_list = get_user_friends_list_db(user_id_str)
        friends_data = {
            "friends": friends_list,
            "total_referrals": len(friends_list),
            "eligible_referrals": summary.get("eligible_task_friends_count", 0),
            "referral_earnings": summary.get("total_ref_earnings", 0.0),
            "unclaimed_rewards": summary.get("pending_ref_earnings", 0.0),
            "invite_link": f"https://t.me/zngoxe_bot?start=ref_{user_id_str}"
        }
        return jsonify({"success": True, **friends_data}), 200
    except Exception as e:
        print(f"Error getting friends: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "خطأ في جلب قائمة الأصدقاء"}), 500


@farm_bp.route('/claim_friends_reward', methods=['POST'])
@farm_bp.route('/farm/claim_friends_reward', methods=['POST'])
@farm_bp.route('/api/farm/claim_friends_reward', methods=['POST'])
def claim_friends_reward():
    """تجميع مكافآت دعوة الأصدقاء المعلقة"""
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)

    if is_rate_limited(user_id_str, "claim_friends_reward", min_interval=2.0, is_mutation=True):
        return jsonify({"success": False, "error": "يرجى الانتظار قبل استلام مكافآت الإحالة مجدداً"}), 429

    if not acquire_user_mutation_lock(user_id_str):
        return jsonify({"success": False, "error": "جاري تنفيذ عملية أخرى لحسابك، يرجى الانتظار"}), 429

    try:
        result = claim_ref_earnings_db(user_id_str)
        return jsonify(result), (200 if result.get("success") else 400)
    except Exception as e:
        print(f"Error claim friends reward: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء تجميع مكافأة الأصدقاء"}), 500
    finally:
        release_user_mutation_lock(user_id_str)

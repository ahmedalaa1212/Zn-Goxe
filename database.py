import json
import os
import time
import firebase_admin
from firebase_admin import credentials, firestore

db = None

# ==================== Dynamic In-Memory Cache System ====================
_SETTINGS_CACHE = None
_SETTINGS_CACHE_TIME = 0
SETTINGS_CACHE_TTL = 300

_LEADERBOARD_CACHE = None
_LEADERBOARD_CACHE_TIME = 0
LEADERBOARD_CACHE_TTL = 180
# ========================================================================


def initialize_firebase():
    """تهيئة الاتصال بقاعدة بيانات Firebase Firestore مع حماية المفاتيح"""
    global db
    if not firebase_admin._apps:
        firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
        try:
            if firebase_creds_json:
                try:
                    creds_dict = json.loads(firebase_creds_json)
                except Exception:
                    creds_dict = json.loads(firebase_creds_json.replace("\\n", "\n"))

                if isinstance(creds_dict, dict) and "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace(
                        "\\n", "\n"
                    )

                cred = credentials.Certificate(creds_dict)
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                else:
                    raise FileNotFoundError("لم يتم العثور على بيانات اعتماد Firebase!")

            firebase_admin.initialize_app(cred)
            print("✅ Firebase Initialized Successfully!")
        except Exception as e:
            print(f"❌ Critical Firebase Initialization Error: {e}")
            raise e

    if db is None:
        db = firestore.client()
    return db


def get_db():
    """الحصول على كائن قاعدة البيانات بطريقة آمنة"""
    global db
    if db is None:
        db = initialize_firebase()
    return db


def clear_settings_cache():
    """تفريغ وتصفير ذاكرة التخزين المؤقت للإعدادات"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    _SETTINGS_CACHE = None
    _SETTINGS_CACHE_TIME = 0


def ensure_game_settings_exist():
    """ضمان وجود مستند الإعدادات الأساسية والإحصائيات التجميعية في Firestore"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    current_db = get_db()
    try:
        config_ref = current_db.collection("app_config").document("game_settings")
        doc_snap = config_ref.get()

        if doc_snap.exists:
            existing_data = doc_snap.to_dict() or {}
            needs_update = False
            updates = {}

            if "zn_go_config" not in existing_data and "grid_game_config" not in existing_data:
                zn_cfg = {
                    "min_bet": 10.0,
                    "target_margin": 0.70,
                    "default_broken_coins": 3,
                }
                existing_data["zn_go_config"] = zn_cfg
                updates["zn_go_config"] = zn_cfg
                updates["grid_game_config"] = zn_cfg
                needs_update = True
            else:
                zn_cfg = existing_data.get("zn_go_config") or existing_data.get("grid_game_config", {})
                if "target_margin" not in zn_cfg or zn_cfg.get("target_margin", 0) == 0:
                    zn_cfg["target_margin"] = 0.70
                    zn_cfg["min_bet"] = zn_cfg.get("min_bet", 10.0)
                    zn_cfg["default_broken_coins"] = zn_cfg.get("default_broken_coins", 3)
                    existing_data["zn_go_config"] = zn_cfg
                    updates["zn_go_config"] = zn_cfg
                    updates["grid_game_config"] = zn_cfg
                    needs_update = True

            if "arena_config" not in existing_data:
                arena_cfg = {
                    "entry_fee": 10.0,
                    "min_participants": 20,
                    "prize_pool_percentage": 0.30,
                    "target_margin": 0.70,
                }
                existing_data["arena_config"] = arena_cfg
                updates["arena_config"] = arena_cfg
                needs_update = True

            if "global_total_bets" not in existing_data:
                updates["global_total_bets"] = 0.0
                existing_data["global_total_bets"] = 0.0
                needs_update = True
            if "global_total_wins" not in existing_data:
                updates["global_total_wins"] = 0.0
                existing_data["global_total_wins"] = 0.0
                needs_update = True

            if needs_update:
                config_ref.update(updates)

            _SETTINGS_CACHE = existing_data
            _SETTINGS_CACHE_TIME = time.time()
            return existing_data

        daily_rewards_30_days = {
            f"day_{i}": val
            for i, val in enumerate(
                [
                    100, 150, 200, 250, 300, 350, 400, 450, 500, 550,
                    600, 600, 650, 650, 700, 700, 750, 750, 800, 800,
                    850, 850, 900, 900, 950, 950, 1000, 1000, 1100, 1250,
                ],
                start=1,
            )
        }

        mining_cfg = {
            "1": {"price": 3500.0, "rate": 5.0, "rate_bonus": 5.0, "base_cost": 3500.0, "max": 10},
            "2": {"price": 11500.0, "rate": 15.0, "rate_bonus": 15.0, "base_cost": 11500.0, "max": 10},
            "3": {"price": 28000.0, "rate": 35.0, "rate_bonus": 35.0, "base_cost": 28000.0, "max": 10},
            "4": {"price": 68000.0, "rate": 80.0, "rate_bonus": 80.0, "base_cost": 68000.0, "max": 10},
            "5": {"price": 165000.0, "rate": 180.0, "rate_bonus": 180.0, "base_cost": 165000.0, "max": 10},
            "6": {"price": 390000.0, "rate": 400.0, "rate_bonus": 400.0, "base_cost": 390000.0, "max": 10},
            "7": {"price": 950000.0, "rate": 900.0, "rate_bonus": 900.0, "base_cost": 950000.0, "max": 10},
            "8": {"price": 2300000.0, "rate": 2000.0, "rate_bonus": 2000.0, "base_cost": 2300000.0, "max": 10},
            "9": {"price": 5500000.0, "rate": 4500.0, "rate_bonus": 4500.0, "base_cost": 5500000.0, "max": 10},
        }

        storage_cfg = {
            "0": {"capacity": 100.0, "price": 0},
            "1": {"capacity": 300.0, "price": 3000},
            "2": {"capacity": 800.0, "price": 8500},
            "3": {"capacity": 2000.0, "price": 25000},
            "4": {"capacity": 5000.0, "price": 70000},
            "5": {"capacity": 12000.0, "price": 180000},
            "6": {"capacity": 28000.0, "price": 450000},
            "7": {"capacity": 65000.0, "price": 1100000},
            "8": {"capacity": 150000.0, "price": 2800000},
            "9": {"capacity": 350000.0, "price": 7000000},
            "10": {"capacity": 800000.0, "price": 18000000},
        }

        zn_go_default = {
            "min_bet": 10.0,
            "target_margin": 0.70,
            "default_broken_coins": 3,
        }

        initial_settings = {
            "usd_to_zn_rate": 1000000,
            "ad_reward_boost": 0.5,
            "daily_rewards": daily_rewards_30_days,
            "mining_config": mining_cfg,
            "storage_config": storage_cfg,
            "global_total_bets": 0.0,
            "global_total_wins": 0.0,
            "zn_go_config": zn_go_default,
            "grid_game_config": zn_go_default,
            "arena_config": {
                "entry_fee": 10.0,
                "min_participants": 20,
                "prize_pool_percentage": 0.30,
                "target_margin": 0.70,
            },
        }

        config_ref.set(initial_settings)
        _SETTINGS_CACHE = initial_settings
        _SETTINGS_CACHE_TIME = time.time()
        print("✅ تم إنشاء app_config/game_settings بنجاح!")
        return initial_settings
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة الإعدادات: {e}")
        return None


def get_game_settings():
    """جلب إعدادات اللعبة من الكاش المؤقت لتوفير قراءات Firestore"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    now = time.time()
    if (
        _SETTINGS_CACHE is not None
        and (now - _SETTINGS_CACHE_TIME) < SETTINGS_CACHE_TTL
    ):
        return _SETTINGS_CACHE

    try:
        current_db = get_db()
        doc = current_db.collection("app_config").document("game_settings").get()
        if doc.exists:
            data = doc.to_dict() or {}
            _SETTINGS_CACHE = data
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
        else:
            return ensure_game_settings_exist() or {}
    except Exception as e:
        print(f"❌ Error getting game settings: {e}")
        return _SETTINGS_CACHE or {}


def update_game_settings(new_settings_dict):
    """تحديث الإعدادات وتفريغ الكاش فوراً"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    try:
        current_db = get_db()
        config_ref = current_db.collection("app_config").document("game_settings")
        config_ref.set(new_settings_dict, merge=True)

        clear_settings_cache()
        doc_snap = config_ref.get()
        if doc_snap.exists:
            _SETTINGS_CACHE = doc_snap.to_dict() or {}
            _SETTINGS_CACHE_TIME = time.time()
        return True, "تم حفظ الإعدادات وتحديث السيرفر بنجاح!"
    except Exception as e:
        print(f"❌ Error updating game settings: {e}")
        return False, f"حدث خطأ أثناء الحفظ: {e}"


# التهيئة الأوليّة
try:
    initialize_firebase()
    ensure_game_settings_exist()
except Exception as e:
    print(f"⚠️ تنبيه أثناء تهيئة DB تلقائياً: {e}")

# =========================================================================
# Re-exports: إتاحة جميع دوال الموديولات عبر الملف الرئيسي لمنع كسر الكود القائم
# =========================================================================
from users.users_db import (
    is_user_banned,
    ban_user,
    init_user,
    get_user,
    get_all_users_admin,
    update_user,
    get_leaderboard,
)

from friends.friends_db import (
    get_user_friends,
    add_referral_reward,
)

from tasks.tasks_db import (
    get_active_campaigns,
    complete_user_task,
    create_ad_campaign,
    convert_balance_to_ad_balance,
    claim_daily_reward,
)

from games.games_db import (
    update_zn_go_config,
    update_grid_game_config,
    get_arena_config,
    update_arena_config,
    record_bet_placed,
    record_game_loss,
    record_game_win,
    get_game_profit_stats,
    should_user_win_next_step,
)

from settings.settings_db import (
    save_admin_settings,
    get_admin_dashboard_stats,
    is_admin,
    is_moderator,
    is_admin_or_mod,
    get_moderators,
    add_moderator,
    delete_moderator,
    get_admin_logs,
    log_admin_action,
)

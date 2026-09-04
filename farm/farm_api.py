import os
import traceback
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
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
    DEFAULT_GAME_SETTINGS
)

farm_bp = Blueprint('farm', __name__)


def to_bool(val):
    """تحويل قيم البوليان بمرونة وسلاسة لمنع أخطاء النصوص والنصوص الفارغة"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    if isinstance(val, (int, float)):
        return val != 0
    return False


def calculate_user_effective_stats(user_data, game_settings, now):
    """
    احتساب السعة الكلية والخصائص الفعالة للمستخدم ديناميكياً
    مع حساب تفعيل مضاعفة السعة لـ VIP والبوت التلقائي
    """
    storage_configs = game_settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS.get("storage_capacities", {})
    storage_lvl = str(user_data.get("storage_level", 0))
    
    # 1. جلب السعة الأساسية للمستوى الحالي
    lvl_info = storage_configs.get(storage_lvl, {})
    base_cap = float(lvl_info.get("capacity", lvl_info.get("cap", 0.5)))
    extra_storage = float(user_data.get("extra_storage", 0.0))
    raw_cap = base_cap + extra_storage

    # 2. التحقق من صلاحية باقة VIP ومضاعفة السعة
    vip_status = user_data.get("vip_status", {})
    is_double_storage_active = False
    is_auto_bot_active = False

    if isinstance(vip_status, dict):
        expires_at_raw = vip_status.get("expires_at")
        is_expired = False
        if expires_at_raw:
            try:
                if isinstance(expires_at_raw, str):
                    exp_dt = datetime.fromisoformat(expires_at_raw.replace('Z', '+00:00'))
                elif isinstance(expires_at_raw, datetime):
                    exp_dt = expires_at_raw
                else:
                    exp_dt = None

                if exp_dt and exp_dt <= now:
                    is_expired = True
            except Exception as e:
                print(f"Error parsing VIP expiration: {e}")

        if not is_expired:
            if to_bool(vip_status.get("double_storage", False)):
                is_double_storage_active = True
            if to_bool(vip_status.get("auto_bot", False)):
                is_auto_bot_active = True

    # 3. تطبیق مضاعفة السعة في حال تفعيل VIP
    effective_max_cap = raw_cap * 2.0 if is_double_storage_active else raw_cap
    
    user_data["max_cap"] = round(effective_max_cap, 4)
    user_data["is_double_storage_active"] = is_double_storage_active
    user_data["is_auto_bot_active"] = is_auto_bot_active

    return user_data


@farm_bp.route('/player_data', methods=['GET', 'POST'])
@farm_bp.route('/farm/player_data', methods=['GET', 'POST'])
@farm_bp.route('/api/farm/player_data', methods=['GET', 'POST'])
def get_player_data():
    """جلب كافة بيانات اللاعب وإعدادات المزرعة الديناميكية من Firebase وحساب قيم VIP"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
    
    user_id_str = str(telegram_id)
    try:
        user_data, game_settings, now = get_or_create_user_farm_data(user_id_str)
        
        # حساب وتحديث السعة والسرعة الفعالة للمستخدم (تطبيق مضاعفة VIP)
        user_data = calculate_user_effective_stats(user_data, game_settings, now)

        welcome_seen = to_bool(user_data.get("welcome_seen", False))
        user_data["welcome_seen"] = welcome_seen
        user_data["is_new_user"] = not welcome_seen

        parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))
        upgrade_configs = game_settings.get("upgrade_config") or DEFAULT_GAME_SETTINGS["upgrade_config"]
        
        upgrade_costs = {}
        for k, v in upgrade_configs.items():
            upgrade_costs[int(k)] = {
                "cost_zn": float(v.get("cost_zn", v.get("base_cost", v.get("price", 0)))),
                "cost_usd": float(v.get("cost_usd", v.get("base_cost_usd", 0.0))),
                "rate": float(v.get("rate_bonus", v.get("rate", 0)))
            }
        
        storage_configs = game_settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_capacities"]
        mining_cfg = game_settings.get("mining_config", {})
        
        daily_boost_reward = float(mining_cfg.get("daily_boost_reward", 0.10))
        max_daily_boost_rate = float(mining_cfg.get("max_daily_boost_rate", 4.5))
        boost_max_reward_coins = float(mining_cfg.get("boost_max_reward_coins", 35.0))
        cooldown_seconds = int(mining_cfg.get("claim_cooldown_seconds", 15))
        max_upgrades_per_level = int(mining_cfg.get("max_upgrades_per_level", 15))

        adsgram_block_id = os.environ.get("ADSGRAM_BLOCK_ID", "")

        return jsonify({
            "success": True, 
            "player": user_data, 
            "server_time": now.isoformat(),
            "cooldown_seconds": cooldown_seconds,
            "game_config": {
                "daily_rewards": parsed_rewards,
                "upgrade_costs": upgrade_costs,
                "storage_config": storage_configs,
                "daily_boost_reward": daily_boost_reward,
                "max_daily_boost_rate": max_daily_boost_rate,
                "boost_max_reward_coins": boost_max_reward_coins,
                "max_upgrades_per_level": max_upgrades_per_level,
                "boost_cooldown_seconds": 10800, # 3 ساعات فترة انتظار المعزز
                "boost_duration_seconds": 7200,   # 2 ساعة مدة التفعيل
                "adsgram_block_id": adsgram_block_id
            }
        }), 200
    except Exception as e:
        print(f"Error player_data: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500


@farm_bp.route('/dismiss_welcome', methods=['POST'])
@farm_bp.route('/farm/dismiss_welcome', methods=['POST'])
@farm_bp.route('/api/farm/dismiss_welcome', methods=['POST'])
def dismiss_welcome():
    """إغلاق نافذة الترحيب وتخزين الحالة لعدم ظهورها مجدداً"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
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
    """تجميع المحصول المعدن"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    try:
        result = claim_mined_tokens_db(user_id_str)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"Error claim: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء التجميع"}), 500


@farm_bp.route('/upgrade', methods=['POST'])
@farm_bp.route('/farm/upgrade', methods=['POST'])
@farm_bp.route('/api/farm/upgrade', methods=['POST'])
def buy_upgrade():
    """شراء ترقية سرعة التعدين"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    data = request.get_json(silent=True) or {}
    raw_level = data.get("level")
    level = str(raw_level) if raw_level is not None else ""
    
    if not level or level not in [str(i) for i in range(1, 10)]:
        return jsonify({"success": False, "error": "مستوى غير صحيح"}), 400
        
    user_id_str = str(telegram_id)
    try:
        result = buy_upgrade_db(user_id_str, level)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"Error upgrade: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية الشراء"}), 500


@farm_bp.route('/upgrade_storage', methods=['POST'])
@farm_bp.route('/farm/upgrade_storage', methods=['POST'])
@farm_bp.route('/api/farm/upgrade_storage', methods=['POST'])
def buy_storage_upgrade():
    """شراء ترقية سعة المخزن"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    try:
        result = buy_storage_db(user_id_str)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"Error upgrade storage: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء ترقية المخزن"}), 500


@farm_bp.route('/daily_claim', methods=['POST'])
@farm_bp.route('/farm/daily_claim', methods=['POST'])
@farm_bp.route('/api/farm/daily_claim', methods=['POST'])
def claim_daily():
    """استلام المكافأة اليومية"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    try:
        result = claim_daily_reward_db(user_id_str)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"Error daily claim: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة اليومية"}), 500


@farm_bp.route('/daily_boost', methods=['POST'])
@farm_bp.route('/farm/daily_boost', methods=['POST'])
@farm_bp.route('/api/farm/daily_boost', methods=['POST'])
def claim_daily_boost():
    """تفعيل التعزيز اليومي للسرعة لمدة ساعتين مع فترة انتظار 3 ساعات وتسجيل last_boost_time"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    try:
        result = claim_daily_boost_db(user_id_str)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"Error daily boost: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء تفعيل التعزيز"}), 500


@farm_bp.route('/leaderboard', methods=['GET', 'POST'])
@farm_bp.route('/farm/leaderboard', methods=['GET', 'POST'])
@farm_bp.route('/api/farm/leaderboard', methods=['GET', 'POST'])
def get_leaderboard():
    """جلب قائمة أفضل 10 متصدرين للتعدين"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
        
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
    """جلب قائمة الأصدقاء المدعوين وإحصائيات مكافآت الإحالة"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    try:
        try:
            from farm.farm_db import get_user_friends_db
            friends_data = get_user_friends_db(user_id_str)
        except ImportError:
            # fallback في حال عدم الربط المباشر مع farm_db
            user_data, _, _ = get_or_create_user_farm_data(user_id_str)
            friends_data = {
                "friends": user_data.get("referrals_list", []),
                "total_referrals": int(user_data.get("referral_count", 0)),
                "referral_earnings": float(user_data.get("referral_earnings", 0.0)),
                "unclaimed_rewards": float(user_data.get("unclaimed_referral_rewards", 0.0)),
                "invite_link": f"https://t.me/ZnGoxe_Bot?start=ref_{user_id_str}"
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
    """تجميع مكافآت دعوة الأصدقاء"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res
        
    user_id_str = str(telegram_id)
    try:
        try:
            from farm.farm_db import claim_referral_rewards_db
            result = claim_referral_rewards_db(user_id_str)
        except ImportError:
            result = {"success": False, "error": "دالة تجميع المكافآت غير متوفرة في قاعدة البيانات حالياً"}
            
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"Error claim friends reward: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "حدث خطأ أثناء تجميع مكافأة الأصدقاء"}), 500

import traceback
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
    parse_daily_rewards,
    DEFAULT_GAME_SETTINGS
)

farm_bp = Blueprint('farm', __name__)

@farm_bp.route('/player_data', methods=['GET', 'POST'])
@farm_bp.route('/farm/player_data', methods=['GET', 'POST'])
@farm_bp.route('/api/farm/player_data', methods=['GET', 'POST'])
def get_player_data():
    """جلب كافة بيانات اللاعب وإعدادات المزرعة الديناميكية بالكامل"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res
    
    user_id_str = str(telegram_id)
    try:
        user_data, game_settings, now = get_or_create_user_farm_data(user_id_str)
        
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
        daily_boost_reward = round(float(mining_cfg.get("daily_boost_reward", 0.15)), 2)
        max_daily_boost_rate = round(float(mining_cfg.get("max_daily_boost_rate", 4.5)), 2)
        boost_max_reward_coins = round(float(mining_cfg.get("boost_max_reward_coins", 35.0)), 2)
        cooldown_seconds = int(mining_cfg.get("claim_cooldown_seconds", 15))
        max_upgrades_per_level = int(mining_cfg.get("max_upgrades_per_level", 15))

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
                "max_upgrades_per_level": max_upgrades_per_level
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
    """تفعيل التعزيز اليومي للسرعة أو استلام مكافأة العملات"""
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

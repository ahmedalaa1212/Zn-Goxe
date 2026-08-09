from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from farm.farm_db import (
    get_or_create_user_farm_data,
    claim_mined_tokens_db,
    buy_upgrade_db,
    claim_daily_reward_db,
    claim_daily_boost_db,
    parse_daily_rewards,
    DEFAULT_FARM_SETTINGS
)

farm_bp = Blueprint('farm', __name__)

@farm_bp.route('/player_data', methods=['GET', 'POST'])
def get_player_data():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res

    user_id_str = str(telegram_id)
    try:
        user_data, game_settings, now = get_or_create_user_farm_data(user_id_str)

        parsed_rewards = parse_daily_rewards(game_settings.get("daily_rewards"))
        upgrade_configs = game_settings.get("upgrade_config") or DEFAULT_FARM_SETTINGS["upgrade_config"]
        upgrade_costs = {int(k): float(v.get("base_cost", v.get("price", 0))) for k, v in upgrade_configs.items()}
        
        mining_cfg = game_settings.get("mining_config", DEFAULT_FARM_SETTINGS["mining_config"])
        daily_boost_reward = round(float(mining_cfg.get("daily_boost_reward", 0.5)), 2)
        daily_boost_target_speed = round(float(mining_cfg.get("daily_boost_target_speed", 15.0)), 2)
        daily_boost_coin_reward = round(float(mining_cfg.get("daily_boost_coin_reward", 50.0)), 2)
        cooldown_seconds = int(mining_cfg.get("cooldown_seconds", 15))

        return jsonify({
            "success": True, 
            "player": user_data, 
            "server_time": now.isoformat(),
            "cooldown_seconds": cooldown_seconds,
            "game_config": {
                "daily_rewards": parsed_rewards,
                "upgrade_costs": upgrade_costs,
                "daily_boost_reward": daily_boost_reward,
                "daily_boost_target_speed": daily_boost_target_speed,
                "daily_boost_coin_reward": daily_boost_coin_reward
            }
        }), 200
    except Exception as e:
        print(f"Error player_data: {e}")
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500


@farm_bp.route('/claim', methods=['POST'])
def claim_mined_tokens():
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
        return jsonify({"success": False, "error": "حدث خطأ أثناء التجميع"}), 500


@farm_bp.route('/upgrade', methods=['POST'])
def buy_upgrade():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res

    data = request.json or {}
    level = str(data.get("level"))

    if not level or level not in [str(i) for i in range(1, 10)]:
        return jsonify({"success": False, "error": "مستوى غير صحيح"}), 400

    user_id_str = str(telegram_id)
    try:
        result = buy_upgrade_db(user_id_str, level)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"Error upgrade: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية الشراء"}), 500


@farm_bp.route('/daily_claim', methods=['POST'])
def claim_daily():
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
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة اليومية"}), 500


@farm_bp.route('/daily_boost', methods=['POST'])
def claim_daily_boost():
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
        return jsonify({"success": False, "error": "حدث خطأ أثناء تفعيل التعزيز"}), 500

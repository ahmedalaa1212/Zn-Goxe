import random
from flask import Blueprint, jsonify, request
import database
from core.security import get_authenticated_user
from games.fogo.fogo_db import (
    get_fogo_config,
    get_bot_profit_percentage,
    update_fogo_economy_stats,
    get_active_fogo_session,
    save_fogo_session,
    delete_fogo_session
)

fogo_bp = Blueprint('fogo', __name__)

MAX_MULTIPLIERS = {
    3: 5.0,    # 13 مربع آمن
    4: 10.0,   # 12 مربع آمن
    5: 15.0,   # 11 مربع آمن
    6: 20.0    # 10 مربعات آمنة
}

def calculate_multiplier(mines_count, opened_count):
    """حساب المضاعف التصاعدي بدقة متناهية وصولاً للحد الأقصى"""
    max_mult = MAX_MULTIPLIERS.get(mines_count, 5.0)
    safe_tiles_total = 16 - mines_count
    
    if opened_count <= 0:
        return 1.0
    if opened_count >= safe_tiles_total:
        return float(max_mult)

    progress = opened_count / safe_tiles_total
    mult = 1.0 + (max_mult - 1.0) * (progress ** 1.35)
    return round(mult, 2)

def update_user_balance_safe(telegram_id, new_balance, delta_amount):
    """تحديث رصيد المستخدم بشكل آمن في database"""
    try:
        if hasattr(database, 'update_user'):
            database.update_user(telegram_id, {'balance': float(new_balance)})
        elif hasattr(database, 'update_user_balance'):
            database.update_user_balance(telegram_id, float(delta_amount))
        elif hasattr(database, 'add_balance'):
            database.add_balance(telegram_id, float(delta_amount))
    except Exception as e:
        print(f"❌ خطأ أثناء تحديث الرصيد fogo: {e}")

@fogo_bp.route('/config', methods=['GET', 'POST'])
def get_config():
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    config = get_fogo_config()
    session = get_active_fogo_session(telegram_id)
    user_data = database.get_user(telegram_id) or {}

    return jsonify({
        "success": True,
        "allowed_bet_options": config.get('allowed_bet_options', [50, 100, 300, 500, 1000, 8000]),
        "active_session": session,
        "current_balance": float(user_data.get('balance', 0.0))
    }), 200

@fogo_bp.route('/start', methods=['POST'])
def start_game():
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    existing_session = get_active_fogo_session(telegram_id)
    if existing_session and existing_session.get('status') == 'active':
        return jsonify({"success": False, "error": "لديك جولة نشطة بالفعل!"}), 400

    data = request.json or {}
    try:
        bet_amount = float(data.get('bet_amount', 0))
        mines_count = int(data.get('mines_count', 3))
        shield_enabled = bool(data.get('shield_enabled', False))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "بيانات غير صالحة"}), 400

    if mines_count not in [3, 4, 5, 6]:
        return jsonify({"success": False, "error": "عدد المخاطر يجب أن يكون 3، 4، 5، أو 6"}), 400

    config = get_fogo_config()
    allowed_options = config.get('allowed_bet_options', [50, 100, 300, 500, 1000, 8000])

    if int(bet_amount) not in [int(x) for x in allowed_options]:
        return jsonify({"success": False, "error": "مبلغ الرهان غير متاح"}), 400

    shield_fee = (bet_amount * 0.25) if shield_enabled else 0.0
    total_cost = bet_amount + shield_fee

    user_data = database.get_user(telegram_id) or {}
    current_balance = float(user_data.get('balance', 0.0))

    if current_balance < total_cost:
        return jsonify({
            "success": False, 
            "error": f"رصيدك غير كافٍ! تكلفة الجولة الإجمالية {total_cost:.2f} ZN (شاملة 25% رسوم الدرع). رصيدك الحالي: {current_balance:.2f} ZN"
        }), 400

    new_balance = current_balance - total_cost
    update_user_balance_safe(telegram_id, new_balance, -total_cost)

    current_bot_profit_pct = get_bot_profit_percentage()
    threshold = float(config.get('force_loss_threshold', 59.0))
    force_loss = (current_bot_profit_pct < threshold) or config.get('force_loss_override', False)

    session_data = {
        'telegram_id': telegram_id,
        'bet_amount': bet_amount,
        'shield_fee': shield_fee,
        'total_cost': total_cost,
        'mines_count': mines_count,
        'shield_enabled': shield_enabled,
        'shield_active': shield_enabled,
        'opened_tiles': [],
        'current_multiplier': 1.0,
        'force_loss': force_loss,
        'status': 'active'
    }

    save_fogo_session(telegram_id, session_data)

    return jsonify({
        "success": True,
        "message": "تم بدء الجولة بنجاح",
        "bet_amount": bet_amount,
        "shield_fee": shield_fee,
        "total_cost": total_cost,
        "mines_count": mines_count,
        "shield_active": shield_enabled,
        "new_balance": new_balance
    }), 200

@fogo_bp.route('/reveal', methods=['POST'])
def reveal_tile():
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    session = get_active_fogo_session(telegram_id)
    if not session or session.get('status') != 'active':
        return jsonify({"success": False, "error": "لا توجد جولة قائمة"}), 400

    data = request.json or {}
    try:
        tile_index = int(data.get('tile_index', -1))
    except (ValueError, TypeError):
        tile_index = -1

    if tile_index < 0 or tile_index > 15:
        return jsonify({"success": False, "error": "مربع غير صالح"}), 400

    opened_tiles = session.get('opened_tiles', [])
    if tile_index in opened_tiles:
        return jsonify({"success": False, "error": "تم فتح هذا المربع بالفعل"}), 400

    mines_count = session.get('mines_count', 3)
    safe_tiles_total = 16 - mines_count
    force_loss = session.get('force_loss', False)
    shield_active = session.get('shield_active', False)
    bet_amount = float(session.get('bet_amount', 0.0))
    total_cost = float(session.get('total_cost', bet_amount))

    risk_factor = (mines_count / 16.0) + (len(opened_tiles) * 0.04)
    is_hit_loss = force_loss or (random.random() < risk_factor)

    if is_hit_loss:
        if shield_active:
            opened_tiles.append(tile_index)
            session['opened_tiles'] = opened_tiles
            session['shield_active'] = False
            save_fogo_session(telegram_id, session)

            return jsonify({
                "success": True,
                "result": "shield_saved",
                "message": "🛡️ تم تدمير الدرع أثناء امتصاص الصدمة! أنت في أمان لاستكمال الجولة."
            }), 200
        else:
            delete_fogo_session(telegram_id)
            update_fogo_economy_stats(total_cost, 0.0)

            user_data = database.get_user(telegram_id) or {}
            return jsonify({
                "success": True,
                "result": "broken_coin",
                "message": "💥 تعثرت في عملة مكسورة وخسرت الجولة!",
                "current_balance": float(user_data.get('balance', 0.0))
            }), 200

    else:
        opened_tiles.append(tile_index)
        session['opened_tiles'] = opened_tiles
        opened_count = len(opened_tiles)
        
        new_multiplier = calculate_multiplier(mines_count, opened_count)
        session['current_multiplier'] = new_multiplier

        if opened_count >= safe_tiles_total:
            winnings = bet_amount * new_multiplier
            user_data = database.get_user(telegram_id) or {}
            old_balance = float(user_data.get('balance', 0.0))
            final_balance = old_balance + winnings

            update_user_balance_safe(telegram_id, final_balance, winnings)
            update_fogo_economy_stats(total_cost, winnings)
            delete_fogo_session(telegram_id)

            return jsonify({
                "success": True,
                "result": "max_win",
                "current_multiplier": new_multiplier,
                "winnings": winnings,
                "new_balance": final_balance,
                "message": "🎉 مبروك! استخرجت جميع العملات الذهبية وحققت أقصى ربح!"
            }), 200

        save_fogo_session(telegram_id, session)

        return jsonify({
            "success": True,
            "result": "safe",
            "current_multiplier": new_multiplier,
            "opened_count": opened_count,
            "message": "✨ عملة ذهبية ناطعة!"
        }), 200

@fogo_bp.route('/cashout', methods=['POST'])
def cashout():
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    session = get_active_fogo_session(telegram_id)
    if not session or session.get('status') != 'active':
        return jsonify({"success": False, "error": "لا توجد جولة قائمة"}), 400

    opened_tiles = session.get('opened_tiles', [])
    if len(opened_tiles) < 1:
        return jsonify({"success": False, "error": "يجب استخراج عملة واحدة على الأقل للاقتطاع!"}), 400

    bet_amount = float(session.get('bet_amount', 0.0))
    total_cost = float(session.get('total_cost', bet_amount))
    multiplier = float(session.get('current_multiplier', 1.0))
    winnings = bet_amount * multiplier

    user_data = database.get_user(telegram_id) or {}
    old_balance = float(user_data.get('balance', 0.0))
    new_balance = old_balance + winnings

    update_user_balance_safe(telegram_id, new_balance, winnings)
    update_fogo_economy_stats(total_cost, winnings)
    delete_fogo_session(telegram_id)

    return jsonify({
        "success": True,
        "message": "تم اقتطاع الأرباح بنجاح!",
        "winnings": winnings,
        "new_balance": new_balance
    }), 200

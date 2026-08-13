import random
from flask import Blueprint, jsonify, request
import database
from core.security import get_authenticated_user
from games.goxe.goxe_db import (
    get_goxe_config,
    get_bot_profit_percentage,
    update_goxe_economy_stats,
    get_active_goxe_session,
    save_goxe_session,
    delete_goxe_session
)

goxe_bp = Blueprint('goxe', __name__)

FLOOR_MULTIPLIERS = [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00]

def update_user_balance_safe(telegram_id, new_balance, delta_amount):
    """
    دالة آمنة ومضمونة لتحديث الرصيد في Firebase بجميع الطرق الممكنة 
    لتفادي اختلاف المسميات في database.py
    """
    try:
        # الطريقة الأولى والأضمن: التحديث المباشر بقيمة الرصيد الكلية
        if hasattr(database, 'update_user'):
            database.update_user(telegram_id, {'balance': float(new_balance)})
        # الطريقة الثانية: التحديث بمقدار التغير (Delta)
        elif hasattr(database, 'update_user_balance'):
            database.update_user_balance(telegram_id, float(delta_amount))
        elif hasattr(database, 'add_balance'):
            database.add_balance(telegram_id, float(delta_amount))
    except Exception as e:
        print(f"❌ خطأ أثناء تحديث الرصيد للمستخدم {telegram_id}: {e}")

@goxe_bp.route('/config', methods=['GET', 'POST'])
def get_config():
    """جلب إعدادات اللعبة وحالة الجولة الحالية للمستخدم مع الرصيد الحالي"""
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    config = get_goxe_config()
    session = get_active_goxe_session(telegram_id)
    user_data = database.get_user(telegram_id) or {}
    
    return jsonify({
        "success": True,
        "min_bet": config.get('min_bet', 10.0),
        "max_bet": config.get('max_bet', 10000.0),
        "multipliers": FLOOR_MULTIPLIERS,
        "active_session": session,
        "current_balance": float(user_data.get('balance', 0.0))
    }), 200

@goxe_bp.route('/start', methods=['POST'])
def start_game():
    """بدء جولة جديدة وخصم الرهان فوراً من الحساب"""
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    existing_session = get_active_goxe_session(telegram_id)
    if existing_session and existing_session.get('status') == 'active':
        return jsonify({"success": False, "error": "لديك جولة قائمة بالفعل، يرجى إكمالها أو السحب!"}), 400

    data = request.json or {}
    try:
        bet_amount = float(data.get('bet_amount', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "قيمة الرهان غير صالحة"}), 400

    config = get_goxe_config()
    min_bet = float(config.get('min_bet', 10.0))
    max_bet = float(config.get('max_bet', 10000.0))

    if bet_amount < min_bet or bet_amount > max_bet:
        return jsonify({"success": False, "error": f"الرهان يجب أن يكون بين {min_bet} و {max_bet}"}), 400

    user_data = database.get_user(telegram_id) or {}
    current_balance = float(user_data.get('balance', 0.0))

    if current_balance < bet_amount:
        return jsonify({"success": False, "error": f"رصيدك غير كافٍ! رصيدك الحالي: {current_balance:.2f} ZN"}), 400

    # 1. حساب الرصيد الجديد
    new_balance = current_balance - bet_amount
    
    # 2. حفظ الخصم فوراً في قاعدة البيانات
    update_user_balance_safe(telegram_id, new_balance, -bet_amount)

    current_bot_profit_pct = get_bot_profit_percentage()
    threshold = float(config.get('force_loss_threshold', 59.0))
    manual_override = config.get('force_loss_override', False)

    force_loss = (current_bot_profit_pct < threshold) or manual_override

    session_data = {
        'telegram_id': telegram_id,
        'bet_amount': bet_amount,
        'current_floor': 0,
        'force_loss': force_loss,
        'status': 'active'
    }
    
    save_goxe_session(telegram_id, session_data)

    return jsonify({
        "success": True,
        "message": "تم بدء الجولة بنجاح",
        "bet_amount": bet_amount,
        "new_balance": new_balance,
        "current_floor": 0,
        "multipliers": FLOOR_MULTIPLIERS
    }), 200

@goxe_bp.route('/climb', methods=['POST'])
def climb_floor():
    """التسلق أو الانفجار وتحديث الرصيد عند الوصول للقمة تلقائياً"""
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    session = get_active_goxe_session(telegram_id)
    if not session or session.get('status') != 'active':
        return jsonify({"success": False, "error": "لا توجد جولة نشطة حالياً"}), 400

    data = request.json or {}
    try:
        door_chosen = int(data.get('door_index', -1))
    except (ValueError, TypeError):
        door_chosen = -1

    if door_chosen not in [0, 1, 2]:
        return jsonify({"success": False, "error": "اختيار الباب غير صحيح"}), 400

    current_floor = session.get('current_floor', 0)
    next_floor = current_floor + 1

    if next_floor > 10:
        return jsonify({"success": False, "error": "وصلت بالفعل للدور الأخير!"}), 400

    force_loss = session.get('force_loss', False)
    bet_amount = float(session.get('bet_amount', 0.0))

    if force_loss:
        is_bomb = True
    else:
        risk_factor = 0.33 + (next_floor * 0.03)
        is_bomb = (random.random() < risk_factor)

    if is_bomb:
        delete_goxe_session(telegram_id)
        update_goxe_economy_stats(bet_amount, 0.0)

        user_data = database.get_user(telegram_id) or {}
        return jsonify({
            "success": True,
            "result": "bomb",
            "bomb_door": door_chosen,
            "message": "💥 للأسف! انفجرت القنبلة وخسرت الجولة.",
            "current_balance": float(user_data.get('balance', 0.0))
        }), 200

    else:
        session['current_floor'] = next_floor
        current_multiplier = FLOOR_MULTIPLIERS[next_floor - 1]
        current_winnings = bet_amount * current_multiplier

        if next_floor == 10:
            delete_goxe_session(telegram_id)
            user_data = database.get_user(telegram_id) or {}
            old_balance = float(user_data.get('balance', 0.0))
            final_balance = old_balance + current_winnings
            
            # إضافة الأرباح بأمان
            update_user_balance_safe(telegram_id, final_balance, current_winnings)
            update_goxe_economy_stats(bet_amount, current_winnings)

            return jsonify({
                "success": True,
                "result": "max_win",
                "current_floor": 10,
                "multiplier": current_multiplier,
                "winnings": current_winnings,
                "new_balance": final_balance,
                "message": "🎉 مبروك! وصلت للقمة في الدور العاشر وتم سحب الأرباح تلقائياً!"
            }), 200

        save_goxe_session(telegram_id, session)

        return jsonify({
            "success": True,
            "result": "safe",
            "current_floor": next_floor,
            "multiplier": current_multiplier,
            "current_winnings": current_winnings,
            "message": f"✨ رائع! صعدت للدور {next_floor}"
        }), 200

@goxe_bp.route('/cashout', methods=['POST'])
def cashout():
    """سحب الأرباح وإضافتها للرصيد"""
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    session = get_active_goxe_session(telegram_id)
    if not session or session.get('status') != 'active':
        return jsonify({"success": False, "error": "لا توجد جولة نشطة للسحب منها"}), 400

    current_floor = session.get('current_floor', 0)
    if current_floor < 1:
        return jsonify({"success": False, "error": "يجب أن تتسلق دوراً واحداً على الأقل لتمكين الانسحاب!"}), 400

    bet_amount = float(session.get('bet_amount', 0.0))
    multiplier = FLOOR_MULTIPLIERS[current_floor - 1]
    winnings = bet_amount * multiplier

    user_data = database.get_user(telegram_id) or {}
    old_balance = float(user_data.get('balance', 0.0))
    new_balance = old_balance + winnings
    
    # إضافة الأرباح للرصيد المباشر
    update_user_balance_safe(telegram_id, new_balance, winnings)

    update_goxe_economy_stats(bet_amount, winnings)
    delete_goxe_session(telegram_id)

    return jsonify({
        "success": True,
        "message": "تم سحب الأرباح وإضافتها لرصيدك بنجاح!",
        "winnings": winnings,
        "new_balance": new_balance
    }), 200

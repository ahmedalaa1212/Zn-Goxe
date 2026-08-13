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

goxe_bp = Blueprint('goxe', __name__, url_prefix='/api/games/goxe')

# قائمة المضاعفات للأدوار العشرة (تبدأ بـ 1.1x وتصل كحد أقصى إلى 5.0x في الدور العاشر)
FLOOR_MULTIPLIERS = [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00]

@goxe_bp.route('/config', methods=['GET', 'POST'])
def get_config():
    """جلب إعدادات اللعبة وحالة الجولة الحالية للمستخدم"""
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    config = get_goxe_config()
    session = get_active_goxe_session(telegram_id)
    
    return jsonify({
        "success": True,
        "min_bet": config.get('min_bet', 10.0),
        "max_bet": config.get('max_bet', 10000.0),
        "multipliers": FLOOR_MULTIPLIERS,
        "active_session": session
    }), 200

@goxe_bp.route('/start', methods=['POST'])
def start_game():
    """بدء جولة تسلق جديدة وحصم مبلغ الرهان"""
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    # التأكد من عدم وجود جولة قائمة بالفعل
    existing_session = get_active_goxe_session(telegram_id)
    if existing_session:
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

    # جلب بيانات المستخدم وفحص الرصيد
    user_data = database.get_user(telegram_id) or {}
    current_balance = float(user_data.get('balance', 0.0))

    if current_balance < bet_amount:
        return jsonify({"success": False, "error": "رصيدك الحالي غير كافٍ لفتح هذه الجولة"}), 400

    # خصم قيمة الرهان من حساب المستخدم
    new_balance = current_balance - bet_amount
    database.update_user_balance(telegram_id, new_balance)

    # فحص اقتصاد البوت لتحديد هل السيستم سيفرض الخسارة
    current_bot_profit_pct = get_bot_profit_percentage()
    threshold = float(config.get('force_loss_threshold', 59.0))
    manual_override = config.get('force_loss_override', False)

    # تفعيل وضع الخسارة الإجبارية إذا انخفض الربح عن 59%
    force_loss = (current_bot_profit_pct < threshold) or manual_override

    session_data = {
        'telegram_id': telegram_id,
        'bet_amount': bet_amount,
        'current_floor': 0, # لم يبدأ التسلق بعد
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
    """تحديد الباب المخفي والانتقال للدور التالي أو الانفجار"""
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
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

    # تحديد ما إذا كان الاختيار سينتهي بقنبلة أم كنز
    is_bomb = False

    if force_loss:
        # أمر الخسارة الفورية مفعل: الاختيار سيؤدي حتماً إلى قنبلة
        is_bomb = True
    else:
        # الوضع العادي: احتمالية ناتجة من السيرفر (1 باب قنبلة من 3 أبواب = 33.3% احتمالية خروج القنبلة)
        # مع تقليل نسبة النجاح تدريجياً مع ارتفاع الأدوار
        risk_factor = 0.33 + (next_floor * 0.03) # زيادة الخطر كلما صعدنا
        is_bomb = (random.random() < risk_factor)

    if is_bomb:
        # اللاعب خسر الجولة!
        delete_goxe_session(telegram_id)
        # تحديث إحصائيات الاقتصاد: البوت كسب الرهان كاملاً (المبلغ المدفوع كأرباح = 0)
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
        # نجح اللاعب في صعود الدور!
        session['current_floor'] = next_floor
        current_multiplier = FLOOR_MULTIPLIERS[next_floor - 1]
        current_winnings = bet_amount * current_multiplier

        # إذا وصل اللاعب للدور العاشر والأخير (5.0x): يتم السحب التلقائي فوراً!
        if next_floor == 10:
            delete_goxe_session(telegram_id)
            user_data = database.get_user(telegram_id) or {}
            old_balance = float(user_data.get('balance', 0.0))
            final_balance = old_balance + current_winnings
            database.update_user_balance(telegram_id, final_balance)

            # تحديث اقتصاد البوت
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

        # حفظ تقدم الجولة للدور التالي
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
    """سحب الأرباح الحالية وإنهاء الجولة"""
    is_post = (request.method == 'POST')
    success, telegram_id, _, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
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

    # إضافة الأرباح لرصيد المستخدم
    user_data = database.get_user(telegram_id) or {}
    old_balance = float(user_data.get('balance', 0.0))
    new_balance = old_balance + winnings
    database.update_user_balance(telegram_id, new_balance)

    # تحديث إحصائيات الاقتصاد في Firebase
    update_goxe_economy_stats(bet_amount, winnings)

    # إنهاء وحذف الجولة
    delete_goxe_session(telegram_id)

    return jsonify({
        "success": True,
        "message": "تم سحب الأرباح وإضافتها لرصيدك بنجاح!",
        "winnings": winnings,
        "new_balance": new_balance
    }), 200

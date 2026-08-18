from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
from .withdraw_db import (
    get_user_withdrawal_context,
    can_user_withdraw_today_utc,
    execute_withdrawal_transaction
)

withdraw_bp = Blueprint('withdraw_api', __name__)

# تحديد مستويات السحب بناءً على سعر الصرف (100,000 ZN = $1)
TIERS_CONFIG = [
    {"level": 1, "min_zn": 10, "max_zn": 100, "auto": True, "name": "المستوى الأول"},
    {"level": 2, "min_zn": 500, "max_zn": 1500, "auto": True, "name": "المستوى الثاني"},
    {"level": 3, "min_zn": 10000, "max_zn": 50000, "auto": True, "name": "المستوى الثالث"},
    {"level": 4, "min_zn": 100000, "max_zn": 200000, "auto": False, "name": "المستوى الرابع"},
    {"level": 5, "min_zn": 400000, "max_zn": 800000, "auto": False, "name": "المستوى الخامس"},
    {"level": 6, "min_zn": 1000000, "max_zn": None, "auto": False, "name": "المستوى المفتوح"}
]

def get_tier_info(withdraw_count: int) -> dict:
    idx = min(withdraw_count, len(TIERS_CONFIG) - 1)
    cfg = TIERS_CONFIG[idx]
    return {
        "withdraw_count": withdraw_count,
        "level": cfg["level"],
        "min_zn": cfg["min_zn"],
        "max_zn": cfg["max_zn"],
        "is_auto": cfg["auto"],
        "tier_name": cfg["name"]
    }

@withdraw_bp.route('/info', methods=['GET'])
def get_withdraw_info():
    user_id = request.args.get('user_id', type=int)
    header_id = request.headers.get('X-Telegram-User-Id')
    if header_id and str(header_id).isdigit():
        user_id = int(header_id)

    if not user_id:
        return jsonify({'success': False, 'error': 'معرف المستخدم غير متاح'}), 400

    ctx = get_user_withdrawal_context(user_id)
    withdraw_count = ctx.get('withdraw_count', 0)
    has_withdrawn_today = ctx.get('has_withdrawn_today', False)

    tier_info = get_tier_info(withdraw_count)
    tier_info['has_withdrawn_today'] = has_withdrawn_today

    # جلب سعر TON (افتراضي 6.0 دولار في حال عدم توفر موديل السعر)
    ton_price = 6.0
    try:
        from core.ton_price import get_ton_price
        ton_price = get_ton_price() or 6.0
    except Exception:
        pass

    return jsonify({
        'success': True,
        'tier_info': tier_info,
        'ton_price': ton_price
    })

@withdraw_bp.route('/request', methods=['POST'])
def process_withdraw_request():
    data = request.get_json() or {}
    user_id = data.get('user_id')
    header_id = request.headers.get('X-Telegram-User-Id')
    
    if header_id and str(header_id).isdigit():
        user_id = int(header_id)

    amount_zn = float(data.get('amount_zn', 0))
    address = str(data.get('wallet_address', '')).strip()

    if not user_id or amount_zn <= 0 or not address:
        return jsonify({'success': False, 'error': 'بيانات الإدخال غير مكتملة'}), 400

    # 1. التحقق من الحد اليومي بالتوقيت العالمي UTC
    if not can_user_withdraw_today_utc(user_id):
        return jsonify({'success': False, 'error': 'مسموح بسحبة واحدة فقط يومياً بتوقيت UTC'}), 400

    # 2. تحديد المستوى والقواعد
    ctx = get_user_withdrawal_context(user_id)
    tier = get_tier_info(ctx.get('withdraw_count', 0))

    if amount_zn < tier['min_zn']:
        return jsonify({'success': False, 'error': f"الحد الأدنى للسحب هو {tier['min_zn']} ZN"}), 400
    
    if tier['max_zn'] and amount_zn > tier['max_zn']:
        return jsonify({'success': False, 'error': f"الحد الأقصى للسحب هو {tier['max_zn']} ZN"}), 400

    # 3. حساب الرسوم والخصم
    fee_zn = amount_zn * 0.03
    net_zn = amount_zn - fee_zn
    usdt_value = net_zn / 100000.0

    # 4. تنفيذ الخصم والتسجيل في قاعدة البيانات والسجلات
    success, msg, new_balance = execute_withdrawal_transaction(
        user_id=user_id,
        amount_zn=amount_zn,
        fee_zn=fee_zn,
        net_zn=net_zn,
        usdt_value=usdt_value,
        wallet_address=address,
        is_auto=tier['is_auto']
    )

    if success:
        return jsonify({
            'success': True,
            'message': 'تم إرسال السحب بنجاح إلى محفظتك!' if tier['is_auto'] else 'تم إرسال طلب السحب بنجاح ومحالة للمراجعة من الأدمن.',
            'new_balance': new_balance,
            'is_auto': tier['is_auto']
        })
    else:
        return jsonify({'success': False, 'error': msg}), 400

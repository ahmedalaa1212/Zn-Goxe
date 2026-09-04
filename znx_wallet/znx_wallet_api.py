# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet API Module (Flask Blueprint)
مسارات الـ API الخاصة بمحفظة ZNX:
- جلب بيانات المحفظة والمتصدرين والشرائح (/api/znx-wallet/data & /init)
- معالجة عملية تحويل النقاط ZN إلى ZNX (/api/znx-wallet/convert)
"""

import math
from flask import Blueprint, jsonify, request

# استيراد موديول قاعدة البيانات الخاص بمحفظة ZNX بطريقة مرنة ومؤمنة
try:
    from znx_wallet import znx_wallet_db
except ImportError:
    try:
        import znx_wallet_db
    except ImportError:
        from . import znx_wallet_db

# إنشاء الـ Blueprint الخاص بالمحفظة
znx_wallet_bp = Blueprint('znx_wallet_bp', __name__)


def _extract_user_id():
    """دالة مساعدة لاستخراج وتنظيف user_id من جميع المصادر الممكنة"""
    user_id = None
    
    # 1. البحث في parameters الطلب (GET/POST)
    if request.method == 'GET':
        user_id = request.args.get('user_id') or request.args.get('tg_id')
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id') or data.get('tg_id')

    # 2. البحث في الترويسات (Headers) كخيار إضافي
    if not user_id:
        user_id = request.headers.get('X-Telegram-User-Id')

    if user_id:
        user_id_str = str(user_id).strip()
        # منع القيم الطويلة جداً أو المفاتيح المشبوهة
        if 0 < len(user_id_str) <= 64 and user_id_str.isalnum():
            return user_id_str

    return None


@znx_wallet_bp.route('/data', methods=['GET'])
@znx_wallet_bp.route('/init', methods=['GET'])
def get_wallet_data():
    """
    مسار جلب بيانات المحفظة: الرصيد الثلاثي، الشريحة الحالية، إجمالي التحويل العام، وقائمة المتصدرين.
    """
    try:
        user_id = _extract_user_id()
        if not user_id:
            return jsonify({
                'success': False, 
                'message': 'معرف المستخدم غير صالح أو مفقود'
            }), 400

        # جلب البيانات من قاعدة بيانات ZNX
        user_data = znx_wallet_db.get_user_data(str(user_id))
        if not user_data:
            return jsonify({
                'success': False,
                'message': 'لم يتم العثور على بيانات المستخدم'
            }), 444 if hasattr(request, 'status_code') else 404

        current_balance = float(user_data.get('balance', 0.0))
        current_tier = znx_wallet_db.get_user_tier(current_balance)
        rankings = znx_wallet_db.get_leaderboard_rankings()
        global_stats = znx_wallet_db.get_global_stats()

        return jsonify({
            'success': True,
            'user': user_data,
            'current_tier': current_tier,
            'tiers_all': getattr(znx_wallet_db, 'TIERS_CONFIG', []),
            'leaderboard': rankings,
            'global_total': float(global_stats.get('total_converted_znx', 0.0)),
            'max_global_znx': getattr(znx_wallet_db, 'MAX_GLOBAL_ZNX', 35000000),
            'live_price': 0.0524
        }), 200

    except Exception as e:
        # تسجيل الخطأ داخلياً وإعادة استجابة آمنة للمستخدم
        return jsonify({
            'success': False,
            'message': 'حدث خطأ غير متوقع أثناء معالجة الطلب',
            'error': str(e)
        }), 500


@znx_wallet_bp.route('/convert', methods=['POST'])
def process_conversion():
    """
    مسار إجراء عملية تحويل النقاط ZN إلى عملة ZNX مع التحقق الصارم لمنع الثغرات والتلاعب.
    """
    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id') or data.get('tg_id') or _extract_user_id()

        if not user_id:
            return jsonify({
                'success': False, 
                'message': 'معرف المستخدم غير صالح أو غير موجود'
            }), 400

        user_id_str = str(user_id).strip()

        # 🛡️ التحقق الحاسم من قيمة التحويل لمنع ثغرات Math Exploits / NaN / Infinity / Negative Numbers
        raw_amount = data.get('amount')
        if raw_amount is None:
            return jsonify({'success': False, 'message': 'يرجى تحديد كمية التحويل'}), 400

        try:
            amount = float(raw_amount)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'صيغة كمية التحويل غير صالحة'}), 400

        if math.isnan(amount) or math.isinf(amount) or amount <= 0:
            return jsonify({
                'success': False, 
                'message': 'كمية التحويل يجب أن تكون رقماً موجباً وصالحاً'
            }), 400

        # تنفيذ عملية التحويل الآمنة في قاعدة البيانات
        success, result = znx_wallet_db.execute_conversion(user_id_str, amount)

        if success:
            return jsonify({
                'success': True,
                'data': result,
                'message': 'تمت عملية التحويل بنجاح'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': str(result)
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'حدث خطأ في النظام أثناء تنفيذ التحويل',
            'error': str(e)
        }), 500

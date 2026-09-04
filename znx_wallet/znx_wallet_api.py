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
    """
    دالة مساعدة شاملة لاستخراج وتنظيف user_id من جميع المصادر الممكنة 
    (Query Parameters, JSON Body, Headers, InitData)
    """
    user_id = None
    
    # 1. البحث في parameters الطلب (GET) أو JSON Body (POST)
    if request.method == 'GET':
        user_id = request.args.get('user_id') or request.args.get('tg_id') or request.args.get('telegram_id')
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            user_id = data.get('user_id') or data.get('tg_id') or data.get('telegram_id')

    # 2. البحث في Query String الشاملة
    if not user_id:
        user_id = request.args.get('user_id') or request.args.get('tg_id') or request.args.get('telegram_id')

    # 3. البحث في الترويسات (Headers)
    if not user_id:
        user_id = request.headers.get('X-Telegram-User-Id')

    # 4. محاولة تحليل initData إن وُجدت
    if not user_id:
        init_data_str = (
            request.args.get('initData') or 
            request.args.get('init_data') or 
            request.headers.get('X-Telegram-Init-Data') or 
            request.headers.get('Authorization')
        )
        if init_data_str:
            try:
                from urllib.parse import parse_qs
                import json
                clean_init = str(init_data_str)
                if clean_init.startswith('Bearer '):
                    clean_init = clean_init[7:]
                parsed_params = parse_qs(clean_init)
                if 'user' in parsed_params:
                    user_data = json.loads(parsed_params['user'][0])
                    if isinstance(user_data, dict) and user_data.get('id'):
                        user_id = str(user_data['id'])
            except Exception:
                pass

    if user_id:
        user_id_str = str(user_id).strip()
        if user_id_str.lower() not in ("none", "null", "undefined", "false", "true", ""):
            if len(user_id_str) <= 64:
                return user_id_str

    return None


@znx_wallet_bp.route('/data', methods=['GET', 'POST', 'OPTIONS'])
@znx_wallet_bp.route('/init', methods=['GET', 'POST', 'OPTIONS'])
def get_wallet_data():
    """
    مسار جلب بيانات المحفظة: الرصيد الثلاثي، الشريحة الحالية، إجمالي التحويل العام، وقائمة المتصدرين.
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

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
            }), 404

        current_balance = float(user_data.get('balance', 0.0))
        current_tier = znx_wallet_db.get_user_tier(current_balance)
        
        # جلب قائمة المتصدرين ورتبة المستخدم
        lb_res = znx_wallet_db.get_leaderboard_data(limit=50, user_id=str(user_id))
        
        if isinstance(lb_res, dict):
            rankings = lb_res.get('leaderboard', [])
            my_rank = lb_res.get('my_rank', 'غير مصنف')
        else:
            rankings = lb_res if isinstance(lb_res, list) else []
            my_rank = 'غير مصنف'

        global_stats = znx_wallet_db.get_global_stats()

        return jsonify({
            'success': True,
            'user': user_data,
            'current_tier': current_tier,
            'tiers_all': getattr(znx_wallet_db, 'TIERS_CONFIG', []),
            'leaderboard': rankings,
            'my_rank': my_rank,
            'global_total': float(global_stats.get('total_converted_znx', 0.0)),
            'max_global_znx': getattr(znx_wallet_db, 'MAX_GLOBAL_ZNX', 35000000.0),
            'live_price': 0.0524
        }), 200

    except Exception as e:
        print(f"❌ Error in get_wallet_data API: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ غير متوقع أثناء معالجة الطلب',
            'error': str(e)
        }), 500


@znx_wallet_bp.route('/convert', methods=['POST', 'OPTIONS'])
def process_conversion():
    """
    مسار إجراء عملية تحويل النقاط ZN إلى عملة ZNX مع التحقق الصارم لمنع الثغرات والتلاعب.
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}

        user_id = data.get('user_id') or data.get('tg_id') or _extract_user_id()

        if not user_id:
            return jsonify({
                'success': False, 
                'message': 'معرف المستخدم غير صالح أو غير موجود'
            }), 400

        user_id_str = str(user_id).strip()

        # 🛡️ التحقق الحاسم من قيمة التحويل لمنع ثغرات Math Exploits / NaN / Infinity / Negative Numbers
        raw_amount = data.get('amount') if 'amount' in data else request.args.get('amount')
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
        print(f"❌ Error in process_conversion API: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ في النظام أثناء تنفيذ التحويل',
            'error': str(e)
        }), 500

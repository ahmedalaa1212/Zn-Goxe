from flask import Blueprint, jsonify, request, make_response
from .deposit_db import (
    get_active_deposit_packages,
    create_deposit_invoice,
    get_package_by_id,
    get_official_ton_wallet,
    credit_user_balance,
    verify_and_process_ton_boc
)

deposit_bp = Blueprint('deposit', __name__)

@deposit_bp.route('/packages', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def get_packages():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        packages = get_active_deposit_packages()
        official_wallet = get_official_ton_wallet()
        
        response = make_response(jsonify({
            'success': True,
            'packages': packages,
            'official_wallet': official_wallet
        }))
        
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as exc:
        print(f"❌ [deposit_api Error]: {exc}")
        return jsonify({
            'success': False,
            'error': f"فشل الاتصال بقاعدة البيانات: {str(exc)}"
        }), 500

@deposit_bp.route('/prepare_ton_pay', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/create_invoice', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def prepare_ton_pay():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or request.form or {}
        package_id = data.get('package_id')
        
        try:
            ton_price = float(data.get('ton_price', 1.30))
            if ton_price <= 0:
                ton_price = 1.30
        except (ValueError, TypeError):
            ton_price = 1.30

        user_id = request.headers.get('X-Telegram-User-Id') or data.get('user_id') or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        pkg = get_package_by_id(package_id) if package_id is not None else None
        
        if pkg and 'usdt_amount' in pkg:
            usdt_amount = float(pkg['usdt_amount'])
        else:
            try:
                usdt_amount = float(data.get('usdt_amount', 0.5))
            except (ValueError, TypeError):
                usdt_amount = 0.5

        ton_amount = round(usdt_amount / ton_price, 4)
        nano_ton = int(round(ton_amount * 1e9))

        wallet_address = get_official_ton_wallet()
        invoice = create_deposit_invoice(user_id, usdt_amount, ton_amount)
        
        payload_memo = invoice.get('memo', '')

        return jsonify({
            'success': True,
            'invoice_id': invoice.get('invoice_id', 0),
            'package_id': package_id,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'nano_ton': nano_ton,
            'memo': payload_memo,
            'payload_memo': payload_memo,
            'wallet_address': wallet_address
        })
    except Exception as exc:
        print(f"❌ [prepare_ton_pay Error]: {exc}")
        return jsonify({
            'success': False,
            'error': f"فشل تجهيز المعاملة: {str(exc)}"
        }), 500

@deposit_bp.route('/verify_and_apply', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/verify_and_apply_package', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/confirm_payment', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def verify_and_apply():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json(silent=True) or request.form or {}
        user_id = request.headers.get('X-Telegram-User-Id') or data.get('user_id') or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        boc = data.get('boc')
        memo = data.get('memo') or data.get('payload_memo')
        package_id = data.get('package_id')

        pkg = get_package_by_id(package_id) if package_id is not None else None
        if pkg and 'usdt_amount' in pkg:
            usdt_amount = float(pkg['usdt_amount'])
        else:
            try:
                usdt_amount = float(data.get('usdt_amount', 0.0))
            except (ValueError, TypeError):
                usdt_amount = 0.0

        if user_id <= 0:
            return jsonify({'success': False, 'error': 'معرف المستخدم غير معروف'}), 400

        if usdt_amount <= 0:
            return jsonify({'success': False, 'error': 'مبلغ الباقة غير صحيح'}), 400

        try:
            new_usd_balance = verify_and_process_ton_boc(user_id, usdt_amount, memo, boc)
            return jsonify({
                'success': True,
                'message': 'تمت عملية الدفع بنجاح وزيادة الرصيد!',
                'new_balance': new_usd_balance,
                'usd_balance': new_usd_balance
            })
        except ValueError as val_err:
            return jsonify({
                'success': False,
                'error': str(val_err)
            }), 400
        except Exception as proc_err:
            err_msg = str(proc_err)
            if "سابقاً" in err_msg or "used" in err_msg.lower():
                return jsonify({'success': False, 'error': err_msg}), 400
            raise proc_err

    except Exception as exc:
        print(f"❌ [verify_and_apply Error]: {exc}")
        return jsonify({'success': False, 'error': f"خطأ في معالجة الشحن: {str(exc)}"}), 500

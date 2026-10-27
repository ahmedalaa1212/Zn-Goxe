# -*- coding: utf-8 -*-
import time
import json
import base64
import urllib.request
from flask import Blueprint, jsonify, request, make_response

from core.security import get_authenticated_user
try:
    from core.ton_price import get_live_ton_price as core_fetch_ton_price
except ImportError:
    core_fetch_ton_price = None

from .deposit_db import (
    get_active_deposit_packages,
    create_deposit_invoice,
    update_deposit_invoice_status,
    get_package_by_id,
    get_deposit_invoice_by_memo,
    get_official_ton_wallet,
    verify_and_process_ton_boc,
    get_user_bound_wallet,
    save_user_bound_wallet,
    clear_user_bound_wallet,
)

deposit_bp = Blueprint('deposit', __name__)

SAFETY_MARGIN_RATIO = 0.03  # 3%

_ton_price_cache = {
    'price': 1.4500,
    'timestamp': 0
}


def _no_cache_json(payload, status_code=200):
    response = make_response(jsonify(payload), status_code)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def encode_ton_comment_boc_crc32c(comment_text: str) -> str:
    """توليد خلية BOC قياسية مدعومة بتدقيق CRC32C متوافقة مع كافة محافظ TON لتمرير الـ Memo"""
    if not comment_text:
        return ""
    try:
        text_bytes = str(comment_text).encode("utf-8")[:115]
        data_bytes = b"\x00\x00\x00\x00" + text_bytes
        cell_bytes = bytes([0x00, len(data_bytes) * 2]) + data_bytes
        header = bytes([
            0xB5, 0xEE, 0x9C, 0x72,
            0x41, 0x01, 0x01, 0x01, 0x00,
            len(cell_bytes), 0x00
        ])
        boc_no_crc = header + cell_bytes
        crc = 0xFFFFFFFF
        for b in boc_no_crc:
            crc ^= b
            for _ in range(8):
                crc = ((crc >> 1) ^ 0x82F63B78) if (crc & 1) else (crc >> 1)
        crc = (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF
        final_boc = boc_no_crc + crc.to_bytes(4, byteorder="little")
        return base64.b64encode(final_boc).decode("ascii")
    except Exception:
        return ""


def get_live_ton_price():
    """جلب سعر عملة TON الحقيقي واللحظي بالدولار بسرعة عالية عبر core.ton_price مع كاش ذكي"""
    global _ton_price_cache
    now = time.time()

    if now - _ton_price_cache['timestamp'] < 20 and _ton_price_cache['price'] > 0:
        return _ton_price_cache['price']

    if callable(core_fetch_ton_price):
        try:
            live_p = float(core_fetch_ton_price() or 0.0)
            if live_p > 0:
                _ton_price_cache['price'] = round(live_p, 4)
                _ton_price_cache['timestamp'] = now
                return _ton_price_cache['price']
        except Exception:
            pass

    sources = [
        ("https://tonapi.io/v2/rates?tokens=ton&currencies=usd", lambda d: float(d['rates']['TON']['prices']['USD'])),
        ("https://www.okx.com/api/v5/market/ticker?instId=TON-USDT", lambda d: float(d['data'][0]['last'])),
        ("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", lambda d: float(d['the-open-network']['usd'])),
    ]

    headers = {'User-Agent': 'Mozilla/5.0'}
    for url, parser in sources:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    price = parser(data)
                    if price > 0:
                        _ton_price_cache['price'] = round(price, 4)
                        _ton_price_cache['timestamp'] = now
                        return _ton_price_cache['price']
        except Exception:
            continue

    return _ton_price_cache['price']


def get_effective_ton_price(live_price=None):
    """حساب سعر TON الآمن للإيداع بعد خصم حد الأمان (3%)"""
    if live_price is None or live_price <= 0:
        live_price = get_live_ton_price()

    effective_price = live_price / (1.0 + SAFETY_MARGIN_RATIO)
    return round(effective_price, 4)


@deposit_bp.route('/packages', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def get_packages():
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        auth_ok, user_id, _, _ = get_authenticated_user(
            request, is_post=(request.method == 'POST'), enforce_device_check=False
        )

        packages = get_active_deposit_packages()
        official_wallet = get_official_ton_wallet()
        live_ton_price = get_live_ton_price()
        effective_price = get_effective_ton_price(live_ton_price)

        bound_wallet_info = {"wallet_address": "", "wallet_name": ""}
        if auth_ok and user_id:
            bound_wallet_info = get_user_bound_wallet(user_id)

        return _no_cache_json({
            'success': True,
            'packages': packages,
            'official_wallet': official_wallet,
            'ton_price': live_ton_price,
            'effective_ton_price': effective_price,
            'safety_margin_percent': 3,
            'bound_wallet': bound_wallet_info.get('wallet_address', ''),
            'bound_wallet_name': bound_wallet_info.get('wallet_name', ''),
        })
    except Exception as exc:
        print(f"❌ [deposit_api Error]: {exc}")
        return _no_cache_json({
            'success': False,
            'error': f"فشل الاتصال بقاعدة البيانات: {str(exc)}"
        }, 500)


@deposit_bp.route('/bind_wallet', methods=['POST', 'OPTIONS'], strict_slashes=False)
def bind_wallet():
    """حفظ المحفظة المربوطة في Supabase لتظل مربوطة بشكل دائم"""
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        success, user_id, _, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json(silent=True) or {}
        wallet_address = str(data.get('wallet_address') or '').strip()
        wallet_name = str(data.get('wallet_name') or 'محفظة TON').strip()

        if not wallet_address:
            return _no_cache_json({'success': False, 'error': 'عنوان المحفظة مطلوب'}, 400)

        save_user_bound_wallet(user_id, wallet_address, wallet_name)
        return _no_cache_json({
            'success': True,
            'bound_wallet': wallet_address,
            'bound_wallet_name': wallet_name
        })
    except Exception as exc:
        return _no_cache_json({'success': False, 'error': str(exc)}, 500)


@deposit_bp.route('/unbind_wallet', methods=['POST', 'OPTIONS'], strict_slashes=False)
def unbind_wallet():
    """إلغاء ربط المحفظة من Supabase عندما يطلب المستخدم ذلك يدوياً فقط"""
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        success, user_id, _, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        clear_user_bound_wallet(user_id)
        return _no_cache_json({'success': True})
    except Exception as exc:
        return _no_cache_json({'success': False, 'error': str(exc)}, 500)


@deposit_bp.route('/prepare_ton_pay', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/create_invoice', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def prepare_ton_pay():
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        success, user_id, _, error_res = get_authenticated_user(
            request, is_post=(request.method == 'POST')
        )
        if not success:
            return error_res

        wallet_address = get_official_ton_wallet()
        if not wallet_address:
            return _no_cache_json({
                'success': False,
                'error': 'لم يتم ضبط عنوان محفظة الاستلام (TON_WALLET_ADDRESS) في متغيرات البيئة!'
            }, 400)

        data = request.get_json(silent=True) or request.form or {}
        package_id = data.get('package_id')
        sender_wallet = str(data.get('sender_wallet') or data.get('wallet_address') or '').strip()

        pkg = get_package_by_id(package_id) if package_id is not None else None
        if not pkg or 'usdt_amount' not in pkg:
            return _no_cache_json({
                'success': False,
                'error': 'باقة الشحن المحددة غير صالحة أو غير متاحة'
            }, 400)

        usdt_amount = float(pkg['usdt_amount'])
        live_price = get_live_ton_price()
        effective_price = get_effective_ton_price(live_price)

        ton_amount = round(usdt_amount / effective_price, 4)
        nano_ton = int(round(ton_amount * 1e9))

        invoice = create_deposit_invoice(user_id, usdt_amount, ton_amount, sender_wallet=sender_wallet)
        payload_memo = invoice.get('memo', '')
        payload_boc = encode_ton_comment_boc_crc32c(payload_memo)

        return _no_cache_json({
            'success': True,
            'invoice_id': invoice.get('invoice_id', 0),
            'package_id': pkg['id'],
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'ton_price': live_price,
            'effective_ton_price': effective_price,
            'nano_ton': nano_ton,
            'memo': payload_memo,
            'payload_memo': payload_memo,
            'payload_boc': payload_boc or None,
            'wallet_address': wallet_address
        })
    except Exception as exc:
        print(f"❌ [prepare_ton_pay Error]: {exc}")
        return _no_cache_json({
            'success': False,
            'error': f"فشل تجهيز المعاملة: {str(exc)}"
        }, 500)


@deposit_bp.route('/cancel_invoice', methods=['POST', 'OPTIONS'], strict_slashes=False)
def cancel_invoice():
    """إلغاء الفاتورة المبدئية الخاصة بالمستخدم الموثق فقط"""
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        success, user_id, _, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        data = request.get_json(silent=True) or request.form or {}
        memo = data.get('memo') or data.get('payload_memo')
        status = data.get('status', 'cancelled')
        reason = data.get('reason')
        delete_if_cancelled = bool(data.get('delete_if_cancelled', True))

        if memo:
            update_deposit_invoice_status(
                memo,
                status=status,
                failure_reason=reason,
                delete_if_cancelled=delete_if_cancelled,
                user_id=user_id,
            )

        return _no_cache_json({'success': True})
    except Exception as exc:
        return _no_cache_json({'success': False, 'error': str(exc)}, 500)


@deposit_bp.route('/verify_and_apply', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/verify_and_apply_package', methods=['POST', 'OPTIONS'], strict_slashes=False)
@deposit_bp.route('/confirm_payment', methods=['GET', 'POST', 'OPTIONS'], strict_slashes=False)
def verify_and_apply():
    if request.method == 'OPTIONS':
        return _no_cache_json({'success': True}, 200)

    try:
        success, user_id, _, error_res = get_authenticated_user(
            request, is_post=(request.method == 'POST')
        )
        if not success:
            return error_res

        data = request.get_json(silent=True) or request.form or {}
        boc = str(data.get('boc') or '').strip()
        memo = str(data.get('memo') or data.get('payload_memo') or '').strip()
        sender_wallet = str(data.get('sender_wallet') or data.get('wallet_address') or '').strip()

        if not memo or not boc:
            return _no_cache_json({'success': False, 'error': 'بيانات تأكيد الفاتورة أو المعاملة غير مكتملة'}, 400)

        invoice_row = get_deposit_invoice_by_memo(memo, user_id=user_id)
        if not invoice_row:
            return _no_cache_json({'success': False, 'error': 'الفاتورة غير موجودة أو لا تخص حسابك'}, 400)

        usdt_amount = float(invoice_row.get('usdt_amount') or 0.0)
        ton_amount = float(invoice_row.get('ton_amount') or 0.0)

        if usdt_amount <= 0 or ton_amount <= 0:
            return _no_cache_json({'success': False, 'error': 'بيانات الفاتورة غير صالحة'}, 400)

        try:
            new_usd_balance = verify_and_process_ton_boc(
                user_id=user_id,
                usdt_amount=usdt_amount,
                memo=memo,
                boc=boc,
                ton_amount=ton_amount,
                sender_wallet=sender_wallet
            )
            return _no_cache_json({
                'success': True,
                'deposited_amount': usdt_amount,
                'message': 'تمت عملية الدفع بنجاح وزيادة الرصيد!',
                'new_balance': new_usd_balance,
                'usd_balance': new_usd_balance
            })
        except ValueError as val_err:
            return _no_cache_json({'success': False, 'error': str(val_err)}, 400)
        except Exception as proc_err:
            err_msg = str(proc_err)
            if "سابقاً" in err_msg || "مسبقاً" in err_msg || "used" in err_msg.lower():
                return _no_cache_json({'success': False, 'error': err_msg}, 400)
            raise proc_err

    except Exception as exc:
        print(f"❌ [verify_and_apply Error]: {exc}")
        return _no_cache_json({'success': False, 'error': f"خطأ في معالجة الشحن: {str(exc)}"}, 500)

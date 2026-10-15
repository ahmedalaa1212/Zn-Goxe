import os
import sys
import uuid
import time
import hashlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# استيراد الوظائف من الملف الرئيسي الخاص بـ Supabase
from wallet.wallet_db import (
    get_supabase_deposit_packages,
    create_supabase_deposit_invoice,
    process_supabase_deposit
)

OFFICIAL_TON_WALLET = 'UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc'

def get_official_ton_wallet():
    # يمكن مستقبلاً جلبها من جدول settings في Supabase
    env_wallet = os.getenv('PROJECT_WALLET') or os.getenv('OFFICIAL_TON_WALLET') or os.getenv('TON_WALLET')
    if env_wallet and str(env_wallet).strip():
        return str(env_wallet).strip()
    return OFFICIAL_TON_WALLET

def get_active_deposit_packages():
    """جلب الباقات مباشرة من Supabase"""
    return get_supabase_deposit_packages()

def get_package_by_id(pkg_id):
    if pkg_id is None:
        return None
    packages = get_active_deposit_packages()
    for pkg in packages:
        if str(pkg.get('id')) == str(pkg_id):
            return pkg
    return None

def create_deposit_invoice(user_id: int, usdt_amount: float, ton_amount: float) -> dict:
    memo = f"DEP-{user_id}-{uuid.uuid4().hex[:6].upper()}"
    invoice_id = create_supabase_deposit_invoice(user_id, usdt_amount, ton_amount, memo)
    return {
        'invoice_id': invoice_id,
        'user_id': user_id,
        'usdt_amount': usdt_amount,
        'ton_amount': ton_amount,
        'memo': memo
    }

def verify_and_process_ton_boc(user_id: int, usdt_amount: float, memo: str, boc: str) -> float:
    if not user_id or usdt_amount <= 0:
        raise ValueError("بيانات المستخدم أو قيمة الباقة غير صحيحة")

    tx_identifier = boc or memo or str(uuid.uuid4())
    tx_hash = hashlib.sha256(tx_identifier.encode('utf-8')).hexdigest()

    # تنفيذ العملية في Supabase
    new_balance = process_supabase_deposit(user_id, usdt_amount, memo, boc, tx_hash)
    return new_balance

def credit_user_balance(user_id: int, usdt_amount: float) -> float:
    if not user_id:
        return 0.0
    return verify_and_process_ton_boc(user_id, usdt_amount, f"MANUAL-{time.time()}", f"BOC-MANUAL-{uuid.uuid4().hex}")

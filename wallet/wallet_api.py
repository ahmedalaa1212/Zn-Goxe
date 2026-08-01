# wallet/wallet_api.py
import datetime
import hashlib
from flask import Blueprint, jsonify, request
from google.cloud import firestore

from database import db, is_user_banned
from core.security import get_authenticated_user

wallet_bp = Blueprint('wallet', __name__)

DEPOSIT_FEE_PERCENT = 0.03
MIN_DEPOSIT_USD = 1.00
MIN_CONVERT_ZN = 1000000

@wallet_bp.route('/', methods=['GET', 'POST'])
def wallet_index():
    return jsonify({"success": True, "message": "Wallet API is Active & Secured!"}), 200

# ==========================================
# 📜 1. جلب سجل المعاملات (قراءة فقط وبقائم محددة)
# ==========================================
@wallet_bp.route('/get_history', methods=['GET', 'POST'])
def get_history():
    is_post = (request.method == 'POST')
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    try:
        user_id_str = str(user_id).strip()
        user_ids = [user_id_str]
        try:
            num_id = int(user_id_str)
            if num_id not in user_ids: 
                user_ids.append(num_id)
        except (ValueError, TypeError): 
            pass

        history = []

        # جلب أحدث 10 عمليات فقط لمنع استهلاك قراءات الفايربيس
        for collection_name, type_label in [('withdrawals', 'withdraw'), ('deposits', 'deposit'), ('conversions', 'convert')]:
            try:
                docs = db.collection(collection_name).where('user_id', 'in', user_ids).limit(10).get()
                for doc in docs:
                    d = doc.to_dict() or {}
                    d['type'] = d.get('type', type_label)
                    d['id'] = doc.id
                    history.append(d)
            except Exception: 
                pass

        def safe_date_key(item):
            val = item.get('created_at') or item.get('timestamp') or item.get('date') or ''
            return val.isoformat() if hasattr(val, 'isoformat') else str(val)

        history.sort(key=safe_date_key, reverse=True)

        clean_history = []
        for item in history[:20]:
            clean_item = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in item.items()}
            # تقريب قيم المبلغ مسبقاً قبل إرسالها للفرونت إند
            if 'amount_usd' in clean_item and clean_item['amount_usd'] is not None:
                clean_item['amount_usd'] = round(float(clean_item['amount_usd']), 2)
            clean_history.append(clean_item)

        return jsonify({"success": True, "history": clean_history}), 200

    except Exception as e:
        print(f"[Wallet API] Error fetching history: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب سجل المعاملات"}), 200

# ==========================================
# 🔄 2. تحويل النقاط ZN إلى USD (معاملة معزولة ومباشرة)
# ==========================================
@wallet_bp.route('/wallet_convert', methods=['POST'])
def wallet_convert():
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
        if amount < MIN_CONVERT_ZN or amount <= 0 or not float(amount).is_integer():
            return jsonify({
                "success": False, 
                "error": f"الحد الأدنى لتحويل ZN هو {MIN_CONVERT_ZN:,} نقطة أعداد صحيحة."
            }), 200
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "كمية نقاط غير صالحة"}), 200
        
    usd_gained = round(amount / 1000000.0, 2)
    user_id_str = str(user_id).strip()
    
    transaction = db.transaction()
    user_ref = db.collection('users').document(user_id_str)
    conversion_ref = db.collection('conversions').document()
    
    @firestore.transactional
    def secure_convert_tx(tx, u_ref, c_ref):
        snapshot = u_ref.get(transaction=tx)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict() or {}
        current_balance = float(user_data.get('balance', 0))
        current_usd = float(user_data.get('usd_balance', 0))
        
        if current_balance < amount:
            raise Exception("رصيد النقاط غير كافٍ لإتمام التحويل")
            
        new_balance = round(current_balance - amount, 2)
        new_usd = round(current_usd + usd_gained, 2)
        
        tx.update(u_ref, {
            'balance': new_balance,
            'usd_balance': new_usd
        })
        
        tx.set(c_ref, {
            'user_id': user_id_str,
            'amount_zn': amount,
            'amount_usd': usd_gained,
            'type': 'convert',
            'status': 'completed',
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        return usd_gained, new_usd, new_balance
        
    try:
        gained, new_usd, new_balance = secure_convert_tx(transaction, user_ref, conversion_ref)
        return jsonify({
            "success": True, 
            "usd_gained": gained, 
            "new_usd_balance": new_usd,
            "new_balance": new_balance,
            "message": "تم تحويل النقاط بنجاح!"
        }), 200
    except Exception as e:
        print(f"[Wallet API] Conversion Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 200

# ==========================================
# 📤 3. طلب سحب الأرباح (خصم لحظي وتحديت مباشر)
# ==========================================
@wallet_bp.route('/wallet_withdraw', methods=['POST'])
def wallet_withdraw():
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    req = request.get_json(silent=True) or {}
    try:
        amount = round(float(req.get('amount', 0)), 2)
        if amount <= 0:
            return jsonify({"success": False, "error": "مبلغ سحب غير صالح"}), 200
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مبلغ سحب غير صالح"}), 200
        
    wallet_address = str(req.get('walletAddress', '')).strip()
    if not wallet_address or len(wallet_address) < 20:
        return jsonify({"success": False, "error": "عنوان المحفظة مفقود أو غير صحيح"}), 200
        
    user_id_str = str(user_id).strip()
    transaction = db.transaction()
    user_ref = db.collection('users').document(user_id_str)
    
    @firestore.transactional
    def secure_withdraw_tx(tx, u_ref):
        snapshot = u_ref.get(transaction=tx)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict() or {}
        current_usd = float(user_data.get('usd_balance', 0))
        
        if current_usd < amount:
            raise Exception("رصيد الـ USD غير كافٍ للسحب")
            
        new_usd = round(current_usd - amount, 2)
        tx.update(u_ref, {'usd_balance': new_usd})
        
        withdraw_ref = db.collection('withdrawals').document()
        tx.set(withdraw_ref, {
            'user_id': user_id_str,
            'amount_usd': amount,
            'wallet_address': wallet_address,
            'type': 'withdraw',
            'status': 'pending',
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        return new_usd
        
    try:
        new_usd = secure_withdraw_tx(transaction, user_ref)
        return jsonify({
            "success": True, 
            "new_usd_balance": new_usd,
            "message": "تم إرسال طلب السحب بنجاح!"
        }), 200
    except Exception as e:
        print(f"[Wallet API] Withdraw Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 200

# ==========================================
# 📥 4. تأكيد الإيداع ورصيد المستخدم (Anti-Replay Protection)
# ==========================================
@wallet_bp.route('/wallet_deposit_report', methods=['POST'])
def wallet_deposit_report():
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    req = request.get_json(silent=True) or {}
    try:
        gross_usd = round(float(req.get('usdAmount', 0)), 2)
        ton_amount = float(req.get('tonAmount', 0))
        
        if gross_usd < MIN_DEPOSIT_USD:
            return jsonify({
                "success": False, 
                "error": f"الحد الأدنى للإيداع هو ${MIN_DEPOSIT_USD:.2f}"
            }), 200
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مبلغ إيداع غير صالح"}), 200
        
    boc = req.get('boc')
    if not boc:
        return jsonify({"success": False, "error": "رمز إثبات المعاملة (BOC) مفقود"}), 200

    fee_usd = round(gross_usd * DEPOSIT_FEE_PERCENT, 2)
    net_usd = round(gross_usd - fee_usd, 2)

    tx_hash = hashlib.sha256(str(boc).encode('utf-8')).hexdigest()
    deposit_ref = db.collection('deposits').document(tx_hash)
    
    user_id_str = str(user_id).strip()
    transaction = db.transaction()
    user_ref = db.collection('users').document(user_id_str)
    
    @firestore.transactional
    def secure_deposit_tx(tx, u_ref, d_ref):
        deposit_snap = d_ref.get(transaction=tx)
        if deposit_snap.exists:
            raise Exception("تم تسجيل هذه المعاملة مسبقاً وتمرير الرصيد!")

        snapshot = u_ref.get(transaction=tx)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict() or {}
        current_usd = float(user_data.get('usd_balance', 0))
        new_usd = round(current_usd + net_usd, 2)
        
        tx.update(u_ref, {'usd_balance': new_usd})
        
        tx.set(d_ref, {
            'user_id': user_id_str,
            'gross_amount_usd': gross_usd,
            'amount_usd': net_usd,
            'fee_usd': fee_usd,
            'amount_ton': ton_amount,
            'tx_hash': tx_hash,
            'type': 'deposit',
            'status': 'completed',
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        return new_usd
        
    try:
        new_usd = secure_deposit_tx(transaction, user_ref, deposit_ref)
        return jsonify({
            "success": True, 
            "new_usd_balance": new_usd,
            "net_usd_credited": net_usd,
            "message": "تم الإيداع وتسجيل الرصيد بنجاح!"
        }), 200
    except Exception as e:
        print(f"[Wallet API] Deposit Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 200

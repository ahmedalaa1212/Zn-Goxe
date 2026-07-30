import datetime
import hashlib
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from database import db, is_user_banned
from google.cloud import firestore

wallet_bp = Blueprint('wallet', __name__)

# الثوابت المعتمدة للعمليات المالية
DEPOSIT_FEE_PERCENT = 0.03  # خصم 3% رسوم إيداع
MIN_DEPOSIT_USD = 1.00      # الحد الأدنى للإيداع
MIN_CONVERT_ZN = 1000000    # الحد الأدنى لتحويل ZN (1 مليون)

@wallet_bp.route('/', methods=['GET', 'POST'])
def wallet_index():
    return jsonify({"success": True, "message": "Wallet API is Secure and Active!"}), 200

# -------------------------------------------------------------------------
# 1. جلب سجل المعاملات (السحب، الإيداع، التحويل، والحركات العامة)
# -------------------------------------------------------------------------
@wallet_bp.route('/get_history', methods=['GET', 'POST'])
def get_history():
    is_post = (request.method == 'POST')
    is_auth, user_id, err = get_authenticated_user(request, is_post=is_post)
    if not is_auth: 
        return err

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 403
    
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

        # استعلام السحوبات (withdrawals)
        try:
            w_docs = db.collection('withdrawals').where('user_id', 'in', user_ids).limit(20).get()
            for doc in w_docs:
                d = doc.to_dict() or {}
                d['type'] = d.get('type', 'withdraw')
                d['id'] = doc.id
                history.append(d)
        except Exception as e:
            print(f"[Wallet API] Warning fetching withdrawals: {e}")

        # استعلام الإيداعات (deposits)
        try:
            d_docs = db.collection('deposits').where('user_id', 'in', user_ids).limit(20).get()
            for doc in d_docs:
                d = doc.to_dict() or {}
                d['type'] = d.get('type', 'deposit')
                d['id'] = doc.id
                history.append(d)
        except Exception as e:
            print(f"[Wallet API] Warning fetching deposits: {e}")

        # استعلام التحويلات (conversions)
        try:
            c_docs = db.collection('conversions').where('user_id', 'in', user_ids).limit(20).get()
            for doc in c_docs:
                d = doc.to_dict() or {}
                d['type'] = d.get('type', 'convert')
                d['id'] = doc.id
                history.append(d)
        except Exception as e:
            print(f"[Wallet API] Warning fetching conversions: {e}")

        # استعلام المعاملات العامة (transactions)
        try:
            t_docs = db.collection('transactions').where('tg_id', 'in', user_ids).limit(20).get()
            for doc in t_docs:
                d = doc.to_dict() or {}
                d['id'] = doc.id
                if not any(item.get('id') == doc.id for item in history):
                    history.append(d)
        except Exception as e:
            print(f"[Wallet API] Warning fetching general transactions: {e}")

        # دالة ترتيب واستخراج التاريخ بأمان
        def safe_date_key(item):
            val = item.get('created_at') or item.get('timestamp') or item.get('date') or ''
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return str(val)

        history.sort(key=safe_date_key, reverse=True)

        # تنظيف الكائنات للـ JSON
        clean_history = []
        for item in history[:30]:
            clean_item = {}
            for k, v in item.items():
                if hasattr(v, 'isoformat'):
                    clean_item[k] = v.isoformat()
                else:
                    clean_item[k] = v
            clean_history.append(clean_item)

        return jsonify({"success": True, "history": clean_history}), 200

    except Exception as e:
        print(f"[Wallet API] Error fetching history: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب السجلات"}), 500

# -------------------------------------------------------------------------
# 2. تحويل نقاط ZN إلى USD
# -------------------------------------------------------------------------
@wallet_bp.route('/wallet_convert', methods=['POST'])
def wallet_convert():
    is_auth, user_id, err = get_authenticated_user(request, is_post=True)
    if not is_auth: 
        return err

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 403
    
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
        if amount < MIN_CONVERT_ZN or amount <= 0:
            return jsonify({
                "success": False, 
                "error": f"الحد الأدنى لتحويل ZN هو {MIN_CONVERT_ZN:,} نقطة."
            }), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "كمية نقاط غير صالحة"}), 400
        
    usd_gained = round(amount / 1000000.0, 5)
    user_id_str = str(user_id).strip()
    
    transaction = db.transaction()
    user_ref = db.collection('users').document(user_id_str)
    conversion_ref = db.collection('conversions').document()
    
    @firestore.transactional
    def secure_convert_tx(transaction, user_ref, conversion_ref):
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود في قاعدة البيانات")
            
        user_data = snapshot.to_dict() or {}
        current_balance = float(user_data.get('balance', 0))
        current_usd = float(user_data.get('usd_balance', 0))
        
        if current_balance < amount:
            raise Exception("رصيد النقاط غير كافٍ لإتمام التحويل")
            
        new_balance = round(current_balance - amount, 2)
        new_usd = round(current_usd + usd_gained, 5)
        
        transaction.update(user_ref, {
            'balance': new_balance,
            'usd_balance': new_usd
        })
        
        transaction.set(conversion_ref, {
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
        return jsonify({"success": False, "error": str(e)}), 400

# -------------------------------------------------------------------------
# 3. تقديم طلب سحب أرباح
# -------------------------------------------------------------------------
@wallet_bp.route('/wallet_withdraw', methods=['POST'])
def wallet_withdraw():
    is_auth, user_id, err = get_authenticated_user(request, is_post=True)
    if not is_auth: 
        return err

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 403
    
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
        if amount <= 0:
            return jsonify({"success": False, "error": "مبلغ سحب غير صالح"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مبلغ سحب غير صالح"}), 400
        
    wallet_address = str(req.get('walletAddress', '')).strip()
    if not wallet_address:
        return jsonify({"success": False, "error": "عنوان المحفظة مفقود"}), 400
        
    user_id_str = str(user_id).strip()
    transaction = db.transaction()
    user_ref = db.collection('users').document(user_id_str)
    
    @firestore.transactional
    def secure_withdraw_tx(transaction, user_ref):
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict() or {}
        current_usd = float(user_data.get('usd_balance', 0))
        
        if current_usd < amount:
            raise Exception("رصيد الـ USD غير كافٍ للسحب")
            
        new_usd = round(current_usd - amount, 5)
        transaction.update(user_ref, {
            'usd_balance': new_usd
        })
        
        withdraw_ref = db.collection('withdrawals').document()
        transaction.set(withdraw_ref, {
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
            "message": "تم إرسال طلب السحب بنجاح"
        }), 200
    except Exception as e:
        print(f"[Wallet API] Withdraw Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 400

# -------------------------------------------------------------------------
# 4. تسجيل إيداع ناجح
# -------------------------------------------------------------------------
@wallet_bp.route('/wallet_deposit_report', methods=['POST'])
def wallet_deposit_report():
    is_auth, user_id, err = get_authenticated_user(request, is_post=True)
    if not is_auth: 
        return err

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 403
    
    req = request.get_json(silent=True) or {}
    try:
        gross_usd = float(req.get('usdAmount', 0))
        ton_amount = float(req.get('tonAmount', 0))
        
        if gross_usd < MIN_DEPOSIT_USD:
            return jsonify({
                "success": False, 
                "error": f"الحد الأدنى للإيداع هو ${MIN_DEPOSIT_USD:.2f}"
            }), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مبلغ إيداع غير صالح"}), 400
        
    boc = req.get('boc')
    if not boc:
        return jsonify({"success": False, "error": "رمز إثبات المعاملة (BOC) مفقود"}), 400

    fee_usd = round(gross_usd * DEPOSIT_FEE_PERCENT, 4)
    net_usd = round(gross_usd - fee_usd, 4)

    tx_hash = hashlib.sha256(str(boc).encode('utf-8')).hexdigest()
    deposit_ref = db.collection('deposits').document(tx_hash)
    
    user_id_str = str(user_id).strip()
    transaction = db.transaction()
    user_ref = db.collection('users').document(user_id_str)
    
    @firestore.transactional
    def secure_deposit_tx(transaction, user_ref):
        deposit_snap = deposit_ref.get(transaction=transaction)
        if deposit_snap.exists:
            raise Exception("تم تسجيل هذه المعاملة مسبقاً")

        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict() or {}
        current_usd = float(user_data.get('usd_balance', 0))
        new_usd = round(current_usd + net_usd, 5)
        
        transaction.update(user_ref, {
            'usd_balance': new_usd
        })
        
        transaction.set(deposit_ref, {
            'user_id': user_id_str,
            'gross_amount_usd': gross_usd,
            'amount_usd': net_usd,
            'fee_usd': fee_usd,
            'amount_ton': ton_amount,
            'boc': boc,
            'type': 'deposit',
            'status': 'completed',
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        return new_usd
        
    try:
        new_usd = secure_deposit_tx(transaction, user_ref)
        return jsonify({
            "success": True, 
            "new_usd_balance": new_usd,
            "net_usd_credited": net_usd,
            "message": "تم الإيداع وتسجيل الرصيد بنجاح!"
        }), 200
    except Exception as e:
        print(f"[Wallet API] Deposit Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 400

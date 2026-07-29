# wallet/wallet_api.py
import datetime
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from database import db, is_user_banned
from google.cloud import firestore

wallet_bp = Blueprint('wallet', __name__)

@wallet_bp.route('/', methods=['GET', 'POST'])
def wallet_index():
    return jsonify({"success": True, "message": "Wallet API is Secure and Active!"}), 200

# 1. استرجاع سجل السحوبات والإيداعات
@wallet_bp.route('/get_history', methods=['GET'])
def get_history():
    is_auth, user_id, err = get_authenticated_user(request)
    if not is_auth: return err
    
    try:
        withdrawals_query = db.collection('withdrawals').where('user_id', '==', str(user_id)).limit(15).get()
        deposits_query = db.collection('deposits').where('user_id', '==', str(user_id)).limit(15).get()
        
        history = []
        for doc in withdrawals_query:
            d = doc.to_dict()
            d['type'] = 'withdraw'
            history.append(d)
            
        for doc in deposits_query:
            d = doc.to_dict()
            d['type'] = 'deposit'
            history.append(d)
            
        history.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return jsonify({"success": True, "history": history[:30]}), 200
    except Exception as e:
        print(f"Error fetching history: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب السجلات"}), 500

# 2. تحويل النقاط ZN إلى USD (معاملة محمية Transaction)
@wallet_bp.route('/wallet_convert', methods=['POST'])
def wallet_convert():
    is_auth, user_id, err = get_authenticated_user(request, is_post=True)
    if not is_auth: return err
    
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
        if amount < 1000000 or amount <= 0:
            return jsonify({"success": False, "error": "الحد الأدنى للتحويل هو 1,000,000 ZN"}), 400
    except ValueError:
        return jsonify({"success": False, "error": "كمية غير صالحة"}), 400
        
    usd_gained = amount / 1000000.0
    
    transaction = db.transaction()
    user_ref = db.collection('users').document(str(user_id))
    
    @firestore.transactional
    def secure_convert_tx(transaction, user_ref):
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict()
        current_balance = float(user_data.get('balance', 0))
        current_usd = float(user_data.get('usd_balance', 0))
        
        if current_balance < amount:
            raise Exception("رصيد النقاط غير كافٍ لإتمام التحويل")
            
        transaction.update(user_ref, {
            'balance': current_balance - amount,
            'usd_balance': current_usd + usd_gained
        })
        return usd_gained
        
    try:
        final_usd = secure_convert_tx(transaction, user_ref)
        return jsonify({"success": True, "usd_gained": final_usd}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# 3. تقديم طلب سحب (معاملة محمية Transaction)
@wallet_bp.route('/wallet_withdraw', methods=['POST'])
def wallet_withdraw():
    is_auth, user_id, err = get_authenticated_user(request, is_post=True)
    if not is_auth: return err
    
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
        if amount <= 0:
            return jsonify({"success": False, "error": "مبلغ غير صالح"}), 400
    except ValueError:
        return jsonify({"success": False, "error": "مبلغ غير صالح"}), 400
        
    wallet_address = req.get('walletAddress', '').strip()
    if not wallet_address:
        return jsonify({"success": False, "error": "عنوان المحفظة مفقود"}), 400
        
    transaction = db.transaction()
    user_ref = db.collection('users').document(str(user_id))
    
    @firestore.transactional
    def secure_withdraw_tx(transaction, user_ref):
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict()
        current_usd = float(user_data.get('usd_balance', 0))
        
        if current_usd < amount:
            raise Exception("رصيد الـ USD غير كافٍ للسحب")
            
        transaction.update(user_ref, {
            'usd_balance': current_usd - amount
        })
        
        withdraw_ref = db.collection('withdrawals').document()
        transaction.set(withdraw_ref, {
            'user_id': str(user_id),
            'amount_usd': amount,
            'wallet_address': wallet_address,
            'status': 'pending',
            'created_at': datetime.datetime.utcnow().isoformat()
        })
        
    try:
        secure_withdraw_tx(transaction, user_ref)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# 4. تسجيل إيداع ناجح عبر TON Connect
@wallet_bp.route('/wallet_deposit_report', methods=['POST'])
def wallet_deposit_report():
    is_auth, user_id, err = get_authenticated_user(request, is_post=True)
    if not is_auth: return err
    
    req = request.get_json(silent=True) or {}
    try:
        usd_amount = float(req.get('usdAmount', 0))
        ton_amount = float(req.get('tonAmount', 0))
        if usd_amount <= 0:
            return jsonify({"success": False, "error": "مبلغ غير صالح"}), 400
    except ValueError:
        return jsonify({"success": False, "error": "مبلغ الإيداع غير صالح"}), 400
        
    boc = req.get('boc')
    
    transaction = db.transaction()
    user_ref = db.collection('users').document(str(user_id))
    
    @firestore.transactional
    def secure_deposit_tx(transaction, user_ref):
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("حساب المستخدم غير موجود")
            
        user_data = snapshot.to_dict()
        current_usd = float(user_data.get('usd_balance', 0))
        
        transaction.update(user_ref, {
            'usd_balance': current_usd + usd_amount
        })
        
        deposit_ref = db.collection('deposits').document()
        transaction.set(deposit_ref, {
            'user_id': str(user_id),
            'amount_usd': usd_amount,
            'amount_ton': ton_amount,
            'boc': boc,
            'status': 'completed',
            'created_at': datetime.datetime.utcnow().isoformat()
        })
        
    try:
        secure_deposit_tx(transaction, user_ref)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

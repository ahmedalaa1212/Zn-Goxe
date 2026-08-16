
# wallet/withdraw/withdraw_db.py
import datetime
from google.cloud import firestore
import database

def convert_zn_to_usd(user_id_str, amount_zn):
    """تحويل النقاط ZN إلى رصيد USD مع العمليات المعزولة Transactions"""
    try:
        usd_gained = round(amount_zn / 1000000.0, 2)
        db = database.get_db()
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
            
            if current_balance < amount_zn:
                raise Exception("رصيد النقاط غير كافٍ لإتمام التحويل")
                
            new_balance = round(current_balance - amount_zn, 2)
            new_usd = round(current_usd + usd_gained, 2)
            
            tx.update(u_ref, {
                'balance': new_balance,
                'usd_balance': new_usd
            })
            
            tx.set(c_ref, {
                'user_id': user_id_str,
                'amount_zn': amount_zn,
                'amount_usd': usd_gained,
                'type': 'convert',
                'status': 'completed',
                'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            return usd_gained, new_usd, new_balance

        gained, new_usd, new_balance = secure_convert_tx(transaction, user_ref, conversion_ref)
        return True, gained, new_usd, new_balance
    except Exception as e:
        print(f"❌ Error converting points for {user_id_str}: {e}")
        return False, str(e), 0, 0


def request_withdrawal(user_id_str, amount_usd, wallet_address):
    """تقديم طلب سحب الأرباح وخصم المبلغ من الرصيد مسبقاً"""
    try:
        db = database.get_db()
        transaction = db.transaction()
        user_ref = db.collection('users').document(user_id_str)

        @firestore.transactional
        def secure_withdraw_tx(tx, u_ref):
            snapshot = u_ref.get(transaction=tx)
            if not snapshot.exists:
                raise Exception("حساب المستخدم غير موجود")
                
            user_data = snapshot.to_dict() or {}
            current_usd = float(user_data.get('usd_balance', 0))
            
            if current_usd < amount_usd:
                raise Exception("رصيد الـ USD غير كافٍ للسحب")
                
            new_usd = round(current_usd - amount_usd, 2)
            tx.update(u_ref, {'usd_balance': new_usd})
            
            withdraw_ref = db.collection('withdrawals').document()
            tx.set(withdraw_ref, {
                'user_id': user_id_str,
                'amount_usd': amount_usd,
                'wallet_address': wallet_address,
                'type': 'withdraw',
                'status': 'pending',
                'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            return new_usd

        new_usd = secure_withdraw_tx(transaction, user_ref)
        return True, new_usd
    except Exception as e:
        print(f"❌ Error submitting withdrawal for {user_id_str}: {e}")
        return False, str(e)


def get_pending_withdrawals_admin(limit=50):
    """جلب طلبات السحب المعلقة للوحة الإدارة"""
    try:
        db = database.get_db()
        docs = db.collection("withdrawals").where("status", "==", "pending").limit(limit).stream()
        return [{"id": doc.id, **(doc.to_dict() or {})} for doc in docs]
    except Exception as e:
        print(f"❌ Error getting pending withdrawals: {e}")
        return []


def process_withdrawal_admin(withdrawal_id, action="approve", tx_hash=None, admin_name="الإدارة المالية"):
    """معالجة السحب للمسؤول (قبول/رفض مع الاسترجاع للرصيد)"""
    try:
        if not withdrawal_id:
            return False, "معرف الطلب غير صالح"

        db = database.get_db()
        w_ref = db.collection("withdrawals").document(str(withdrawal_id))
        w_doc = w_ref.get()

        if not w_doc.exists:
            return False, "طلب السحب غير موجود"

        w_data = w_doc.to_dict() or {}
        if w_data.get("status") != "pending":
            return False, "تمت معالجة هذا الطلب مسبقاً!"

        user_id = w_data.get("user_id")
        amount = float(w_data.get("amount_usd", 0.0))

        if action == "approve":
            w_ref.update({
                "status": "approved",
                "tx_hash": tx_hash or "N/A",
                "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            database.log_admin_action(admin_name, f"الموافقة على طلب السحب {withdrawal_id} بمبلغ ${amount}")
            return True, "تمت الموافقة على طلب السحب بنجاح!"

        elif action == "reject":
            w_ref.update({
                "status": "rejected",
                "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            user_data = database.get_user(user_id) or {}
            cur_usd = float(user_data.get("usd_balance", 0.0) or 0.0)
            database.update_user(user_id, {"usd_balance": round(cur_usd + amount, 2)})

            database.log_admin_action(admin_name, f"رفض طلب السحب {withdrawal_id} وإعادة ${amount} لرصيد {user_id}")
            return True, "تم رفض الطلب وإعادة المبلغ لرصيد المستخدم بنجاح!"

        return False, "إجراء غير معروف"
    except Exception as e:
        print(f"❌ Error processing withdrawal: {e}")
        return False, f"حدث خطأ: {e}"

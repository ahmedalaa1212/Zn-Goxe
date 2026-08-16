# wallet/deposit/deposit_db.py
import datetime
from google.cloud import firestore
import database

def record_user_deposit(user_id_str, gross_usd, net_usd, fee_usd, ton_amount, tx_hash):
    """تسجيل الإيداع وإضافة الرصيد للمستخدم مع نظام حماية ومنع التكرار Anti-Replay"""
    try:
        db = database.get_db()
        deposit_ref = db.collection('deposits').document(tx_hash)
        user_ref = db.collection('users').document(user_id_str)
        transaction = db.transaction()

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

        new_usd = secure_deposit_tx(transaction, user_ref, deposit_ref)
        return True, new_usd
    except Exception as e:
        print(f"❌ Error recording deposit for {user_id_str}: {e}")
        return False, str(e)


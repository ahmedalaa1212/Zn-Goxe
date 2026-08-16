# wallet/history/history_db.py
import database

def fetch_user_history(user_id):
    """جلب دمج كافّة العمليات المسجلة من الفايربيس مجمعة مع المحافظة على الترتيب الأحدث"""
    try:
        db = database.get_db()
        user_id_str = str(user_id).strip()
        user_ids = [user_id_str]
        try:
            num_id = int(user_id_str)
            if num_id not in user_ids: 
                user_ids.append(num_id)
        except (ValueError, TypeError): 
            pass

        history = []

        # جلب أحدث 10 عمليات من كل قسم لتخفيف قراءات الفايربيس
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
            if 'amount_usd' in clean_item and clean_item['amount_usd'] is not None:
                clean_item['amount_usd'] = round(float(clean_item['amount_usd']), 2)
            clean_history.append(clean_item)

        return True, clean_history
    except Exception as e:
        print(f"❌ Error fetching history for {user_id}: {e}")
        return False, []


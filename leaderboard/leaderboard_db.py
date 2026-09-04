import firebase_admin
from firebase_admin import firestore

db = firestore.client()

MAX_GLOBAL_ZNX = 35_000_000.0

TIERS_CONFIG = [
    {"tier": 1, "name": "الشريحة الأولى", "min_pts": 0, "max_pts": 20_000_000, "rate": 10, "quota": 1_500_000},
    {"tier": 2, "name": "الشريحة الثانية", "min_pts": 20_000_000, "max_pts": 100_000_000, "rate": 30, "quota": 2_000_000},
    {"tier": 3, "name": "الشريحة الثالثة", "min_pts": 100_000_000, "max_pts": 500_000_000, "rate": 80, "quota": 2_500_000},
    {"tier": 4, "name": "الشريحة الرابعة", "min_pts": 500_000_000, "max_pts": 2_000_000_000, "rate": 200, "quota": 4_000_000},
    {"tier": 5, "name": "الشريحة الخامسة", "min_pts": 2_000_000_000, "max_pts": 8_000_000_000, "rate": 600, "quota": 5_500_000},
    {"tier": 6, "name": "الشريحة السادسة", "min_pts": 8_000_000_000, "max_pts": 25_000_000_000, "rate": 1600, "quota": 8_000_000},
    {"tier": 7, "name": "الشريحة السابعة", "min_pts": 25_000_000_000, "max_pts": float('inf'), "rate": 4000, "quota": 9_000_000}
]

def get_global_stats():
    doc_ref = db.collection('znx_global_stats').document('summary')
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        init_data = {
            'total_converted_znx': 0.0,
            'max_global_znx': MAX_GLOBAL_ZNX,
            'is_active': True,
            'tiers_config': TIERS_CONFIG
        }
        doc_ref.set(init_data)
        return init_data

def get_user_tier(user_points: float):
    for item in TIERS_CONFIG:
        if item["min_pts"] <= user_points < item["max_pts"]:
            return item
    return TIERS_CONFIG[-1]

def get_user_data(user_id: str):
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        
        balance = float(data.get('balance') or 0.0)
        usd_balance = float(data.get('usd_balance') or 0.0)
        znx_balance = float(data.get('znx_balance') or 0.0)
        total_znx_earned = float(data.get('total_znx_earned') or 0.0)
        
        updates = {}
        if 'usd_balance' not in data: updates['usd_balance'] = usd_balance
        if 'znx_balance' not in data: updates['znx_balance'] = znx_balance
        if 'total_znx_earned' not in data: updates['total_znx_earned'] = total_znx_earned
        
        if updates:
            doc_ref.set(updates, merge=True)

        return {
            'balance': balance,
            'usd_balance': usd_balance,
            'znx_balance': znx_balance,
            'total_znx_earned': total_znx_earned,
            'first_name': data.get('first_name') or data.get('name') or 'لاعب'
        }
    else:
        new_user = {
            'balance': 0.0,
            'usd_balance': 0.0,
            'znx_balance': 0.0,
            'total_znx_earned': 0.0,
            'first_name': 'لاعب جديد'
        }
        doc_ref.set(new_user)
        return new_user

def get_leaderboard_rankings(limit=50):
    rankings = []
    try:
        docs = db.collection('users').limit(100).stream()
        for doc in docs:
            d = doc.to_dict()
            rankings.append({
                'user_id': doc.id,
                'name': d.get('first_name') or d.get('name') or 'لاعب',
                'total_znx_earned': float(d.get('total_znx_earned') or 0.0),
                'znx_balance': float(d.get('znx_balance') or 0.0)
            })
        rankings.sort(key=lambda x: x['total_znx_earned'], reverse=True)
        return rankings[:limit]
    except Exception as e:
        print(f"⚠️ Leaderboard query fallback error: {e}")
        return rankings

def execute_conversion(user_id: str, points_to_convert: float):
    global_ref = db.collection('znx_global_stats').document('summary')
    user_ref = db.collection('users').document(str(user_id))

    stats = get_global_stats()
    total_global_znx = float(stats.get('total_converted_znx') or 0.0)

    if total_global_znx >= MAX_GLOBAL_ZNX:
        return False, "عذراً، تم الوصول إلى الحد الأقصى للمجمّع الكلي (35M ZNX)."

    user_doc = user_ref.get()
    if not user_doc.exists:
        return False, "حساب المستخدم غير موجود بالفيربيس."

    user_data = user_doc.to_dict()
    current_zn_balance = float(user_data.get('balance') or 0.0)

    if points_to_convert <= 0:
        return False, "كمية النقاط يجب أن تكون أكبر من الصفر."

    if current_zn_balance < points_to_convert:
        return False, f"رصيد نقاط ZN غير كافٍ. رصيدك الحالي: {current_zn_balance:,.2f}"

    current_tier = get_user_tier(current_zn_balance)
    znx_received = points_to_convert / current_tier['rate']

    if total_global_znx + znx_received > MAX_GLOBAL_ZNX:
        znx_received = MAX_GLOBAL_ZNX - total_global_znx
        points_to_convert = znx_received * current_tier['rate']
        if znx_received <= 0:
            return False, "تم استنفاد مجمّع العملات المتاح بالكامل."

    new_zn_balance = current_zn_balance - points_to_convert
    new_znx_balance = float(user_data.get('znx_balance') or 0.0) + znx_received
    new_total_znx_earned = float(user_data.get('total_znx_earned') or 0.0) + znx_received
    new_global_total = total_global_znx + znx_received

    user_ref.set({
        'balance': round(new_zn_balance, 4),
        'znx_balance': round(new_znx_balance, 6),
        'total_znx_earned': round(new_total_znx_earned, 6),
        'usd_balance': float(user_data.get('usd_balance') or 0.0)
    }, merge=True)

    global_ref.set({
        'total_converted_znx': round(new_global_total, 6),
        'max_global_znx': MAX_GLOBAL_ZNX,
        'is_active': new_global_total < MAX_GLOBAL_ZNX,
        'tiers_config': TIERS_CONFIG
    }, merge=True)

    return True, {
        'converted_points': points_to_convert,
        'znx_gained': round(znx_received, 6),
        'new_zn_balance': round(new_zn_balance, 4),
        'new_znx_balance': round(new_znx_balance, 6),
        'new_total_earned': round(new_total_znx_earned, 6)
    }

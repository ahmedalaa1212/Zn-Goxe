import firebase_admin
from firebase_admin import firestore

db = firestore.client()

# ثوابت النظام
MAX_GLOBAL_ZNX = 35_000_000

# تعريف الشرائح: (الحد الأدنى للنقاط، الحد الأقصى للنقاط، معدل التحويل)
CONVERSION_TIERS = [
    (0, 20_000_000, 10),
    (20_000_000, 100_000_000, 30),
    (100_000_000, 500_000_000, 80),
    (500_000_000, 2_000_000_000, 200),
    (2_000_000_000, 8_000_000_000, 600),
    (8_000_000_000, 25_000_000_000, 1600),
    (25_000_000_000, float('inf'), 4000)
]

def calculate_znx_output(user_points: float, points_to_convert: float) -> float:
    """حساب عدد عملات ZNX المستحقة بناءً على شريحة النقاط الحالية للمستخدم"""
    for min_pts, max_pts, rate in CONVERSION_TIERS:
        if min_pts <= user_points < max_pts:
            return points_to_convert / rate
    return points_to_convert / 4000

def get_global_stats():
    """جلب إجمالي العملات المحولة على مستوى البوت"""
    doc_ref = db.collection('znx_global_stats').document('summary')
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        initial_data = {'total_converted_znx': 0.0, 'is_pool_active': True}
        doc_ref.set(initial_data)
        return initial_data

def get_leaderboard_data(limit=50):
    """جلب المتصدرين بناءً على رصيد ZNX المحول"""
    users_ref = db.collection('users').order_by('znx_balance', direction=firestore.Query.DESCENDING).limit(limit)
    docs = users_ref.stream()
    leaderboard = []
    for doc in docs:
        data = doc.to_dict()
        leaderboard.append({
            'user_id': doc.id,
            'name': data.get('name', 'مستخدم'),
            'znx_balance': round(data.get('znx_balance', 0.0), 4)
        })
    return leaderboard

def process_conversion(user_id: str, points_amount: float):
    """تنفيذ عملية التحويل والتحقق من سقف الـ 35 مليون عملة"""
    global_ref = db.collection('znx_global_stats').document('summary')
    user_ref = db.collection('users').document(user_id)

    stats = get_global_stats()
    if stats.get('total_converted_znx', 0) >= MAX_GLOBAL_ZNX:
        return False, "تم الوصول للحد الأقصى الكلي للمجمّع (35,000,000 ZNX)، التحويل متوقف حالياً."

    user_doc = user_ref.get()
    if not user_doc.exists:
        return False, "المستخدم غير موجود."

    user_data = user_doc.to_dict()
    user_points = user_data.get('points', 0)

    if user_points < points_amount or points_amount <= 0:
        return False, "رصيد النقاط غير كافٍ."

    # حساب الناتج
    znx_gained = calculate_znx_output(user_points, points_amount)

    # التحقق من عدم تجاوز السقف الكلي
    if stats['total_converted_znx'] + znx_gained > MAX_GLOBAL_ZNX:
        znx_gained = MAX_GLOBAL_ZNX - stats['total_converted_znx']
        if znx_gained <= 0:
            return False, "تجاوز السقف الإجمالي للعملة."

    # تحديث البيانات في معاملات ذرية (Atomic Transaction)
    new_user_points = user_points - points_amount
    new_user_znx = user_data.get('znx_balance', 0.0) + znx_gained
    new_global_total = stats['total_converted_znx'] + znx_gained

    user_ref.update({
        'points': new_user_points,
        'znx_balance': new_user_znx
    })

    global_ref.update({
        'total_converted_znx': new_global_total,
        'is_pool_active': new_global_total < MAX_GLOBAL_ZNX
    })

    return True, {
        'message': 'تم التحويل بنجاح!',
        'znx_gained': round(znx_gained, 4),
        'remaining_points': new_user_points,
        'total_znx': round(new_user_znx, 4),
        'global_total': round(new_global_total, 4)
    }

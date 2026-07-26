# games/games_api.py
from flask import Blueprint, jsonify, request
import time
import random
# قم بتعديل الاستيراد التالي بناءً على هيكلة مشروعك
# from database import db
# from core.security import get_authenticated_user 

games_bp = Blueprint('games', __name__)

# إعدادات الساحة
ENTRY_FEE = 1000
MIN_PARTICIPANTS = 20
PRIZE_POOL_PERCENTAGE = 0.45 # 45% للجوائز و 55% أرباح وحرق
ROUND_DURATION = 900 # 15 دقيقة (بالثواني)
LOCK_SECONDS = 15 # قفل الاشتراك قبل النهاية بـ 15 ثانية

def get_current_round_info():
    """حساب الـ ID الخاص بالجولة الحالية بناءً على الوقت العالمي الثابت"""
    current_time = int(time.time())
    round_id = current_time // ROUND_DURATION
    end_time = (round_id + 1) * ROUND_DURATION
    return round_id, end_time, current_time

@games_bp.route('/status', methods=['POST'])
def arena_status():
    data = request.get_json()
    init_data = data.get('initData')
    
    # user = get_authenticated_user(init_data)
    # if not user: return jsonify({"success": False, "message": "غير مصرح لك"}), 401
    # uid = user['uid']
    
    # للتجربة فقط (احذف هذا واستخدم السطرين بالأعلى)
    uid = "test_user_id" 
    
    round_id, end_time, current_time = get_current_round_info()
    
    # استدعاء بيانات الجولة من الداتابيز (Firestore)
    # round_ref = db.collection('arena_rounds').document(str(round_id))
    # round_doc = round_ref.get()
    
    # محاكاة البيانات في حالة عدم وجود داتابيز حقيقية متصلة هنا
    participants = []
    # if round_doc.exists:
    #     participants = round_doc.to_dict().get('participants', [])
        
    participants_count = len(participants)
    has_joined = any(p['uid'] == uid for p in participants)
    
    # الحسبة الذكية: نظهر فقط 45% من الإجمالي
    total_collected = participants_count * ENTRY_FEE
    visible_prize_pool = int(total_collected * PRIZE_POOL_PERCENTAGE)

    # معالجة الجولة إذا انتهى وقتها ولم تتم معالجتها
    if current_time >= end_time:
        resolve_round(round_id)

    return jsonify({
        "success": True,
        "round_id": round_id,
        "end_time": end_time,
        "participants": participants_count,
        "prize_pool": visible_prize_pool,
        "has_joined": has_joined
    })

@games_bp.route('/join', methods=['POST'])
def join_arena():
    data = request.get_json()
    init_data = data.get('initData')
    
    # user = get_authenticated_user(init_data)
    # if not user: return jsonify({"success": False, "message": "غير مصرح"}), 401
    # uid = user['uid']
    # name = user.get('first_name', 'Player')
    
    uid = "test_user_id"
    name = "Player"

    round_id, end_time, current_time = get_current_round_info()
    
    # 1. منع الدخول في آخر 15 ثانية (Security Check)
    if current_time >= (end_time - LOCK_SECONDS):
        return jsonify({"success": False, "message": "تم إغلاق باب الاشتراك لهذه الجولة!"})
        
    # 2. جلب الجولة من الداتابيز
    # round_ref = db.collection('arena_rounds').document(str(round_id))
    # user_ref = db.collection('users').document(uid)
    
    # @firestore.transactional
    # def join_transaction(transaction, round_ref, user_ref):
    #     user_doc = user_ref.get(transaction=transaction)
    #     if not user_doc.exists or user_doc.to_dict().get('balance', 0) < ENTRY_FEE:
    #         return False, "رصيدك غير كافٍ"
            
    #     round_doc = round_ref.get(transaction=transaction)
    #     participants = []
    #     if round_doc.exists:
    #         participants = round_doc.to_dict().get('participants', [])
            
    #     if any(p['uid'] == uid for p in participants):
    #         return False, "أنت مشترك بالفعل"
            
    #     # خصم الرصيد
    #     transaction.update(user_ref, {'balance': firestore.Increment(-ENTRY_FEE)})
    #     # إضافة المستخدم للجولة
    #     participants.append({"uid": uid, "name": name})
    #     transaction.set(round_ref, {'participants': participants, 'status': 'active'}, merge=True)
    #     return True, "تم الاشتراك بنجاح"
        
    # success, msg = join_transaction(db.transaction(), round_ref, user_ref)
    
    # محاكاة النجاح
    success, msg = True, "تم الاشتراك بنجاح"
    
    if success:
        return jsonify({"success": True, "message": msg})
    else:
        return jsonify({"success": False, "message": msg})

def resolve_round(round_id):
    """دالة لإنهاء الجولة، يتم استدعاؤها تلقائياً عند طلب النتائج أو الحالة بعد انتهاء الوقت"""
    # round_ref = db.collection('arena_rounds').document(str(round_id))
    # round_doc = round_ref.get()
    
    # if not round_doc.exists or round_doc.to_dict().get('status') != 'active':
    #     return # الجولة غير موجودة أو تمت معالجتها بالفعل
        
    # data = round_doc.to_dict()
    # participants = data.get('participants', [])
    participants = [] # محاكاة
    
    # # الحالة الأولى: لم يكتمل العدد (Refund)
    # if len(participants) < MIN_PARTICIPANTS:
    #     batch = db.batch()
    #     for p in participants:
    #         user_ref = db.collection('users').document(p['uid'])
    #         batch.update(user_ref, {'balance': firestore.Increment(ENTRY_FEE)})
    #     round_ref.update({'status': 'refunded'})
    #     batch.commit()
    #     return

    # # الحالة الثانية: اكتمال العدد وتوزيع الجوائز (45% فقط)
    # total_collected = len(participants) * ENTRY_FEE
    # visible_prize_pool = int(total_collected * PRIZE_POOL_PERCENTAGE)
    
    # # اختيار 5 فائزين عشوائياً
    # random.shuffle(participants)
    # winners_list = participants[:5] if len(participants) >= 5 else participants
    
    # percentages = [0.30, 0.25, 0.20, 0.15, 0.10]
    # final_winners = []
    
    # batch = db.batch()
    # for i, winner in enumerate(winners_list):
    #     prize_amount = int(visible_prize_pool * percentages[i])
    #     user_ref = db.collection('users').document(winner['uid'])
    #     batch.update(user_ref, {'balance': firestore.Increment(prize_amount)})
        
    #     final_winners.append({
    #         "uid": winner['uid'],
    #         "name": winner['name'],
    #         "prize": prize_amount
    #     })
        
    # round_ref.update({
    #     'status': 'completed',
    #     'winners': final_winners
    # })
    # batch.commit()
    pass

@games_bp.route('/results', methods=['POST'])
def get_results():
    """الفرونت إند بيستدعيها بمجرد ما العداد يوصل صفر عشان يعرض الأنيميشن"""
    data = request.get_json()
    init_data = data.get('initData')
    req_round_id = data.get('round_id')
    
    # تأكد إن الجولة اتعالجت
    resolve_round(req_round_id)
    
    # جلب النتيجة النهائية
    # round_ref = db.collection('arena_rounds').document(str(req_round_id))
    # round_doc = round_ref.get()
    
    # if not round_doc.exists:
    #     return jsonify({"success": False})
        
    # r_data = round_doc.to_dict()
    # return jsonify({
    #     "success": True,
    #     "status": r_data.get('status'),
    #     "winners": r_data.get('winners', [])
    # })
    
    # محاكاة للرد عشان الفرونت إند يشتغل معاك أثناء التجربة
    return jsonify({
        "success": True,
        "status": "refunded", # غيرها لـ completed وشوف شكل الأنيميشن للفائزين
        "winners": []
    })

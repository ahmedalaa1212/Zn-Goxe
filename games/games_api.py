# games/games_api.py
import time
import random
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

# استدعاء كائن قاعدة البيانات من الملف الخاص بك
from database import db
# استدعاء دالة الحماية (يجب أن تكون موجودة لديك في هذا المسار)
from core.security import get_authenticated_user

games_bp = Blueprint('games', __name__)

# ==========================================
# إعدادات اقتصاد اللعبة
# ==========================================
ENTRY_FEE = 1000
MIN_PARTICIPANTS = 20
PRIZE_POOL_PERCENTAGE = 0.45
ROUND_DURATION = 900 # 15 دقيقة
LOCK_SECONDS = 15 # قفل قبل النهاية

def get_current_round_info():
    """حساب ID الجولة والوقت بناءً على توقيت السيرفر العالمي"""
    current_time = int(time.time())
    round_id = current_time // ROUND_DURATION
    end_time = (round_id + 1) * ROUND_DURATION
    return str(round_id), end_time, current_time

@games_bp.route('/status', methods=['POST'])
def arena_status():
    data = request.get_json()
    init_data = data.get('initData')
    
    user = get_authenticated_user(init_data)
    if not user:
        return jsonify({"success": False, "message": "غير مصرح لك"}), 401
    
    uid = user['uid']
    round_id, end_time, current_time = get_current_round_info()
    
    # جلب بيانات الجولة من Firestore
    round_ref = db.collection('arena_rounds').document(round_id)
    round_doc = round_ref.get()
    
    participants = []
    if round_doc.exists:
        participants = round_doc.to_dict().get('participants', [])
        
    has_joined = any(p['uid'] == uid for p in participants)
    participants_count = len(participants)
    
    # إرسال مبلغ الجائزة فقط للفرونت إند دون كشف التفاصيل
    total_collected = participants_count * ENTRY_FEE
    visible_prize_pool = int(total_collected * PRIZE_POOL_PERCENTAGE)

    # التحقق مما إذا كانت الجولة انتهت وتحتاج لمعالجة
    if current_time >= end_time:
        resolve_round(round_id)

    return jsonify({
        "success": True,
        "round_id": round_id,
        "end_time": end_time,
        "prize_pool": visible_prize_pool, # نرسل القيمة النهائية فقط
        "has_joined": has_joined
    })

@games_bp.route('/join', methods=['POST'])
def join_arena():
    data = request.get_json()
    init_data = data.get('initData')
    
    user = get_authenticated_user(init_data)
    if not user:
        return jsonify({"success": False, "message": "غير مصرح لك"}), 401
        
    uid = user['uid']
    name = user.get('first_name', 'Player')

    round_id, end_time, current_time = get_current_round_info()
    
    # منع الدخول في آخر 15 ثانية
    if current_time >= (end_time - LOCK_SECONDS):
        return jsonify({"success": False, "message": "تم إغلاق باب الاشتراك لهذه الجولة! انتظر الجولة القادمة."})
        
    round_ref = db.collection('arena_rounds').document(round_id)
    user_ref = db.collection('users').document(uid)
    
    # استخدام Transaction لضمان عدم حدوث تلاعب أو خصم مزدوج
    @firestore.transactional
    def join_transaction(transaction, round_ref, user_ref):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists or user_doc.to_dict().get('balance', 0) < ENTRY_FEE:
            return False, "رصيدك غير كافٍ للاشتراك (تحتاج 1000 ZN)."
            
        round_doc = round_ref.get(transaction=transaction)
        participants = []
        if round_doc.exists:
            participants = round_doc.to_dict().get('participants', [])
            
        if any(p['uid'] == uid for p in participants):
            return False, "أنت مشترك بالفعل في هذه الجولة."
            
        # خصم الرصيد
        transaction.update(user_ref, {'balance': firestore.Increment(-ENTRY_FEE)})
        
        # إضافة اللاعب للجولة
        participants.append({"uid": uid, "name": name})
        transaction.set(round_ref, {'participants': participants, 'status': 'active'}, merge=True)
        return True, "تم دخول الساحة بنجاح!"
        
    try:
        success, msg = join_transaction(db.transaction(), round_ref, user_ref)
        return jsonify({"success": success, "message": msg})
    except Exception as e:
        print(f"Error in join_arena: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء معالجة الطلب."})

def resolve_round(round_id):
    """معالجة الجولة بعد انتهاء الوقت (توزيع الجوائز أو الاسترداد)"""
    round_ref = db.collection('arena_rounds').document(round_id)
    round_doc = round_ref.get()
    
    if not round_doc.exists or round_doc.to_dict().get('status') != 'active':
        return # الجولة عولجت مسبقاً أو غير موجودة
        
    data = round_doc.to_dict()
    participants = data.get('participants', [])
    
    # الحالة 1: لم يكتمل العدد المطلوب (استرداد آمن)
    if len(participants) < MIN_PARTICIPANTS:
        batch = db.batch()
        for p in participants:
            user_ref = db.collection('users').document(p['uid'])
            # إرجاع الرصيد للمستخدم
            batch.update(user_ref, {'balance': firestore.Increment(ENTRY_FEE)})
            
        round_ref.update({'status': 'refunded'})
        batch.commit()
        return

    # الحالة 2: اكتمل العدد (توزيع الأرباح على 5 فائزين)
    total_collected = len(participants) * ENTRY_FEE
    visible_prize_pool = int(total_collected * PRIZE_POOL_PERCENTAGE)
    
    # خلط المتسابقين واختيار 5
    random.shuffle(participants)
    winners_list = participants[:5] if len(participants) >= 5 else participants
    
    percentages = [0.30, 0.25, 0.20, 0.15, 0.10]
    final_winners = []
    
    batch = db.batch()
    for i, winner in enumerate(winners_list):
        prize_amount = int(visible_prize_pool * percentages[i])
        user_ref = db.collection('users').document(winner['uid'])
        # إضافة الجائزة للمستخدم
        batch.update(user_ref, {'balance': firestore.Increment(prize_amount)})
        
        final_winners.append({
            "uid": winner['uid'],
            "name": winner['name'],
            "prize": prize_amount
        })
        
    round_ref.update({
        'status': 'completed',
        'winners': final_winners
    })
    batch.commit()

@games_bp.route('/results', methods=['POST'])
def get_results():
    data = request.get_json()
    init_data = data.get('initData')
    req_round_id = data.get('round_id')
    
    user = get_authenticated_user(init_data)
    if not user:
        return jsonify({"success": False}), 401
    
    # تأكد من معالجة الجولة إذا لزم الأمر
    resolve_round(str(req_round_id))
    
    round_ref = db.collection('arena_rounds').document(str(req_round_id))
    round_doc = round_ref.get()
    
    if not round_doc.exists:
        return jsonify({"success": False})
        
    r_data = round_doc.to_dict()
    return jsonify({
        "success": True,
        "status": r_data.get('status'),
        "winners": r_data.get('winners', [])
    })

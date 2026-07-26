# games/games_api.py
import time
import random
from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from database import db
# استدعاء دالة الحماية
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
    """حساب ID الجولة الحالية والسابقة بناءً على توقيت السيرفر العالمي"""
    current_time = int(time.time())
    round_id_num = current_time // ROUND_DURATION
    end_time = (round_id_num + 1) * ROUND_DURATION
    prev_round_id = str(round_id_num - 1)
    return str(round_id_num), end_time, current_time, prev_round_id

@games_bp.route('/status', methods=['POST'])
def arena_status():
    try:
        # التعديل الجذري: استخدام دالة الحماية بالطريقة الصحيحة المتوافقة مع ملفك
        success, uid, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res # إرجاع رسالة الخطأ من ملف الحماية مباشرة
        
        round_id, end_time, current_time, prev_round_id = get_current_round_info()
        
        # فحص الجولة السابقة
        prev_round_ref = db.collection('arena_rounds').document(prev_round_id)
        prev_doc = prev_round_ref.get()
        if prev_doc.exists and prev_doc.to_dict().get('status') == 'active':
            resolve_round(prev_round_id)

        # جلب بيانات الجولة الحالية
        round_ref = db.collection('arena_rounds').document(round_id)
        round_doc = round_ref.get()
        
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
        has_joined = any(p['uid'] == uid for p in participants)
        
        # جلب رصيد اللاعب
        user_doc = db.collection('users').document(uid).get()
        balance = user_doc.to_dict().get('balance', 0) if user_doc.exists else 0

        total_collected = len(participants) * ENTRY_FEE
        visible_prize_pool = int(total_collected * PRIZE_POOL_PERCENTAGE)

        return jsonify({
            "success": True,
            "round_id": round_id,
            "end_time": end_time,
            "prize_pool": visible_prize_pool,
            "has_joined": has_joined,
            "balance": balance
        })
    except Exception as e:
        print(f"Error in arena_status: {e}")
        return jsonify({"success": False, "message": "خطأ في الاتصال بالخادم."}), 500

@games_bp.route('/join', methods=['POST'])
def join_arena():
    # التعديل هنا أيضاً
    success, uid, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res
        
    name = f"Player #{uid[:5]}" # بما أن دالتك ترجع الـ ID فقط، سننشئ اسماً افتراضياً مميزاً

    round_id, end_time, current_time, _ = get_current_round_info()
    
    if current_time >= (end_time - LOCK_SECONDS):
        return jsonify({"success": False, "message": "تم إغلاق باب الاشتراك لهذه الجولة! انتظر الجولة القادمة."})
        
    round_ref = db.collection('arena_rounds').document(round_id)
    user_ref = db.collection('users').document(uid)
    
    @firestore.transactional
    def join_transaction(transaction, round_ref, user_ref):
        user_doc = user_ref.get(transaction=transaction)
        current_balance = user_doc.to_dict().get('balance', 0) if user_doc.exists else 0
        
        if current_balance < ENTRY_FEE:
            return False, "رصيدك غير كافٍ للاشتراك (تحتاج 1000 ZN)."
            
        round_doc = round_ref.get(transaction=transaction)
        participants = round_doc.to_dict().get('participants', []) if round_doc.exists else []
            
        if any(p['uid'] == uid for p in participants):
            return False, "أنت مشترك بالفعل في هذه الجولة."
            
        # خصم الرصيد
        transaction.update(user_ref, {'balance': current_balance - ENTRY_FEE})
        
        # إضافة اللاعب
        participants.append({"uid": uid, "name": name})
        transaction.set(round_ref, {'participants': participants, 'status': 'active'}, merge=True)
        return True, "تم دخول الساحة بنجاح!"
        
    try:
        success_join, msg = join_transaction(db.transaction(), round_ref, user_ref)
        return jsonify({"success": success_join, "message": msg})
    except Exception as e:
        print(f"Error in join_arena: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء معالجة الطلب."})

def resolve_round(round_id):
    round_ref = db.collection('arena_rounds').document(round_id)
    round_doc = round_ref.get()
    
    if not round_doc.exists or round_doc.to_dict().get('status') != 'active':
        return 
        
    data = round_doc.to_dict()
    participants = data.get('participants', [])
    batch = db.batch()
    
    if len(participants) < MIN_PARTICIPANTS:
        for p in participants:
            user_ref = db.collection('users').document(p['uid'])
            batch.update(user_ref, {'balance': firestore.Increment(ENTRY_FEE)})
            
        batch.update(round_ref, {'status': 'refunded'})
        batch.commit()
        return

    total_collected = len(participants) * ENTRY_FEE
    visible_prize_pool = int(total_collected * PRIZE_POOL_PERCENTAGE)
    
    random.shuffle(participants)
    winners_list = participants[:5] if len(participants) >= 5 else participants
    percentages = [0.30, 0.25, 0.20, 0.15, 0.10]
    final_winners = []
    
    for i, winner in enumerate(winners_list):
        prize_amount = int(visible_prize_pool * percentages[i])
        user_ref = db.collection('users').document(winner['uid'])
        batch.update(user_ref, {'balance': firestore.Increment(prize_amount)})
        
        final_winners.append({
            "uid": winner['uid'],
            "name": winner['name'],
            "prize": prize_amount
        })
        
    batch.update(round_ref, {'status': 'completed', 'winners': final_winners})
    batch.commit()

@games_bp.route('/results', methods=['POST'])
def get_results():
    success, uid, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res
    
    data = request.get_json() or {}
    req_round_id = data.get('round_id')
    
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

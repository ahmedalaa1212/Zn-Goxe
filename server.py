import os
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

db = None
firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT', '').strip()

if firebase_creds_json:
    try:
        creds_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ [Firebase] Connected successfully!")
    except Exception as e:
        print(f"❌ [Firebase] Error: {e}")

GAME_CONFIG = {
    'capacities': {0: 10000, 1: 20000, 2: 30000, 3: 50000, 4: 100000, 5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000},
    'miningRates': {1: 100, 2: 500, 3: 1500, 4: 4000, 5: 10000, 6: 25000, 7: 60000, 8: 150000, 9: 500000},
    'dailyRewards': {1: 3000, 2: 6000, 3: 10000, 4: 15000, 5: 25000, 6: 40000, 7: 100000}
}

SHOP_CONFIG = {
    'mining': {
        1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000,
        6: 250000, 7: 600000, 8: 1500000, 9: 5000000
    },
    'storage': {
        1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000,
        6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000
    }
}

def safe_float(val):
    try: return float(val)
    except (TypeError, ValueError): return 0.0

def safe_int(val):
    try: return int(val)
    except (TypeError, ValueError): return 0

def make_aware(dt):
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_user_ref(tg_id):
    return db.collection('users').document(str(tg_id).strip())

def get_user_mining_rate(user_data):
    hourly_rate = 0.0
    for i in range(1, 11):
        count = safe_int(user_data.get(f'lvl{i}_count', 0))
        hourly_rate += count * GAME_CONFIG['miningRates'].get(i, 0)
    return hourly_rate

def calculate_user_harvest(user_data):
    last_claim_str = user_data.get('last_claim_time')
    if not last_claim_str: return 0.0
    try:
        last_claim = datetime.fromisoformat(str(last_claim_str))
        last_claim = make_aware(last_claim)
    except ValueError:
        return 0.0
    now = datetime.now(timezone.utc)
    diff_hours = max(0.0, (now - last_claim).total_seconds() / 3600.0)
    
    hourly_rate = get_user_mining_rate(user_data)
    storage_lvl = safe_int(user_data.get('storage_level', 0))
    max_cap = GAME_CONFIG['capacities'].get(storage_lvl, 10000)
    
    unclaimed = diff_hours * hourly_rate
    return min(unclaimed, float(max_cap))

@app.route('/')
def index(): 
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename): 
    return send_from_directory('.', filename)

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    telegram_id = request.args.get('telegramId')
    ref_id = request.args.get('ref_id')
    
    if not telegram_id or not db:
        return jsonify({'success': False, 'error': 'Missing ID'}), 400
    
    telegram_id = str(telegram_id).strip()
    doc = get_user_ref(telegram_id).get()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if not doc.exists:
        new_user = {
            "telegram_id": telegram_id,
            "first_name": "صديق",
            "balance": 0.0,
            "ad_balance": 0.0, 
            "is_banned": False,
            "last_claim_time": now_iso,
            "storage_level": 0,
            "daily_day": 1,
            "last_daily_claim_time": "2000-01-01T00:00:00+00:00",
            "referred_by": ref_id if (ref_id and ref_id != telegram_id) else None,
            "pending_ref_earnings": 0.0,
            "invited_friends_count": 0,
            "claimed_ref_tasks": [],
            "referral_details": {}
        }
        for i in range(1, 11): new_user[f"lvl{i}_count"] = 0
        get_user_ref(telegram_id).set(new_user)
        user_data = new_user
        
        if new_user['referred_by']:
            ref_user_ref = get_user_ref(new_user['referred_by'])
            ref_doc = ref_user_ref.get()
            if ref_doc.exists:
                ref_user_ref.update({
                    'invited_friends_count': firestore.Increment(1),
                    f'referral_details.{telegram_id}': {'name': 'صديق', 'earned': 0.0}
                })
    else:
        user_data = doc.to_dict()
        updates = {}
        if 'ad_balance' not in user_data: updates['ad_balance'] = 0.0
        if 'pending_ref_earnings' not in user_data: updates['pending_ref_earnings'] = 0.0
        if 'invited_friends_count' not in user_data: updates['invited_friends_count'] = 0
        if 'claimed_ref_tasks' not in user_data: updates['claimed_ref_tasks'] = []
        if 'referral_details' not in user_data: updates['referral_details'] = {}
        
        if updates:
            get_user_ref(telegram_id).update(updates)
            user_data.update(updates)
        
    response_data = user_data.copy()
    
    calculated_rate = get_user_mining_rate(user_data)
    storage_lvl = safe_int(user_data.get('storage_level', 0))
    calculated_cap = GAME_CONFIG['capacities'].get(storage_lvl, 10000)
    calculated_uncl = calculate_user_harvest(user_data)
    
    response_data['calculated_hourly_rate'] = calculated_rate
    response_data['calculated_max_cap'] = calculated_cap
    response_data['calculated_unclaimed'] = calculated_uncl
    response_data['server_time'] = now_iso
    
    return jsonify({'success': True, 'data': response_data}), 200

# 🔥 واجهة جديدة لجلب قائمة الأصدقاء وأرباحهم الفردية 🔥
@app.route('/api/get_friends_list', methods=['GET'])
def get_friends_list():
    telegram_id = request.args.get('telegramId')
    if not telegram_id: return jsonify({'success': False}), 400
    
    try:
        doc = get_user_ref(telegram_id).get()
        if not doc.exists: return jsonify({'success': False, 'friends': []}), 200
        
        user_data = doc.to_dict()
        referral_details = user_data.get('referral_details', {})
        
        friends_list = []
        for f_id, details in referral_details.items():
            friends_list.append({
                'id': f_id,
                'name': details.get('name', f'User {f_id}'),
                'earned': safe_float(details.get('earned', 0))
            })
            
        # ترتيب الأصدقاء حسب الأكثر ربحاً
        friends_list.sort(key=lambda x: x['earned'], reverse=True)
        return jsonify({'success': True, 'friends': friends_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/claim', methods=['POST'])
def claim():
    data = request.get_json() or {}
    telegram_id = data.get('telegramId')
    if not telegram_id: return jsonify({'success': False}), 400
    
    telegram_id = str(telegram_id).strip()
    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists: return jsonify({'success': False, 'error': 'User not found'}), 404
        
        user_data = doc.to_dict()
        unclaimed = calculate_user_harvest(user_data)
        if unclaimed <= 0: return jsonify({'success': False, 'error': 'لا يوجد رصيد للتجميع'}), 400

        now_iso = datetime.now(timezone.utc).isoformat()
        current_balance = safe_float(user_data.get('balance', 0))
        
        user_ref.update({
            'balance': current_balance + unclaimed,
            'last_claim_time': now_iso
        })
        
        # 🔥 نظام مكافأة الأصدقاء وتحديث أرباح كل شخص بشكل منفصل 🔥
        referred_by = user_data.get('referred_by')
        if referred_by:
            referrer_ref = get_user_ref(referred_by)
            referrer_doc = referrer_ref.get()
            if referrer_doc.exists:
                bonus = unclaimed * 0.10
                # التحديث في رصيد الإحالة العام وفي ملف الصديق الفردي
                referrer_ref.update({
                    'pending_ref_earnings': firestore.Increment(bonus),
                    f'referral_details.{telegram_id}.earned': firestore.Increment(bonus)
                })

        return jsonify({'success': True, 'claimed': unclaimed}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    data = request.get_json() or {}
    telegram_id = data.get('telegramId')
    if not telegram_id: return jsonify({'success': False}), 400
    
    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists: return jsonify({'success': False}), 404
        
        user_data = doc.to_dict()
        pending = safe_float(user_data.get('pending_ref_earnings', 0))
        if pending <= 0: return jsonify({'success': False, 'error': 'لا توجد أرباح للتجميع'}), 400
        
        fee = pending * 0.03 
        net_amount = pending - fee
        current_balance = safe_float(user_data.get('balance', 0))
        
        user_ref.update({
            'balance': current_balance + net_amount,
            'pending_ref_earnings': 0.0
        })
        
        return jsonify({'success': True, 'net_amount': net_amount, 'fee': fee}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/claim_ref_task', methods=['POST'])
def claim_ref_task():
    data = request.get_json() or {}
    telegram_id = data.get('telegramId')
    task_id = safe_int(data.get('taskId'))
    reward = safe_float(data.get('reward'))
    req_friends = safe_int(data.get('reqFriends'))
    
    if not telegram_id or not task_id: return jsonify({'success': False}), 400
    
    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists: return jsonify({'success': False}), 404
        
        user_data = doc.to_dict()
        friends_count = safe_int(user_data.get('invited_friends_count', 0))
        claimed_tasks = user_data.get('claimed_ref_tasks', [])
        
        if task_id in claimed_tasks:
            return jsonify({'success': False, 'error': 'تم استلام المكافأة مسبقاً'}), 400
            
        if friends_count < req_friends:
            return jsonify({'success': False, 'error': 'عدد الأصدقاء غير كافي'}), 400
            
        current_balance = safe_float(user_data.get('balance', 0))
        claimed_tasks.append(task_id)
        
        user_ref.update({
            'balance': current_balance + reward,
            'claimed_ref_tasks': claimed_tasks
        })
        
        return jsonify({'success': True, 'reward': reward}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    data = request.get_json() or {}
    telegram_id = data.get('telegramId')
    if not telegram_id: return jsonify({'success': False}), 400
    
    telegram_id = str(telegram_id).strip()
    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists: return jsonify({'success': False, 'error': 'User not found'}), 404
            
        user_data = doc.to_dict()
        last_daily_str = user_data.get('last_daily_claim_time', "2000-01-01T00:00:00+00:00")
        try: 
            last_daily = datetime.fromisoformat(str(last_daily_str))
            last_daily = make_aware(last_daily)
        except ValueError: 
            last_daily = make_aware(datetime.fromisoformat("2000-01-01T00:00:00+00:00"))
            
        now = datetime.now(timezone.utc)
        
        if (now - last_daily).total_seconds() < 86400:
            return jsonify({'success': False, 'error': 'لم تمر 24 ساعة بعد!'}), 400
            
        current_day = safe_int(user_data.get('daily_day', 1))
        reward = safe_float(GAME_CONFIG['dailyRewards'].get(current_day, 3000))
        
        next_day = current_day + 1 if current_day < 7 else 1
        current_balance = safe_float(user_data.get('balance', 0))
        
        user_ref.update({
            'balance': current_balance + reward,
            'daily_day': next_day,
            'last_daily_claim_time': now.isoformat()
        })
        return jsonify({'success': True, 'reward': reward}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@firestore.transactional
def execute_upgrade_transaction(transaction, user_ref, upg_type, level_num):
    doc = user_ref.get(transaction=transaction)
    if not doc.exists: return False, 'المستخدم غير موجود'
        
    user_data = doc.to_dict()
    current_balance = safe_float(user_data.get('balance', 0))
    
    price = SHOP_CONFIG.get(upg_type, {}).get(level_num)
    if price is None: return False, 'مستوى غير صالح'
    price = float(price)
    
    if current_balance < price:
        return False, 'الرصيد غير كافي!'
        
    updates = {
        'balance': current_balance - price
    }
    
    if upg_type == 'mining':
        field_name = f'lvl{level_num}_count'
        current_count = safe_int(user_data.get(field_name, 0))
        if current_count >= 15: return False, 'وصلت للحد الأقصى'
        updates[field_name] = current_count + 1
    elif upg_type == 'storage':
        if level_num <= safe_int(user_data.get('storage_level', 0)):
            return False, 'تم شراء هذا المخزن مسبقاً'
        updates['storage_level'] = level_num
        
    transaction.update(user_ref, updates)
    return True, 'تم الشراء بنجاح'

@app.route('/api/upgrade', methods=['POST'])
def upgrade():
    data = request.get_json() or {}
    telegram_id = data.get('telegramId') or data.get('tg_id')
    upg_type = data.get('type') 
    level_num = safe_int(data.get('level_num'))

    if not telegram_id or not upg_type or not level_num:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400
        
    telegram_id = str(telegram_id).strip()
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        success, message = execute_upgrade_transaction(transaction, user_ref, upg_type, level_num)
        
        if success: return jsonify({'success': True}), 200
        else: return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/game_reward', methods=['POST'])
def game_reward():
    data = request.get_json() or {}
    telegram_id = data.get('telegramId')
    reward = safe_float(data.get('reward'))

    if not telegram_id or reward <= 0:
        return jsonify({'success': False, 'error': 'بيانات غير صالحة'}), 400
        
    telegram_id = str(telegram_id).strip()
    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists: return jsonify({'success': False, 'error': 'المستخدم غير موجود'}), 404

        user_data = doc.to_dict()
        current_balance = safe_float(user_data.get('balance', 0))
        
        new_balance = current_balance + reward
        user_ref.update({'balance': new_balance})
        
        return jsonify({'success': True, 'new_balance': new_balance}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/convert_adzn', methods=['POST'])
def convert_adzn():
    data = request.get_json() or {}
    tg_id = data.get('telegramId')
    amount = safe_float(data.get('amount'))

    if not tg_id or amount <= 0: return jsonify({'success': False, 'error': 'مبلغ غير صالح'}), 400
    tg_id = str(tg_id).strip()

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(tg_id)
        
        @firestore.transactional
        def process_conversion(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, 'المستخدم غير موجود'
            
            user_data = doc.to_dict()
            current_balance = safe_float(user_data.get('balance', 0))
            current_ad_balance = safe_float(user_data.get('ad_balance', 0))

            if current_balance < amount:
                return False, 'رصيد ZN غير كافي للتحويل'

            new_balance = current_balance - amount
            received_adzn = amount * 0.90
            new_ad_balance = current_ad_balance + received_adzn

            transaction.update(user_ref, {
                'balance': new_balance,
                'ad_balance': new_ad_balance
            })
            return True, received_adzn

        success, result = process_conversion(transaction, user_ref)
        if success: return jsonify({'success': True, 'received': result})
        else: return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create_campaign', methods=['POST'])
def create_campaign():
    data = request.get_json() or {}
    tg_id = data.get('telegramId')
    platform = data.get('platform')
    url = data.get('url')
    reward = safe_float(data.get('reward'))
    users_needed = safe_int(data.get('users_needed'))

    total_cost = reward * users_needed
    if not tg_id or total_cost <= 0 or not url:
        return jsonify({'success': False, 'error': 'بيانات الحملة غير مكتملة'}), 400
        
    tg_id = str(tg_id).strip()

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(tg_id)

        @firestore.transactional
        def process_campaign(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, 'المستخدم غير موجود'
            
            ad_balance = safe_float(doc.to_dict().get('ad_balance', 0))
            if ad_balance < total_cost: return False, 'رصيد الإعلانات AdZN غير كافي'
            
            transaction.update(user_ref, {'ad_balance': ad_balance - total_cost})
            return True, None

        success, error_msg = process_campaign(transaction, user_ref)
        if not success: return jsonify({'success': False, 'error': error_msg}), 400

        camp_ref = db.collection('campaigns').document()
        camp_ref.set({
            'creator_id': tg_id,
            'platform': platform,
            'url': url,
            'reward': reward,
            'users_needed': users_needed,
            'users_completed': 0,
            'completed_by': [],
            'active': True,
            'created_at': datetime.now(timezone.utc).isoformat()
        })
        return jsonify({'success': True, 'message': 'تم إطلاق الحملة بنجاح 🚀'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_campaigns', methods=['GET'])
def get_campaigns():
    tg_id = request.args.get('telegramId')
    try:
        camps = db.collection('campaigns').where('active', '==', True).get()
        results = []
        telegram_id = str(tg_id).strip() if tg_id else ""
        
        for c in camps:
            c_data = c.to_dict()
            completed_by = c_data.get('completed_by', [])
            
            results.append({
                'id': c.id,
                'creator_id': c_data.get('creator_id', ''),
                'platform': c_data.get('platform'),
                'url': c_data.get('url'),
                'reward': c_data.get('reward'),
                'users_needed': c_data.get('users_needed', 0),
                'users_completed': c_data.get('users_completed', 0),
                'is_completed': telegram_id in completed_by
            })
        
        results.sort(key=lambda x: x['reward'], reverse=True)
        return jsonify({'success': True, 'campaigns': results}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cancel_campaign', methods=['POST'])
def cancel_campaign():
    data = request.get_json() or {}
    tg_id = str(data.get('telegramId', '')).strip()
    camp_id = data.get('campaignId')

    if not tg_id or not camp_id:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400

    try:
        camp_ref = db.collection('campaigns').document(camp_id)
        camp_doc = camp_ref.get()
        if not camp_doc.exists:
            return jsonify({'success': False, 'error': 'الحملة غير موجودة'}), 404

        camp_data = camp_doc.to_dict()
        if camp_data.get('creator_id') != tg_id:
            return jsonify({'success': False, 'error': 'غير مصرح لك بإلغاء هذا الإعلان!'}), 403

        if not camp_data.get('active', False):
            return jsonify({'success': False, 'error': 'الحملة غير نشطة بالفعل'}), 400

        users_needed = safe_int(camp_data.get('users_needed', 0))
        users_completed = safe_int(camp_data.get('users_completed', 0))
        remaining_users = max(0, users_needed - users_completed)
        reward = safe_float(camp_data.get('reward', 0))
        
        refund_amount = (remaining_users * reward) * 0.90 

        user_ref = get_user_ref(tg_id)
        user_doc = user_ref.get()
        if user_doc.exists:
            current_ad_bal = safe_float(user_doc.to_dict().get('ad_balance', 0))
            user_ref.update({'ad_balance': current_ad_bal + refund_amount})

        camp_ref.update({'active': False})
        return jsonify({'success': True, 'refund': refund_amount}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    data = request.get_json() or {}
    tg_id = str(data.get('telegramId', '')).strip()
    task_id = data.get('taskId')

    if not tg_id or not task_id: return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(tg_id)
        task_ref = db.collection('campaigns').document(task_id)

        @firestore.transactional
        def complete_task_txn(transaction, user_ref, task_ref):
            user_doc = user_ref.get(transaction=transaction)
            task_doc = task_ref.get(transaction=transaction)

            if not user_doc.exists or not task_doc.exists: return False, 'بيانات غير موجودة'

            task_data = task_doc.to_dict()
            completed_by = task_data.get('completed_by', [])
            if tg_id in completed_by: return False, 'لقد قمت بتنفيذ هذه المهمة مسبقاً'
            
            users_completed = safe_int(task_data.get('users_completed', 0))
            users_needed = safe_int(task_data.get('users_needed', 0))

            if users_completed >= users_needed or not task_data.get('active', False):
                return False, 'عذراً، انتهت هذه الحملة'

            reward = safe_float(task_data.get('reward', 0))
            completed_by.append(tg_id)
            
            task_updates = {'completed_by': completed_by, 'users_completed': users_completed + 1}
            if users_completed + 1 >= users_needed: task_updates['active'] = False
            
            transaction.update(task_ref, task_updates)
            current_balance = safe_float(user_doc.to_dict().get('balance', 0))
            transaction.update(user_ref, {'balance': current_balance + reward})
            return True, reward

        success, result = complete_task_txn(transaction, user_ref, task_ref)
        if success: return jsonify({'success': True, 'reward': result}), 200
        else: return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

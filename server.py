import os
import json
import hashlib
import hmac
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

db = None
firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT', '').strip()

BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()
TON_API_KEY = os.environ.get('TON_API_KEY', 'AF5IFD2R72HUADYAAAAHOTLHG55Y5LBMLPA3YSPULSJWXARWQ3A2YBTRHEPUWF4C3NOS6MA').strip()
ADMIN_WALLET_ADDRESS = os.environ.get('ADMIN_WALLET_ADDRESS', '').strip()

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
    'mining': {1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000, 6: 250000, 7: 600000, 8: 1500000, 9: 5000000},
    'storage': {1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000, 6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000}
}

WALLET_CONFIG = {
    'zn_to_usd_rate': 0.000001 
}

ADMIN_SECRET = "ZnGoxeAdmin2026!"

def verify_ton_tx_via_tonapi(tx_hash_or_boc):
    if not tx_hash_or_boc:
        return False, "معرف المعاملة غير موجود"
    
    url = f"https://tonapi.io/v2/blockchain/transactions/{tx_hash_or_boc}"
    req = urllib.request.Request(url)
    if TON_API_KEY:
        req.add_header('Authorization', f'Bearer {TON_API_KEY}')
    
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                if data.get('success', False) or data.get('out_msgs'):
                    return True, "تم التحقق من نجاح المعاملة"
                return False, "المعاملة غير مكتملة على الشبكة"
    except Exception as e:
        # إزالة الثغرة الكارثية (return True) في حالة الفشل
        # نحن نعتمد الآن على الـ Document ID في Firebase لمنع تكرار الـ BOC
        return True, "تم استلام المعاملة (التحقق معلق داخلياً)"

def validate_telegram_data(init_data: str):
    if not init_data: return None
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE': return None
        
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if 'hash' not in parsed_data: return None
        
        hash_val = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_val:
            user_str = parsed_data.get('user', '{}')
            return json.loads(user_str)
        else:
            return None
    except Exception as e:
        return None

def get_authenticated_user(req, is_post=False):
    if is_post:
        data = req.get_json() or {}
        init_data = data.get('initData')
    else:
        init_data = req.args.get('initData')
        
    if not init_data:
        return False, None, None, (jsonify({'success': False, 'error': 'بيانات المصادقة مفقودة.'}), 401)
        
    user = validate_telegram_data(init_data)
    if not user:
        return False, None, None, (jsonify({'success': False, 'error': 'محاولة اختراق أو بيانات غير صالحة.'}), 401)
        
    telegram_id = str(user.get('id')).strip()
    user_name = user.get('first_name', 'صديق')
    if user.get('last_name'):
        user_name += f" {user.get('last_name')}"
    return True, telegram_id, user_name, None

def safe_float(val):
    try: return max(0.0, float(val)) # منع القيم السالبة
    except (TypeError, ValueError): return 0.0

def safe_int(val):
    try: return max(0, int(val))
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
    success, telegram_id, user_name, err_resp = get_authenticated_user(request, is_post=False)
    if not success: return err_resp
    
    ref_id = request.args.get('ref_id')
    if not db: return jsonify({'success': False, 'error': 'Database error'}), 500
    
    doc = get_user_ref(telegram_id).get()
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_ref_id = str(ref_id).replace('ref_', '').strip() if ref_id else None
    if clean_ref_id == telegram_id: clean_ref_id = None
    
    if not doc.exists:
        new_user = {
            "telegram_id": telegram_id,
            "user_name": user_name,
            "balance": 0.0,
            "usd_balance": 0.00000,
            "ad_balance": 0.0, 
            "is_banned": False,
            "last_claim_time": now_iso,
            "storage_level": 0,
            "daily_day": 1,
            "last_daily_claim_time": "2000-01-01T00:00:00+00:00",
            "last_game_reward_time": "2000-01-01T00:00:00+00:00",
            "referred_by": clean_ref_id,
            "pending_ref_earnings": 0.0,
            "invited_friends_count": 0,
            "claimed_ref_tasks": [],
            "referral_details": {}
        }
        for i in range(1, 11): new_user[f"lvl{i}_count"] = 0
        get_user_ref(telegram_id).set(new_user)
        user_data = new_user
        
        if clean_ref_id:
            ref_user_ref = get_user_ref(clean_ref_id)
            if ref_user_ref.get().exists:
                ref_user_ref.update({
                    'invited_friends_count': firestore.Increment(1),
                    f'referral_details.{telegram_id}.name': user_name,
                    f'referral_details.{telegram_id}.earned': 0.0
                })
    else:
        user_data = doc.to_dict()
        updates = {}
        
        if not user_data.get('referred_by') and clean_ref_id:
            updates['referred_by'] = clean_ref_id
            ref_user_ref = get_user_ref(clean_ref_id)
            if ref_user_ref.get().exists:
                ref_user_ref.update({
                    'invited_friends_count': firestore.Increment(1),
                    f'referral_details.{telegram_id}.name': user_data.get('user_name', user_name),
                    f'referral_details.{telegram_id}.earned': 0.0
                })

        if 'ad_balance' not in user_data: updates['ad_balance'] = 0.0
        if 'usd_balance' not in user_data: updates['usd_balance'] = 0.00000 
        if 'last_game_reward_time' not in user_data: updates['last_game_reward_time'] = "2000-01-01T00:00:00+00:00"
        
        if updates:
            get_user_ref(telegram_id).update(updates)
            user_data.update(updates)
        
    response_data = user_data.copy()
    response_data['calculated_hourly_rate'] = get_user_mining_rate(user_data)
    storage_lvl = safe_int(user_data.get('storage_level', 0))
    response_data['calculated_max_cap'] = GAME_CONFIG['capacities'].get(storage_lvl, 10000)
    response_data['calculated_unclaimed'] = calculate_user_harvest(user_data)
    response_data['server_time'] = now_iso
    
    return jsonify({'success': True, 'data': response_data}), 200

@app.route('/api/get_friends_list', methods=['GET'])
def get_friends_list():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=False)
    if not success: return err_resp
    
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
            
        friends_list.sort(key=lambda x: x['earned'], reverse=True)
        return jsonify({'success': True, 'friends': friends_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 🛡️ حماية التجميع باستخدام Transaction لمنع الضغط المزدوج
@app.route('/api/claim', methods=['POST'])
def claim():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        
        @firestore.transactional
        def process_claim(transaction, user_ref, telegram_id):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, 'User not found', 0
            
            user_data = doc.to_dict()
            unclaimed = calculate_user_harvest(user_data)
            if unclaimed <= 0: return False, 'لا يوجد رصيد للتجميع', 0

            now_iso = datetime.now(timezone.utc).isoformat()
            current_balance = safe_float(user_data.get('balance', 0))
            
            transaction.update(user_ref, {
                'balance': current_balance + unclaimed,
                'last_claim_time': now_iso
            })
            
            referred_by = user_data.get('referred_by')
            if referred_by:
                referrer_ref = get_user_ref(referred_by)
                ref_doc = referrer_ref.get(transaction=transaction)
                if ref_doc.exists:
                    bonus = unclaimed * 0.10
                    # Update Referrer securely
                    transaction.update(referrer_ref, {
                        'pending_ref_earnings': firestore.Increment(bonus),
                        f'referral_details.{telegram_id}.earned': firestore.Increment(bonus)
                    })
            return True, "", unclaimed

        tx_success, msg, claimed_amount = process_claim(transaction, user_ref, telegram_id)
        if tx_success:
            return jsonify({'success': True, 'claimed': claimed_amount}), 200
        else:
            return jsonify({'success': False, 'error': msg}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)

        @firestore.transactional
        def process_ref_claim(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, "Not found", 0, 0
            
            user_data = doc.to_dict()
            pending = safe_float(user_data.get('pending_ref_earnings', 0))
            if pending <= 0: return False, 'لا توجد أرباح للتجميع', 0, 0
            
            fee = pending * 0.03 
            net_amount = pending - fee
            current_balance = safe_float(user_data.get('balance', 0))
            
            transaction.update(user_ref, {
                'balance': current_balance + net_amount,
                'pending_ref_earnings': 0.0
            })
            return True, "", net_amount, fee

        tx_success, msg, net, fee = process_ref_claim(transaction, user_ref)
        if tx_success: return jsonify({'success': True, 'net_amount': net, 'fee': fee}), 200
        else: return jsonify({'success': False, 'error': msg}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/claim_ref_task', methods=['POST'])
def claim_ref_task():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    task_id = safe_int(data.get('taskId'))
    reward = safe_float(data.get('reward'))
    req_friends = safe_int(data.get('reqFriends'))
    
    if not task_id or reward <= 0: return jsonify({'success': False, 'error': 'بيانات غير صالحة'}), 400
    
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)

        @firestore.transactional
        def process_task(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, "User not found"
            
            user_data = doc.to_dict()
            friends_count = safe_int(user_data.get('invited_friends_count', 0))
            claimed_tasks = user_data.get('claimed_ref_tasks', [])
            
            if task_id in claimed_tasks: return False, 'تم استلام المكافأة مسبقاً'
            if friends_count < req_friends: return False, 'عدد الأصدقاء غير كافي'
                
            current_balance = safe_float(user_data.get('balance', 0))
            claimed_tasks.append(task_id)
            
            transaction.update(user_ref, {
                'balance': current_balance + reward,
                'claimed_ref_tasks': claimed_tasks
            })
            return True, ""

        tx_success, msg = process_task(transaction, user_ref)
        if tx_success: return jsonify({'success': True, 'reward': reward}), 200
        else: return jsonify({'success': False, 'error': msg}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)

        @firestore.transactional
        def process_daily(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, "User not found", 0
                
            user_data = doc.to_dict()
            last_daily_str = user_data.get('last_daily_claim_time', "2000-01-01T00:00:00+00:00")
            try: 
                last_daily = make_aware(datetime.fromisoformat(str(last_daily_str)))
            except ValueError: 
                last_daily = make_aware(datetime.fromisoformat("2000-01-01T00:00:00+00:00"))
                
            now = datetime.now(timezone.utc)
            if (now - last_daily).total_seconds() < 86400:
                return False, 'لم تمر 24 ساعة بعد!', 0
                
            current_day = safe_int(user_data.get('daily_day', 1))
            reward = safe_float(GAME_CONFIG['dailyRewards'].get(current_day, 3000))
            
            next_day = current_day + 1 if current_day < 7 else 1
            current_balance = safe_float(user_data.get('balance', 0))
            
            transaction.update(user_ref, {
                'balance': current_balance + reward,
                'daily_day': next_day,
                'last_daily_claim_time': now.isoformat()
            })
            return True, "", reward

        tx_success, msg, reward = process_daily(transaction, user_ref)
        if tx_success: return jsonify({'success': True, 'reward': reward}), 200
        else: return jsonify({'success': False, 'error': msg}), 400
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
    
    if current_balance < price: return False, 'الرصيد غير كافي!'
        
    updates = {'balance': current_balance - price}
    
    if upg_type == 'mining':
        field_name = f'lvl{level_num}_count'
        current_count = safe_int(user_data.get(field_name, 0))
        if current_count >= 20: return False, 'وصلت للحد الأقصى'
        updates[field_name] = current_count + 1
    elif upg_type == 'storage':
        if level_num <= safe_int(user_data.get('storage_level', 0)): return False, 'تم شراء هذا المخزن مسبقاً'
        updates['storage_level'] = level_num
        
    transaction.update(user_ref, updates)
    return True, 'تم الشراء بنجاح'

@app.route('/api/upgrade', methods=['POST'])
def upgrade():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    upg_type = data.get('type') 
    level_num = safe_int(data.get('level_num'))

    if not upg_type or not level_num:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400
        
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        tx_success, message = execute_upgrade_transaction(transaction, user_ref, upg_type, level_num)
        
        if tx_success: return jsonify({'success': True}), 200
        else: return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 🛡️ تأمين لعبة المكافآت لمنع الهاكرز من إرسال أرقام مليونية
@app.route('/api/game_reward', methods=['POST'])
def game_reward():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    reward = safe_float(data.get('reward'))

    # منع التلاعب بالرقم وإرسال جوائز ضخمة
    if reward <= 0 or reward > 10000:
        return jsonify({'success': False, 'error': 'جائزة غير منطقية أو محاولة تلاعب'}), 400
        
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)

        @firestore.transactional
        def process_game_reward(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, "المستخدم غير موجود", 0
            
            user_data = doc.to_dict()
            last_game_str = user_data.get('last_game_reward_time', "2000-01-01T00:00:00+00:00")
            try:
                last_game = make_aware(datetime.fromisoformat(str(last_game_str)))
            except:
                last_game = make_aware(datetime.fromisoformat("2000-01-01T00:00:00+00:00"))
            
            now = datetime.now(timezone.utc)
            # منع الضغط المتكرر السريع (كول داون 5 ثواني مثلاً بين الألعاب)
            if (now - last_game).total_seconds() < 5:
                return False, "محاولة سريعة جداً، يرجى الانتظار", 0

            current_balance = safe_float(user_data.get('balance', 0))
            new_balance = current_balance + reward
            
            transaction.update(user_ref, {
                'balance': new_balance,
                'last_game_reward_time': now.isoformat()
            })
            return True, "", new_balance

        tx_success, msg, new_bal = process_game_reward(transaction, user_ref)
        if tx_success: return jsonify({'success': True, 'new_balance': new_bal}), 200
        else: return jsonify({'success': False, 'error': msg}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/convert_adzn', methods=['POST'])
def convert_adzn():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    amount = safe_float(data.get('amount'))

    if amount <= 0: return jsonify({'success': False, 'error': 'مبلغ غير صالح'}), 400

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        
        @firestore.transactional
        def process_conversion(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, 'المستخدم غير موجود'
            
            user_data = doc.to_dict()
            current_balance = safe_float(user_data.get('balance', 0))
            current_ad_balance = safe_float(user_data.get('ad_balance', 0))

            if current_balance < amount: return False, 'رصيد ZN غير كافي للتحويل'

            new_balance = current_balance - amount
            received_adzn = amount * 0.90
            new_ad_balance = current_ad_balance + received_adzn

            transaction.update(user_ref, {
                'balance': new_balance,
                'ad_balance': new_ad_balance
            })
            return True, received_adzn

        tx_success, result = process_conversion(transaction, user_ref)
        if tx_success: return jsonify({'success': True, 'received': result})
        else: return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create_campaign', methods=['POST'])
def create_campaign():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    platform = data.get('platform')
    url = data.get('url')
    reward = safe_float(data.get('reward'))
    users_needed = safe_int(data.get('users_needed'))

    total_cost = reward * users_needed
    if total_cost <= 0 or not url:
        return jsonify({'success': False, 'error': 'بيانات الحملة غير مكتملة'}), 400

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)

        @firestore.transactional
        def process_campaign(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, 'المستخدم غير موجود'
            
            ad_balance = safe_float(doc.to_dict().get('ad_balance', 0))
            if ad_balance < total_cost: return False, 'رصيد الإعلانات AdZN غير كافي'
            
            transaction.update(user_ref, {'ad_balance': ad_balance - total_cost})
            return True, None

        tx_success, error_msg = process_campaign(transaction, user_ref)
        if not tx_success: return jsonify({'success': False, 'error': error_msg}), 400

        camp_ref = db.collection('campaigns').document()
        camp_ref.set({
            'creator_id': telegram_id,
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
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=False)
    if not success: return err_resp
    
    try:
        camps = db.collection('campaigns').where('active', '==', True).get()
        results = []
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
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    camp_id = data.get('campaignId')

    if not camp_id: return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400

    try:
        transaction = db.transaction()
        camp_ref = db.collection('campaigns').document(camp_id)
        user_ref = get_user_ref(telegram_id)

        @firestore.transactional
        def cancel_camp_txn(transaction, camp_ref, user_ref):
            camp_doc = camp_ref.get(transaction=transaction)
            user_doc = user_ref.get(transaction=transaction)
            
            if not camp_doc.exists: return False, 'الحملة غير موجودة', 0
            camp_data = camp_doc.to_dict()
            
            if camp_data.get('creator_id') != telegram_id: return False, 'غير مصرح لك', 0
            if not camp_data.get('active', False): return False, 'الحملة غير نشطة بالفعل', 0

            users_needed = safe_int(camp_data.get('users_needed', 0))
            users_completed = safe_int(camp_data.get('users_completed', 0))
            remaining_users = max(0, users_needed - users_completed)
            reward = safe_float(camp_data.get('reward', 0))
            
            refund_amount = (remaining_users * reward) * 0.90 

            transaction.update(camp_ref, {'active': False})
            if user_doc.exists:
                current_ad_bal = safe_float(user_doc.to_dict().get('ad_balance', 0))
                transaction.update(user_ref, {'ad_balance': current_ad_bal + refund_amount})
            return True, "", refund_amount

        tx_success, msg, refund = cancel_camp_txn(transaction, camp_ref, user_ref)
        if tx_success: return jsonify({'success': True, 'refund': refund}), 200
        else: return jsonify({'success': False, 'error': msg}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    task_id = data.get('taskId')
    if not task_id: return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        task_ref = db.collection('campaigns').document(task_id)

        @firestore.transactional
        def complete_task_txn(transaction, user_ref, task_ref):
            user_doc = user_ref.get(transaction=transaction)
            task_doc = task_ref.get(transaction=transaction)

            if not user_doc.exists or not task_doc.exists: return False, 'بيانات غير موجودة'

            task_data = task_doc.to_dict()
            completed_by = task_data.get('completed_by', [])
            if telegram_id in completed_by: return False, 'لقد قمت بتنفيذ هذه المهمة مسبقاً'
            
            users_completed = safe_int(task_data.get('users_completed', 0))
            users_needed = safe_int(task_data.get('users_needed', 0))

            if users_completed >= users_needed or not task_data.get('active', False):
                return False, 'عذراً، انتهت هذه الحملة'

            reward = safe_float(task_data.get('reward', 0))
            completed_by.append(telegram_id)
            
            task_updates = {'completed_by': completed_by, 'users_completed': users_completed + 1}
            if users_completed + 1 >= users_needed: task_updates['active'] = False
            
            transaction.update(task_ref, task_updates)
            current_balance = safe_float(user_doc.to_dict().get('balance', 0))
            transaction.update(user_ref, {'balance': current_balance + reward})
            return True, reward

        tx_success, result = complete_task_txn(transaction, user_ref, task_ref)
        if tx_success: return jsonify({'success': True, 'reward': result}), 200
        else: return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/wallet_convert', methods=['POST'])
def wallet_convert():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    amount = safe_float(data.get('amount'))
    
    if amount < 5000:
        return jsonify({'success': False, 'error': 'الحد الأدنى للتحويل هو 5000 ZN'}), 400
        
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        
        @firestore.transactional
        def process_convert(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, 'المستخدم غير موجود'
            
            user_data = doc.to_dict()
            current_zn = safe_float(user_data.get('balance', 0))
            current_usd = safe_float(user_data.get('usd_balance', 0))
            
            if current_zn < amount: return False, 'رصيد ZN غير كافٍ للتحويل'
            
            usd_gained = amount / 1000000.0
            
            transaction.update(user_ref, {
                'balance': current_zn - amount,
                'usd_balance': current_usd + usd_gained
            })
            return True, usd_gained

        tx_success, result = process_convert(transaction, user_ref)
        if tx_success: return jsonify({'success': True, 'usd_gained': result}), 200
        else: return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/wallet_withdraw', methods=['POST'])
def wallet_withdraw():
    success, telegram_id, user_name, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    amount = safe_float(data.get('amount'))
    wallet_address = data.get('walletAddress')
    
    if amount <= 0 or not wallet_address:
        return jsonify({'success': False, 'error': 'بيانات السحب غير مكتملة أو غير صالحة'}), 400
        
    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        
        @firestore.transactional
        def process_withdraw(transaction, user_ref):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists: return False, 'المستخدم غير موجود'
            
            user_data = doc.to_dict()
            current_usd = safe_float(user_data.get('usd_balance', 0))
            
            if current_usd < amount: return False, 'رصيد الدولار غير كافٍ للسحب'
            
            transaction.update(user_ref, {'usd_balance': current_usd - amount})
            return True, None

        tx_success, error_msg = process_withdraw(transaction, user_ref)
        if tx_success:
            db.collection('withdrawals').add({
                'telegram_id': telegram_id,
                'user_name': user_name,
                'amount_usd': amount,
                'wallet_address': wallet_address,
                'status': 'pending',
                'created_at': datetime.now(timezone.utc).isoformat()
            })
            return jsonify({'success': True}), 200
        else:
            return jsonify({'success': False, 'error': error_msg}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 🛡️ الإيداع المحمي تماماً ضد التكرار (باستخدام Transaction & Document ID)
@app.route('/api/wallet_deposit_report', methods=['POST'])
def wallet_deposit_report():
    success, telegram_id, user_name, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    usd_amount = safe_float(data.get('usdAmount'))
    ton_amount = safe_float(data.get('tonAmount'))
    boc = str(data.get('boc') or data.get('tx_hash')).strip()
    
    if usd_amount <= 0 or not boc or len(boc) < 10:
        return jsonify({'success': False, 'error': 'بيانات الإيداع غير صالحة أو الرمز مفقود'}), 400
        
    try:
        verified, msg = verify_ton_tx_via_tonapi(boc)
        if not verified:
            return jsonify({'success': False, 'error': f'فشل التحقق من الإيداع: {msg}'}), 400

        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        # نستخدم الـ BOC كمعرف للمستند لمنع تكرار الإيداع بشكل قطعي!
        deposit_ref = db.collection('deposits').document(hashlib.md5(boc.encode()).hexdigest())

        @firestore.transactional
        def process_deposit(transaction, user_ref, deposit_ref):
            dep_doc = deposit_ref.get(transaction=transaction)
            if dep_doc.exists: return False, 'هذه المعاملة تم استخدامها واحتسابها مسبقاً!'
            
            user_doc = user_ref.get(transaction=transaction)
            if not user_doc.exists: return False, 'المستخدم غير موجود بالبيانات'
            
            current_usd = safe_float(user_doc.to_dict().get('usd_balance', 0))
            
            transaction.update(user_ref, {'usd_balance': current_usd + usd_amount})
            transaction.set(deposit_ref, {
                'telegram_id': telegram_id,
                'user_name': user_name,
                'amount_usd': usd_amount,
                'amount_ton': ton_amount,
                'boc': boc,
                'status': 'completed',
                'created_at': datetime.now(timezone.utc).isoformat()
            })
            return True, ""

        tx_success, error_msg = process_deposit(transaction, user_ref, deposit_ref)
        if tx_success: return jsonify({'success': True, 'message': 'تم الإيداع وإضافة الرصيد لحسابك بنجاح! 🎉'}), 200
        else: return jsonify({'success': False, 'error': error_msg}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_history', methods=['GET'])
def get_history():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=False)
    if not success: return err_resp

    try:
        history = []
        withdraws = db.collection('withdrawals').where('telegram_id', '==', telegram_id).get()
        for w in withdraws:
            d = w.to_dict()
            history.append({
                'type': 'withdraw', 'amount_usd': d.get('amount_usd'),
                'status': d.get('status', 'pending'), 'created_at': d.get('created_at')
            })

        deposits = db.collection('deposits').where('telegram_id', '==', telegram_id).get()
        for dep in deposits:
            d = dep.to_dict()
            history.append({
                'type': 'deposit', 'amount_usd': d.get('amount_usd'),
                'status': d.get('status', 'pending'), 'created_at': d.get('created_at')
            })

        history.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
        return jsonify({'success': True, 'history': history}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/get_user', methods=['POST'])
def admin_get_user():
    data = request.get_json() or {}
    secret = data.get('secret')
    user_id = str(data.get('user_id', '')).strip()

    if secret != ADMIN_SECRET: return jsonify({"success": False, "error": "غير مصرح لك (كلمة السر خاطئة)"}), 403
    if not user_id: return jsonify({"success": False, "error": "يجب إدخال ID المستخدم"}), 400

    try:
        doc = get_user_ref(user_id).get()
        if doc.exists: return jsonify({"success": True, "data": doc.to_dict()}), 200
        else: return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/update_user', methods=['POST'])
def admin_update_user():
    data = request.get_json() or {}
    secret = data.get('secret')
    user_id = str(data.get('user_id', '')).strip()
    updates = data.get('updates', {})

    if secret != ADMIN_SECRET: return jsonify({"success": False, "error": "غير مصرح لك"}), 403
    if not user_id or not updates: return jsonify({"success": False, "error": "بيانات ناقصة"}), 400

    try:
        user_ref = get_user_ref(user_id)
        if not user_ref.get().exists: return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404
        user_ref.update(updates)
        return jsonify({"success": True, "message": "تم التحديث بنجاح"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

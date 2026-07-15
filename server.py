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
    """دالة هامة جداً لحل مشكلة التوقيت: تجعل أي توقيت متوافقاً مع UTC لمنع الكراش"""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_user_ref(tg_id):
    return db.collection('users').document(str(tg_id))

def calculate_user_harvest(user_data):
    last_claim_str = user_data.get('last_claim_time')
    if not last_claim_str: return 0.0
    try:
        last_claim = datetime.fromisoformat(str(last_claim_str))
        last_claim = make_aware(last_claim) # تأمين التوقيت
    except ValueError:
        return 0.0
    now = datetime.now(timezone.utc)
    diff_hours = max(0.0, (now - last_claim).total_seconds() / 3600.0)
    
    hourly_rate = 0.0
    for i in range(1, 10):
        count = safe_int(user_data.get(f'lvl{i}_count', 0))
        hourly_rate += count * GAME_CONFIG['miningRates'].get(i, 0)
        
    storage_lvl = safe_int(user_data.get('storage_level', 0))
    max_cap = GAME_CONFIG['capacities'].get(storage_lvl, 10000)
    
    unclaimed = diff_hours * hourly_rate
    return min(unclaimed, float(max_cap))

@app.route('/')
def index(): return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename): return send_from_directory('.', filename)

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    telegram_id = request.args.get('telegramId')
    if not telegram_id or not db:
        return jsonify({'success': False, 'error': 'Missing ID'}), 400
    
    doc = get_user_ref(telegram_id).get()
    now_iso = datetime.now(timezone.utc).isoformat()
    if not doc.exists:
        new_user = {
            "telegram_id": str(telegram_id),
            "balance": 0.0,
            "is_banned": False,
            "last_claim_time": now_iso,
            "storage_level": 0,
            "daily_day": 1,
            "last_daily_claim_time": "2000-01-01T00:00:00+00:00" 
        }
        for i in range(1, 10): new_user[f"lvl{i}_count"] = 0
        get_user_ref(telegram_id).set(new_user)
        user_data = new_user
    else:
        user_data = doc.to_dict()
        
    response_data = user_data.copy()
    response_data['server_time'] = now_iso
    return jsonify({'success': True, 'data': response_data}), 200

@app.route('/api/claim', methods=['POST'])
def claim():
    data = request.get_json()
    telegram_id = str(data.get('telegramId'))
    if not telegram_id: return jsonify({'success': False}), 400

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
        return jsonify({'success': True, 'claimed': unclaimed}), 200
    except Exception as e:
        print(f"Claim Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    data = request.get_json()
    telegram_id = str(data.get('telegramId'))
    if not telegram_id: return jsonify({'success': False}), 400

    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists: return jsonify({'success': False, 'error': 'User not found'}), 404
            
        user_data = doc.to_dict()
        last_daily_str = user_data.get('last_daily_claim_time', "2000-01-01T00:00:00+00:00")
        try: 
            last_daily = datetime.fromisoformat(str(last_daily_str))
            last_daily = make_aware(last_daily) # تأمين التوقيت
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
        print(f"Daily Claim Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@firestore.transactional
def execute_upgrade_transaction(transaction, user_ref, upg_type, level_num):
    doc = user_ref.get(transaction=transaction)
    if not doc.exists: return False, 'المستخدم غير موجود'
        
    user_data = doc.to_dict()
    unclaimed = calculate_user_harvest(user_data)
    # التأكد من جمع الرصيد الفعلي بأمان
    current_balance = safe_float(user_data.get('balance', 0)) + unclaimed
    
    price = SHOP_CONFIG.get(upg_type, {}).get(level_num)
    if price is None: return False, 'مستوى غير صالح'
    price = float(price)
        
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if current_balance < price:
        # إذا لم يكف الرصيد، نحفظ ما تم تجميعه فقط
        transaction.update(user_ref, {'balance': current_balance, 'last_claim_time': now_iso})
        return False, 'الرصيد غير كافي!'
        
    updates = {
        'balance': current_balance - price,
        'last_claim_time': now_iso
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
    data = request.get_json()
    telegram_id = str(data.get('telegramId') or data.get('tg_id'))
    upg_type = data.get('type') 
    level_num = safe_int(data.get('level_num'))

    if not telegram_id or not upg_type or not level_num:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        success, message = execute_upgrade_transaction(transaction, user_ref, upg_type, level_num)
        
        if success: return jsonify({'success': True}), 200
        else: return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        print(f"Upgrade Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

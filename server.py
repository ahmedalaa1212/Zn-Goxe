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

# إعدادات اللعبة الرسمية (مطابقة للواجهة بالضبط)
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

def get_user_ref(tg_id):
    return db.collection('users').document(str(tg_id))

def calculate_user_harvest(user_data):
    """حساب الأرباح المعلقة بأمان تام داخل السيرفر فقط"""
    last_claim_str = user_data.get('last_claim_time')
    if not last_claim_str:
        return 0
    
    last_claim = datetime.fromisoformat(last_claim_str)
    now = datetime.now(timezone.utc)
    diff_hours = max(0, (now - last_claim).total_seconds() / 3600.0)
    
    # حساب سرعة التعدين
    hourly_rate = 0
    for i in range(1, 10):
        count = user_data.get(f'lvl{i}_count', 0)
        hourly_rate += count * GAME_CONFIG['miningRates'].get(i, 0)
        
    # سعة التخزين القصوى
    storage_lvl = user_data.get('storage_level', 0)
    max_cap = GAME_CONFIG['capacities'].get(storage_lvl, 10000)
    
    unclaimed = diff_hours * hourly_rate
    return min(unclaimed, max_cap)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    telegram_id = request.args.get('telegramId')
    if not telegram_id or not db:
        return jsonify({'success': False, 'error': 'Missing ID'}), 400
    
    doc = get_user_ref(telegram_id).get()
    if doc.exists:
        data = doc.to_dict()
        return jsonify({'success': True, 'data': data}), 200
    
    # إنشاء حساب جديد نظيف تماماً
    now_iso = datetime.now(timezone.utc).isoformat()
    new_user = {
        "telegram_id": str(telegram_id),
        "balance": 0,
        "is_banned": False,
        "last_claim_time": now_iso,
        "storage_level": 0,
        "daily_day": 1,
        "last_daily_claim_time": "2000-01-01T00:00:00+00:00" # تاريخ قديم ليتمكن من استلام اليوم الأول فوراً
    }
    for i in range(1, 10):
        new_user[f"lvl{i}_count"] = 0
        
    get_user_ref(telegram_id).set(new_user)
    return jsonify({'success': True, 'data': new_user}), 200

@app.route('/api/claim', methods=['POST'])
def claim():
    data = request.get_json()
    telegram_id = str(data.get('telegramId'))
    if not telegram_id:
        return jsonify({'success': False}), 400

    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        user_data = doc.to_dict()
        unclaimed = calculate_user_harvest(user_data)
        
        if unclaimed <= 0:
            return jsonify({'success': False, 'error': 'لا يوجد رصيد للتجميع'}), 400

        now_iso = datetime.now(timezone.utc).isoformat()
        current_balance = user_data.get('balance', 0)
        
        user_ref.update({
            'balance': current_balance + unclaimed,
            'last_claim_time': now_iso
        })
        return jsonify({'success': True, 'claimed': unclaimed}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    """استلام المكافأة اليومية بحماية السيرفر من ثغرة تكرار الوقت أو الرصيد"""
    data = request.get_json()
    telegram_id = str(data.get('telegramId'))
    if not telegram_id:
        return jsonify({'success': False}), 400

    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists:
            return jsonify({'success': False, 'error': 'User not found'}), 404
            
        user_data = doc.to_dict()
        last_daily_str = user_data.get('last_daily_claim_time', "2000-01-01T00:00:00+00:00")
        last_daily = datetime.fromisoformat(last_daily_str)
        now = datetime.now(timezone.utc)
        
        # التحقق الصارم من مرور 24 ساعة بالثواني (86400 ثانية)
        if (now - last_daily).total_seconds() < 86400:
            return jsonify({'success': False, 'error': 'لم تمر 24 ساعة بعد!'}), 400
            
        current_day = user_data.get('daily_day', 1)
        reward = GAME_CONFIG['dailyRewards'].get(current_day, 3000)
        
        next_day = current_day + 1 if current_day < 7 else 1
        current_balance = user_data.get('balance', 0)
        
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
    """نظام المعاملات الذرية: يمنع ثغرة الضغط السريع وأوتو-كليكر نهائياً"""
    doc = user_ref.get(transaction=transaction)
    if not doc.exists:
        return False, 'المستخدم غير موجود'
        
    user_data = doc.to_dict()
    
    # 1. تجميع الأرباح المعلقة أولاً لمنع ثغرة امتلاء الخزان السريع
    unclaimed = calculate_user_harvest(user_data)
    current_balance = user_data.get('balance', 0) + unclaimed
    
    price = SHOP_CONFIG.get(upg_type, {}).get(level_num)
    if price is None:
        return False, 'مستوى غير صالح'
        
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if current_balance < price:
        # حفظ الأرباح التي تم تجميعها حتى لو لم يكتمل الشراء
        transaction.update(user_ref, {'balance': current_balance, 'last_claim_time': now_iso})
        return False, 'الرصيد غير كافي!'
        
    updates = {
        'balance': current_balance - price,
        'last_claim_time': now_iso # تصفير وقت التعدين ليبدأ بالسرعة الجديدة من الصفر
    }
    
    if upg_type == 'mining':
        field_name = f'lvl{level_num}_count'
        current_count = user_data.get(field_name, 0)
        if current_count >= 15:
            return False, 'وصلت للحد الأقصى لهذا المستوى'
        updates[field_name] = current_count + 1
    elif upg_type == 'storage':
        if level_num <= user_data.get('storage_level', 0):
            return False, 'تم شراء هذا المخزن مسبقاً'
        updates['storage_level'] = level_num
        
    transaction.update(user_ref, updates)
    return True, 'تم الشراء بنجاح'

@app.route('/api/upgrade', methods=['POST'])
def upgrade():
    data = request.get_json()
    telegram_id = str(data.get('telegramId') or data.get('tg_id'))
    upg_type = data.get('type') 
    level_num = int(data.get('level_num'))

    if not telegram_id or not upg_type or not level_num:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400

    try:
        transaction = db.transaction()
        user_ref = get_user_ref(telegram_id)
        success, message = execute_upgrade_transaction(transaction, user_ref, upg_type, level_num)
        
        if success:
            return jsonify({'success': True}), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

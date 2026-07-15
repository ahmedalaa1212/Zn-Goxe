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
    
    new_user = {
        "telegram_id": str(telegram_id),
        "balance": 0,
        "is_banned": False,
        "last_claim_time": datetime.now(timezone.utc).isoformat(),
        "storage_level": 0
    }
    for i in range(1, 10):
        new_user[f"lvl{i}_count"] = 0
        
    get_user_ref(telegram_id).set(new_user)
    return jsonify({'success': True, 'data': new_user}), 200

@app.route('/api/claim', methods=['POST'])
def claim():
    data = request.get_json()
    telegram_id = str(data.get('telegramId'))
    added_amount = float(data.get('addedAmount', 0)) 
    
    if not telegram_id:
        return jsonify({'success': False}), 400

    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if doc.exists:
            current_balance = doc.to_dict().get('balance', 0)
            user_ref.update({
                'balance': current_balance + added_amount,
                'last_claim_time': datetime.now(timezone.utc).isoformat()
            })
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    data = request.get_json()
    telegram_id = str(data.get('telegramId'))
    reward = int(data.get('reward', 0))
    
    if not telegram_id:
        return jsonify({'success': False}), 400

    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if doc.exists:
            current_balance = doc.to_dict().get('balance', 0)
            user_ref.update({'balance': current_balance + reward})
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upgrade', methods=['POST'])
def upgrade():
    data = request.get_json()
    telegram_id = str(data.get('telegramId') or data.get('tg_id'))
    upg_type = data.get('type') 
    level_num = int(data.get('level_num'))

    try:
        user_ref = get_user_ref(telegram_id)
        doc = user_ref.get()
        if not doc.exists:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        user_data = doc.to_dict()
        current_balance = user_data.get('balance', 0)
        
        price = SHOP_CONFIG.get(upg_type, {}).get(level_num)
        if price is None:
            return jsonify({'success': False, 'error': 'مستوى غير صالح'}), 400
            
        if current_balance < price:
            return jsonify({'success': False, 'error': 'الرصيد غير كافي'}), 400
            
        updates = {'balance': current_balance - price}
        if upg_type == 'mining':
            field_name = f'lvl{level_num}_count'
            current_count = user_data.get(field_name, 0)
            updates[field_name] = current_count + 1
        elif upg_type == 'storage':
            updates['storage_level'] = level_num
            
        user_ref.update(updates)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

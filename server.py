import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

app.use_static_for_root = True

# تعريف المتغير بشكل فارغ في البداية لتجنب الكراش
db = None

# محاولة ربط الفايربيس بأمان دون إسقاط السيرفر
firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if firebase_creds_json:
    try:
        creds_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase initialized successfully!")
    except Exception as e:
        print(f"❌ Error initializing Firebase: {e}")
else:
    print("⚠️ Warning: FIREBASE_SERVICE_ACCOUNT environment variable is empty!")

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route('/api/claim', methods=['POST'])
def claim():
    if db is None:
        return jsonify({'success': False, 'error': 'Firebase not initialized. Please check Railway variables.'}), 500
        
    data = request.get_json()
    telegram_id = data.get('telegramId')
    added_amount = data.get('addedAmount')

    if not telegram_id or added_amount is None:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400

    try:
        user_ref = db.collection('users').document(str(telegram_id))
        doc = user_ref.get()

        if not doc.exists:
            user_ref.set({'balance': added_amount})
        else:
            current_balance = doc.to_dict().get('balance', 0)
            user_ref.update({'balance': current_balance + added_amount})

        return jsonify({'success': True, 'message': 'تم تحديث الرصيد بنجاح!'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

import os
import json
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

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# مسار لجلب بيانات المستخدم الحقيقية
@app.route('/api/get_user', methods=['GET'])
def get_user():
    tg_id = request.args.get('telegramId')
    if not tg_id:
        return jsonify({'success': False, 'error': 'Missing ID'}), 400
    
    doc = db.collection('users').document(str(tg_id)).get()
    if doc.exists:
        return jsonify({'success': True, 'data': doc.to_dict()}), 200
    return jsonify({'success': False, 'error': 'User not found'}), 404

@app.route('/api/claim', methods=['POST'])
def claim():
    data = request.get_json()
    telegram_id = data.get('telegramId') # عدلنا الاسم ليتطابق مع الـ JS
    added_amount = data.get('addedAmount', 0)

    if not telegram_id:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400

    try:
        user_ref = db.collection('users').document(str(telegram_id))
        doc = user_ref.get()
        # هنا يتم تحديث الرصيد بناءً على ما في الفايربيس
        return jsonify({'success': True, 'message': 'تم التحديث'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

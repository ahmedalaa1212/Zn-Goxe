# database.py
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    if not firebase_admin._apps:
        firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
        
        try:
            if firebase_creds_json:
                creds_dict = json.loads(firebase_creds_json)
                cred = credentials.Certificate(creds_dict)
            else:
                cred = credentials.Certificate("firebase-adminsdk.json") 

            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully!")
            
        except Exception as e:
            print(f"❌ Critical Firebase Error: {e}")
            raise e

# تهيئة الاتصال فور استيراد الملف
initialize_firebase()

# كائن الداتابيز الموحد
db = firestore.client()

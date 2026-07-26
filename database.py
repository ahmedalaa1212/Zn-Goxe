# database.py
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    # التأكد من عدم تهيئة فايربيس أكثر من مرة
    if not firebase_admin._apps:
        # 1. محاولة جلب المفتاح من إعدادات السيرفر المخفية (لبيئة الإنتاج زي Railway)
        firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
        
        try:
            if firebase_creds_json:
                creds_dict = json.loads(firebase_creds_json)
                cred = credentials.Certificate(creds_dict)
                print("✅ يتم الاتصال بفايربيس عبر متغيرات البيئة (الإنتاج).")
            else:
                # 2. لو مفيش متغيرات بيئة، بنحاول نقرأ من الملف المحلي (لبيئة التطوير على جهازك)
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                    print("⚠️ يتم الاتصال بفايربيس عبر الملف المحلي (التطوير).")
                else:
                    raise FileNotFoundError("لم يتم العثور على بيانات اعتماد فايربيس لا في السيرفر ولا في الملف المحلي!")

            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully!")
            
        except Exception as e:
            print(f"❌ Critical Firebase Error: {e}")
            raise e

# تهيئة الاتصال فور استيراد الملف
initialize_firebase()

# كائن الداتابيز الموحد (اللي هنستخدمه في كل القوائم)
db = firestore.client()

# database.py
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """
    دالة لتهيئة الاتصال بقاعدة بيانات فايربيس (Firestore)
    بتضمن فتح الاتصال مرة واحدة بشكل أمن وسريع
    """
    if not firebase_admin._apps:
        firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
        
        try:
            if firebase_creds_json:
                # تحويل النص الجاي من متغيرات البيئة لـ Dictionary
                creds_dict = json.loads(firebase_creds_json)
                cred = credentials.Certificate(creds_dict)
            else:
                # للتشغيل المحلي على جهازك الشخصي
                cred = credentials.Certificate("firebase-adminsdk.json") 

            firebase_admin.initialize_app(cred)
            print("✅ تم الاتصال بقاعدة بيانات Firebase بنجاح!")
            
        except Exception as e:
            print(f"❌ خطأ حرج: فشل الاتصال بقاعدة البيانات Firebase: {e}")
            # نرفع الاستثناء عشان السيرفر ينبهك فوراً لو في مشكلة وما يكملش بشكل خاطئ
            raise e

# 1. فتح الاتصال عند تشغيل الملف
initialize_firebase()

# 2. تصدير كائن الداتابيز (db) ليستخدم في كافة القوائم (Blueprints)
db = firestore.client()

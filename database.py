# database.py
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """
    دالة لتهيئة الاتصال بقاعدة بيانات فايربيس (Firestore)
    بتتأكد إن الاتصال بيتفتح مرة واحدة بس عشان نوفر موارد السيرفر
    """
    # التأكد من عدم تهيئة Firebase أكثر من مرة
    if not firebase_admin._apps:
        try:
            # الطريقة الأفضل لسيرفرات زي Railway: تخزين مفاتيح فايربيس كـ نص في متغيرات البيئة
            firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
            
            if firebase_creds_json:
                # لو رافع المشروع على سيرفر وحاطط المفاتيح في المتغيرات
                creds_dict = json.loads(firebase_creds_json)
                cred = credentials.Certificate(creds_dict)
            else:
                # لو بتجرب على جهازك الشخصي، هيقرأ من ملف الجيسون ده
                # تأكد إنك تغير اسم الملف ده لاسم ملف مفاتيح فايربيس بتاعك
                cred = credentials.Certificate("firebase-adminsdk.json") 

            firebase_admin.initialize_app(cred)
            print("✅ تم الاتصال بقاعدة بيانات Firebase بنجاح!")
        except Exception as e:
            print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

# استدعاء الدالة لفتح الاتصال
initialize_firebase()

# تصدير (db) عشان أي ملف تاني في المشروع يقدر يستخدمه بسهولة
db = firestore.client()

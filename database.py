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


# ==========================================
# دوال التحكم في اللاعبين (يتم استدعاؤها من البوت)
# ==========================================

def is_user_banned(tg_id):
    """التحقق مما إذا كان اللاعب محظوراً في قاعدة البيانات"""
    try:
        doc_ref = db.collection('users').document(str(tg_id))
        doc = doc_ref.get()
        
        if doc.exists:
            user_data = doc.to_dict()
            return user_data.get('banned', False)
        return False
    except Exception as e:
        print(f"Error checking ban status for {tg_id}: {e}")
        return False

def init_user(tg_id, ref_id=None, first_name="صديقي"):
    """تهيئة بيانات اللاعب الجديد في قاعدة البيانات عند الضغط على /start"""
    try:
        user_ref = db.collection('users').document(str(tg_id))
        user_doc = user_ref.get()
        
        is_new_referral = False
        
        if not user_doc.exists:
            # اللاعب جديد: نقوم بإنشاء ملفه بناءً على هيكلة المشروع
            new_user_data = {
                "first_name": first_name,
                "balance": 0.0,
                "hourly_rate": 0.0,
                "mining_level": 1,          # بداية التعدين من المستوى الأول
                "level_1_upgrades": 0,      # عداد لتتبع الترقيات الـ 15 الثابتة في هذا المستوى
                "banned": False,
                "referred_by": str(ref_id) if ref_id else None,
                "joined_at": firestore.SERVER_TIMESTAMP
            }
            user_ref.set(new_user_data)
            
            # معالجة نظام الإحالة (لو تم دعوته عن طريق لاعب آخر)
            if ref_id and str(ref_id) != str(tg_id):
                is_new_referral = True
                referrer_ref = db.collection('users').document(str(ref_id))
                referrer_doc = referrer_ref.get()
                
                # إضافة اللاعب الجديد إلى قائمة أصدقاء الداعي
                if referrer_doc.exists:
                    referrer_ref.collection('friends').document(str(tg_id)).set({
                        "first_name": first_name,
                        "joined_at": firestore.SERVER_TIMESTAMP
                    })
        
        return is_new_referral
    except Exception as e:
        print(f"Error initializing user {tg_id}: {e}")
        return False

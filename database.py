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
                print("✅ يتم الاتصال بفايربيس عبر متغيرات البيئة (الإنتاج).")
            else:
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

initialize_firebase()
db = firestore.client()

def is_user_banned(tg_id):
    try:
        doc = db.collection('users').document(str(tg_id)).get()
        return doc.to_dict().get('banned', False) if doc.exists else False
    except:
        return False

def init_user(tg_id, ref_id=None, first_name="صديقي"):
    """تهيئة بيانات اللاعب الجديد وتحديث القديم وتجهيز نظام الإحالة بالكامل"""
    try:
        user_ref = db.collection('users').document(str(tg_id))
        user_doc = user_ref.get()
        
        is_new_referral = False
        
        if not user_doc.exists:
            # 1. إنشاء حساب اللاعب الجديد بالهيكلة الصحيحة لتدعم الأصدقاء ونسبة 10% والمهام
            new_user_data = {
                "first_name": first_name,
                "balance": 0.0,
                "hourly_rate": 0.0,
                "mining_level": 1,
                "level_1_upgrades": 0,
                "banned": False,
                "referred_by": str(ref_id) if ref_id and str(ref_id) != str(tg_id) else None,
                "invited_friends_count": 0,     # إجمالي الأصدقاء
                "pending_ref_earnings": 0.0,    # الأرباح المعلقة من الأصدقاء 10%
                "total_ref_earnings": 0.0,      # إجمالي ما سحبه من الأصدقاء في تاريخه
                "claimed_ref_tasks": [],        # مهام الأصدقاء التي تم استلامها
                "joined_at": firestore.SERVER_TIMESTAMP
            }
            user_ref.set(new_user_data)
            
            # 2. ربط الإحالة وإنشاء سجل للصديق عند الداعي
            if ref_id and str(ref_id) != str(tg_id):
                referrer_ref = db.collection('users').document(str(ref_id))
                referrer_doc = referrer_ref.get()
                
                if referrer_doc.exists:
                    is_new_referral = True
                    
                    # زيادة عدد الأصدقاء
                    referrer_ref.update({
                        "invited_friends_count": firestore.Increment(1)
                    })
                    
                    # إنشاء سجل هذا الصديق بداخل حساب الداعي لعرضه في واجهة السجل لاحقاً
                    referrer_ref.collection('friends').document(str(tg_id)).set({
                        "first_name": first_name,
                        "earned_from_him": 0.0, # تتبع إجمالي العملات المجموعة من هذا الصديق خصيصاً
                        "joined_at": firestore.SERVER_TIMESTAMP
                    })
        else:
            # تحديث الاسم فقط للاعب القديم لضمان عدم ضياع بياناته
            user_ref.update({"first_name": first_name})
        
        return is_new_referral
    except Exception as e:
        print(f"Error initializing user {tg_id}: {e}")
        return False

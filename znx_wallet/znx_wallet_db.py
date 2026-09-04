# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet Database Module
إدارة عمليات قاعدة البيانات (Firebase Firestore) الخاصة بمحفظة ZNX
"""

import math
import firebase_admin
from firebase_admin import firestore


def _get_db():
    try:
        return firestore.client()
    except Exception:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return firestore.client()


def _sanitize_id(user_id):
    if user_id is None:
        return None
    s_id = str(user_id).strip()
    if not s_id or s_id.lower() in ("none", "null", "undefined", "false", "true"):
        return None
    return s_id


MAX_GLOBAL_ZNX = 35_000_000.0

TIERS_CONFIG = [
    {"tier": 1, "name": "الشريحة الأولى", "min_pts": 0, "max_pts": 20_000_000, "rate": 10, "quota": 1_500_000},
    {"tier": 2, "name": "الشريحة الثانية", "min_pts": 20_000_000, "max_pts": 100_000_000, "rate": 30, "quota": 2_000_000},
    {"tier": 3, "name": "الشريحة الثالثة", "min_pts": 100_000_000, "max_pts": 500_000_000, "rate": 80, "quota": 2_500_000},
    {"tier": 4, "name": "الشريحة الرابعة", "min_pts": 500_000_000, "max_pts": 2_000_000_000, "rate": 200, "quota": 4_000_000},
    {"tier": 5, "name": "الشريحة الخامسة", "min_pts": 2_000_000_000, "max_pts": 8_000_000_000, "rate": 600, "quota": 5_500_000},
    {"tier": 6, "name": "الشريحة السادسة", "min_pts": 8_000_000_000, "max_pts": 25_000_000_000, "rate": 1600, "quota": 8_000_000},
    {"tier": 7, "name": "الشريحة السابعة", "min_pts": 25_000_000_000, "max_pts": float('inf'), "rate": 4000, "quota": 9_000_000}
]


def get_global_stats():
    try:
        db = _get_db()
        doc_ref = db.collection('znx_global_stats').document('summary')
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict() or {}
            if 'max_global_znx' not in data:
                data['max_global_znx'] = MAX_GLOBAL_ZNX
            if 'tiers_config' not in data or not data['tiers_config']:
                data['tiers_config'] = TIERS_CONFIG
            return data
        else:
            init_data = {
                'total_converted_znx': 0.0,
                'max_global_znx': MAX_GLOBAL_ZNX,
                'is_active': True,
                'tiers_config': TIERS_CONFIG
            }
            doc_ref.set(init_data)
            return init_data
    except Exception as e:
        print(f"⚠️ Error fetching ZNX global stats: {e}")
        return {
            'total_converted_znx': 0.0,
            'max_global_znx': MAX_GLOBAL_ZNX,
            'is_active': True,
            'tiers_config': TIERS_CONFIG
        }


def get_user_tier(user_points: float):
    try:
        pts = float(user_points) if user_points and not math.isnan(user_points) else 0.0
    except (ValueError, TypeError):
        pts = 0.0

    for item in TIERS_CONFIG:
        if item["min_pts"] <= pts < item["max_pts"]:
            return item
    return TIERS_CONFIG[-1]


def get_user_data(user_id: str):
    clean_uid = _sanitize_id(user_id)
    default_user = {
        'user_id': clean_uid or '',
        'balance': 0.0,
        'usd_balance': 0.0,
        'znx_balance': 0.0,
        'total_znx_earned': 0.0,
        'first_name': 'لاعب جديد',
        'current_tier': TIERS_CONFIG[0]
    }

    if not clean_uid:
        return default_user

    try:
        db = _get_db()
        doc_ref = db.collection('users').document(clean_uid)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict() or {}
            
            balance = float(data.get('balance') or 0.0)
            usd_balance = float(data.get('usd_balance') or 0.0)
            znx_balance = float(data.get('znx_balance') or 0.0)
            total_znx_earned = float(data.get('total_znx_earned') or 0.0)
            first_name = data.get('first_name') or data.get('name') or 'لاعب'
            
            updates = {}
            if 'usd_balance' not in data: updates['usd_balance'] = usd_balance
            if 'znx_balance' not in data: updates['znx_balance'] = znx_balance
            if 'total_znx_earned' not in data: updates['total_znx_earned'] = total_znx_earned
            
            if updates:
                doc_ref.set(updates, merge=True)

            current_tier = get_user_tier(balance)

            return {
                'user_id': clean_uid,
                'balance': balance,
                'usd_balance': usd_balance,
                'znx_balance': znx_balance,
                'total_znx_earned': total_znx_earned,
                'first_name': first_name,
                'current_tier': current_tier
            }
        else:
            current_tier = TIERS_CONFIG[0]
            new_user = {
                'user_id': clean_uid,
                'balance': 0.0,
                'usd_balance': 0.0,
                'znx_balance': 0.0,
                'total_znx_earned': 0.0,
                'first_name': 'لاعب جديد',
                'current_tier': current_tier
            }
            doc_ref.set(new_user, merge=True)
            return new_user
    except Exception as e:
        print(f"❌ Error in get_user_data ({user_id}): {e}")
        return default_user


def get_leaderboard_rankings(limit=50, user_id=None):
    db = _get_db()
    rankings = []
    clean_target_id = _sanitize_id(user_id)
    user_rank = "غير مصنف"
    user_in_top = False

    try:
        query = db.collection('users').order_by('total_znx_earned', direction=firestore.Query.DESCENDING).limit(limit)
        docs = list(query.stream())
        
        rank = 1
        for doc in docs:
            d = doc.to_dict() or {}
            uid = str(d.get('user_id') or doc.id)
            earned = float(d.get('total_znx_earned') or 0.0)
            znx_bal = float(d.get('znx_balance') or 0.0)
            
            entry = {
                'rank': rank,
                'user_id': uid,
                'name': d.get('first_name') or d.get('name') or 'لاعب',
                'first_name': d.get('first_name') or d.get('name') or 'لاعب',
                'total_znx_earned': earned,
                'znx_balance': znx_bal,
                'balance': float(d.get('balance') or 0.0)
            }
            rankings.append(entry)

            if clean_target_id and uid == clean_target_id:
                user_rank = rank
                user_in_top = True

            rank += 1

    except Exception as e:
        print(f"⚠️ Ordered query failed, attempting fallback query: {e}")
        try:
            docs = db.collection('users').limit(100).stream()
            raw_list = []
            for doc in docs:
                d = doc.to_dict() or {}
                raw_list.append({
                    'user_id': str(d.get('user_id') or doc.id),
                    'name': d.get('first_name') or d.get('name') or 'لاعب',
                    'first_name': d.get('first_name') or d.get('name') or 'لاعب',
                    'total_znx_earned': float(d.get('total_znx_earned') or 0.0),
                    'znx_balance': float(d.get('znx_balance') or 0.0),
                    'balance': float(d.get('balance') or 0.0)
                })
            raw_list.sort(key=lambda x: x['total_znx_earned'], reverse=True)
            
            rank = 1
            for item in raw_list[:limit]:
                item['rank'] = rank
                rankings.append(item)
                if clean_target_id and item['user_id'] == clean_target_id:
                    user_rank = rank
                    user_in_top = True
                rank += 1
        except Exception as ex:
            print(f"❌ Fallback leaderboard query failed: {ex}")

    if clean_target_id and not user_in_top:
        try:
            target_doc = db.collection('users').document(clean_target_id).get()
            if target_doc.exists:
                t_data = target_doc.to_dict() or {}
                t_earned = float(t_data.get('total_znx_earned') or 0.0)
                higher_docs = db.collection('users').where('total_znx_earned', '>', t_earned).stream()
                higher_count = sum(1 for _ in higher_docs)
                user_rank = higher_count + 1
        except Exception as e:
            print(f"⚠️ Error calculating target user rank: {e}")

    return {
        'success': True,
        'leaderboard': rankings,
        'my_rank': user_rank
    }


def get_leaderboard_data(limit=50, user_id=None):
    return get_leaderboard_rankings(limit=limit, user_id=user_id)


def execute_conversion(user_id: str, points_to_convert: float):
    clean_uid = _sanitize_id(user_id)
    if not clean_uid:
        return False, "معرف المستخدم غير صالح."

    try:
        points_to_convert = float(points_to_convert)
    except (ValueError, TypeError):
        return False, "كمية النقاط غير صالحة."

    if math.isnan(points_to_convert) or math.isinf(points_to_convert) or points_to_convert <= 0:
        return False, "كمية النقاط يجب أن تكون رقماً موجباً وصالحاً."

    db = _get_db()
    transaction = db.transaction()
    user_ref = db.collection('users').document(clean_uid)
    global_ref = db.collection('znx_global_stats').document('summary')

    @firestore.transactional
    def update_in_transaction(trans):
        global_doc = global_ref.get(transaction=trans)
        if global_doc.exists:
            stats = global_doc.to_dict() or {}
        else:
            stats = {
                'total_converted_znx': 0.0,
                'max_global_znx': MAX_GLOBAL_ZNX,
                'is_active': True,
                'tiers_config': TIERS_CONFIG
            }

        total_global_znx = float(stats.get('total_converted_znx') or 0.0)

        if total_global_znx >= MAX_GLOBAL_ZNX:
            return False, "عذراً، تم الوصول إلى الحد الأقصى للمجمّع الكلي (35M ZNX).", None

        user_doc = user_ref.get(transaction=trans)
        if not user_doc.exists:
            return False, "حساب المستخدم غير موجود بالفيربيس.", None

        user_data = user_doc.to_dict() or {}
        current_zn_balance = float(user_data.get('balance') or 0.0)

        actual_points = points_to_convert
        if current_zn_balance < actual_points:
            return False, f"رصيد نقاط ZN غير كافٍ. رصيدك الحالي: {current_zn_balance:,.2f}", None

        current_tier = get_user_tier(current_zn_balance)
        znx_received = actual_points / current_tier['rate']

        if total_global_znx + znx_received > MAX_GLOBAL_ZNX:
            znx_received = MAX_GLOBAL_ZNX - total_global_znx
            actual_points = znx_received * current_tier['rate']
            if znx_received <= 0:
                return False, "تم استنفاد مجمّع العملات المتاح بالكامل.", None

        new_zn_balance = current_zn_balance - actual_points
        new_znx_balance = float(user_data.get('znx_balance') or 0.0) + znx_received
        new_total_znx_earned = float(user_data.get('total_znx_earned') or 0.0) + znx_received
        new_global_total = total_global_znx + znx_received

        trans.set(user_ref, {
            'balance': round(new_zn_balance, 4),
            'znx_balance': round(new_znx_balance, 6),
            'total_znx_earned': round(new_total_znx_earned, 6),
            'usd_balance': float(user_data.get('usd_balance') or 0.0)
        }, merge=True)

        trans.set(global_ref, {
            'total_converted_znx': round(new_global_total, 6),
            'max_global_znx': MAX_GLOBAL_ZNX,
            'is_active': new_global_total < MAX_GLOBAL_ZNX,
            'tiers_config': TIERS_CONFIG
        }, merge=True)

        result_payload = {
            'converted_points': actual_points,
            'znx_gained': round(znx_received, 6),
            'new_zn_balance': round(new_zn_balance, 4),
            'new_znx_balance': round(new_znx_balance, 6),
            'new_total_earned': round(new_total_znx_earned, 6)
        }
        return True, "تم التحويل بنجاح", result_payload

    try:
        success, msg, res_data = update_in_transaction(transaction)
        if success:
            return True, res_data
        else:
            return False, msg
    except Exception as e:
        print(f"❌ Conversion Transaction Error: {e}")
        return False, f"حدث خطأ أثناء معالجة العملية: {str(e)}"

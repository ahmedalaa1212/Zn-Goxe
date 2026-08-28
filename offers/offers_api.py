from flask import Blueprint, request, jsonify
from offers.offers_db import get_all_offers, get_user_completed_offers, claim_offer_reward
from database import is_user_banned

offers_bp = Blueprint('offers_bp', __name__)

def extract_telegram_id(req):
    return req.headers.get('X-Telegram-User-Id')

@offers_bp.route('/api/offers/list', methods=['GET'])
def list_offers():
    tg_id = extract_telegram_id(request)
    if not tg_id:
        return jsonify({"success": False, "error": "المستخدم غير محدد"}), 400

    if is_user_banned(tg_id):
        return jsonify({"success": False, "error": "حسابك محظور."}), 403

    offers = get_all_offers()
    completed_ids = get_user_completed_offers(tg_id)

    for offer in offers:
        offer['completed'] = offer['id'] in completed_ids

    return jsonify({
        "success": True,
        "offers": offers,
        "completed_ids": completed_ids
    }), 200

@offers_bp.route('/api/offers/claim', methods=['POST'])
def claim_offer():
    tg_id = extract_telegram_id(request)
    if not tg_id:
        return jsonify({"success": False, "error": "المستخدم غير محدد"}), 400

    if is_user_banned(tg_id):
        return jsonify({"success": False, "error": "حسابك محظور."}), 403

    data = request.get_json() or {}
    offer_id = data.get('offer_id')

    if not offer_id:
        return jsonify({"success": False, "error": "معرف العرض مفقود"}), 400

    result = claim_offer_reward(tg_id, offer_id)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


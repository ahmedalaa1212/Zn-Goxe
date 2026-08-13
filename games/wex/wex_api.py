from flask import Blueprint, jsonify

wex_bp = Blueprint('wex', __name__, url_prefix='/api/games/wex')

@wex_bp.route('/status', methods=['GET'])
def get_status():
    return jsonify({"success": True, "status": "coming_soon", "message": "لعبة wex تحت التطوير"}), 200

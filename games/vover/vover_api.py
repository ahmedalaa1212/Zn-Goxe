from flask import Blueprint, jsonify

vover_bp = Blueprint('vover', __name__, url_prefix='/api/games/vover')

@vover_bp.route('/status', methods=['GET'])
def get_status():
    return jsonify({"success": True, "status": "coming_soon", "message": "لعبة vover تحت التطوير"}), 200

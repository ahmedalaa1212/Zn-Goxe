from flask import Blueprint, jsonify

hitob_bp = Blueprint('hitob', __name__, url_prefix='/api/games/hitob')

@hitob_bp.route('/status', methods=['GET'])
def get_status():
    return jsonify({"success": True, "status": "coming_soon", "message": "لعبة hitob تحت التطوير"}), 200

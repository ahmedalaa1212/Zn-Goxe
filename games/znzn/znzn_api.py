from flask import Blueprint, jsonify

znzn_bp = Blueprint('znzn', __name__, url_prefix='/api/games/znzn')

@znzn_bp.route('/status', methods=['GET'])
def get_status():
    return jsonify({"success": True, "status": "coming_soon", "message": "لعبة znzn تحت التطوير"}), 200

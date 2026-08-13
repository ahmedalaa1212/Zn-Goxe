from flask import Blueprint, jsonify

fogo_bp = Blueprint('fogo', __name__, url_prefix='/api/games/fogo')

@fogo_bp.route('/status', methods=['GET'])
def get_status():
    return jsonify({"success": True, "status": "coming_soon", "message": "لعبة fogo تحت التطوير"}), 200

from flask import Blueprint, jsonify

blxe_bp = Blueprint('blxe', __name__, url_prefix='/api/games/blxe')

@blxe_bp.route('/status', methods=['GET'])
def get_status():
    return jsonify({"success": True, "status": "coming_soon", "message": "لعبة Blxe تحت التطوير"}), 200

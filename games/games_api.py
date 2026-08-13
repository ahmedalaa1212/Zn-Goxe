from flask import Blueprint

games_bp = Blueprint('games_bp', __name__)

@games_bp.route('/api/games/status', methods=['GET'])
def games_status():
    return {"success": True, "message": "Games module active"}

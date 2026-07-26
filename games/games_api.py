# games/games_api.py
from flask import Blueprint, jsonify, request

games_bp = Blueprint('games', __name__)

@games_bp.route('/', methods=['GET', 'POST'])
def games_index():
    return jsonify({
        "success": True,
        "message": "Games API is working!"
    }), 200

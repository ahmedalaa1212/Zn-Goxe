from flask import Blueprint, jsonify

game_1_bp = Blueprint('game_1', __name__, url_prefix='/api/games/game_1')

@game_1_bp.route('/play', methods=['POST'])
def play_game_1():
    return jsonify({"success": True, "message": "تم لعب الجولة في اللعبة 1"})

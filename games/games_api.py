from flask import Blueprint, jsonify

# استيراد الـ Blueprints الفرعية لكل لعبة
from games.goxe.goxe_api import goxe_bp
from games.fogo.fogo_api import fogo_bp
from games.hitob.hitob_api import hitob_bp
from games.wex.wex_api import wex_bp
from games.vover.vover_api import vover_bp
from games.znzn.znzn_api import znzn_bp
from games.blxe.blxe_api import blxe_bp

# إنشاء الـ Blueprint الرئيسي لقسم الألعاب
games_bp = Blueprint('games', __name__, url_prefix='/api/games')

# تسجيل الـ Blueprints الفرعية
games_bp.register_blueprint(goxe_bp)
games_bp.register_blueprint(fogo_bp)
games_bp.register_blueprint(hitob_bp)
games_bp.register_blueprint(wex_bp)
games_bp.register_blueprint(vover_bp)
games_bp.register_blueprint(znzn_bp)
games_bp.register_blueprint(blxe_bp)

@games_bp.route('/list', methods=['GET'])
def get_games_list():
    """
    نقطة نهاية ترجع قائمة الألعاب وحالتها المتاحة
    """
    games = [
        {"id": "goxe", "name": "Goxe", "status": "active"},
        {"id": "fogo", "name": "fogo", "status": "coming_soon"},
        {"id": "hitob", "name": "hitob", "status": "coming_soon"},
        {"id": "wex", "name": "wex", "status": "coming_soon"},
        {"id": "vover", "name": "vover", "status": "coming_soon"},
        {"id": "znzn", "name": "znzn", "status": "coming_soon"},
        {"id": "blxe", "name": "Blxe", "status": "coming_soon"}
    ]
    return jsonify({"success": True, "games": games}), 200

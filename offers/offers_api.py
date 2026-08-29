from flask import Blueprint, request, jsonify
import offers.offers_db as offers_db

# Import sub-module blueprints
from offers.offers_tasks.offers_tasks_api import offers_tasks_bp
from offers.simple_tasks.simple_tasks_api import simple_tasks_bp
from offers.wall_tasks.wall_tasks_api import wall_tasks_bp
from offers.instant_tasks.instant_tasks_api import instant_tasks_bp
from offers.games_tasks.games_tasks_api import games_tasks_bp
from offers.disk_tasks.disk_tasks_api import disk_tasks_bp
from offers.voltra_tasks.voltra_tasks_api import voltra_tasks_bp
from offers.zngoxe_tasks.zngoxe_tasks_api import zngoxe_tasks_bp

offers_bp = Blueprint('offers', __name__)

# Register sub-module blueprints
sub_blueprints = [
    offers_tasks_bp, simple_tasks_bp, wall_tasks_bp, instant_tasks_bp,
    games_tasks_bp, disk_tasks_bp, voltra_tasks_bp, zngoxe_tasks_bp
]

for bp in sub_blueprints:
    offers_bp.register_blueprint(bp)

@offers_bp.route('/api/offers/status', methods=['GET'])
def get_offers_hub_status():
    user_id = request.headers.get('X-Telegram-User-Id')
    return jsonify({'success': True, 'status': 'Offers Hub Active', 'modules_count': 8})

from flask import Blueprint, jsonify
from games.games_db import get_games_badges

# إنشاء الـ Blueprint الرئيسي لقسم الألعاب مع البادئة الموحدة
games_bp = Blueprint('games', __name__, url_prefix='/api/games')

# تسجيل لعبة Goxe
try:
    from games.goxe.goxe_api import goxe_bp
    games_bp.register_blueprint(goxe_bp, url_prefix='/goxe')
    print("✅ تم تسجيل موديول لعبة Goxe بنجاح!")
except Exception as e:
    print(f"⚠️ خطأ أثناء تسجيل لعبة Goxe: {e}")

# تسجيل باقي الألعاب بحماية Try/Except لمنع إيقاف الخادم عند غياب أي موديول
for game_module, prefix in [
    ('fogo', '/fogo'),
    ('hitob', '/hitob'),
    ('wex', '/wex'),
    ('vover', '/vover'),
    ('znzn', '/znzn'),
    ('blxe', '/blxe')
]:
    try:
        mod = __import__(f"games.{game_module}.{game_module}_api", fromlist=[f"{game_module}_bp"])
        bp = getattr(mod, f"{game_module}_bp")
        games_bp.register_blueprint(bp, url_prefix=prefix)
        print(f"✅ تم تسجيل موديول لعبة {game_module} بنجاح!")
    except Exception as e:
        pass

@games_bp.route('/list', methods=['GET'])
def get_games_list():
    """نقطة نهاية ترجع قائمة الألعاب وحالتها المتاحة مع الشارات الديناميكية من الفايربيس"""
    badges = get_games_badges()
    
    games = [
        {"id": "goxe", "name": "Goxe", "status": "active", "badge": badges.get("goxe", "جديد")},
        {"id": "fogo", "name": "fogo", "status": "active", "badge": badges.get("fogo", "جديد")},
        {"id": "hitob", "name": "hitob", "status": "active", "badge": badges.get("hitob", "جديد")},
        {"id": "wex", "name": "wex", "status": "active", "badge": badges.get("wex", "جديد")},
        {"id": "vover", "name": "vover", "status": "active", "badge": badges.get("vover", "جديد")},
        {"id": "znzn", "name": "znzn", "status": "active", "badge": badges.get("znzn", "جديد")},
        {"id": "blxe", "name": "Blxe", "status": "active", "badge": badges.get("blxe", "جديد")}
    ]
    return jsonify({"success": True, "games": games, "badges": badges}), 200

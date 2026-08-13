from flask import Blueprint, jsonify

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
    """نقطة نهاية ترجع قائمة الألعاب وحالتها المتاحة"""
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

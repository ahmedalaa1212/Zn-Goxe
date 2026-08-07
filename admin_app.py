import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__)

# إعداد CORS بالسماح للوحة الأدمن بالوصول لكافة المسارات
CORS(app, resources={r"/api/*": {"origins": "*"}})

# تسجيل شات الإدارة إن وجد
from admin_chat.admin_chat_api import admin_chat_bp
app.register_blueprint(admin_chat_bp, url_prefix='/api/admin/chat')

# ==========================================
# دالة مساعدة لجلب البيانات المباشرة
# ==========================================

def _fetch_arena_current_stats():
    """جلب إحصائيات arena/current مباشرة من Firestore"""
    try:
        if hasattr(database, 'db') and database.db:
            doc_ref = database.db.collection('arena').document('current')
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()
    except Exception as e:
        print(f"⚠️ Error fetching arena/current doc: {e}")
    return {}

# ==========================================
# مسارات التوثيق وإحصائيات الأدمن (Super Admin APIs)
# ==========================================

@app.route('/api/verify_admin', methods=['POST'])
def verify_admin_access():
    """التحقق المباشر من هويّة الأدمن وصلاحيات الدخول من التليجرام"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    try:
        user_data = database.get_user(telegram_id) or {}
        return jsonify({
            "success": True,
            "role": "المدير العام",
            "telegram_id": telegram_id,
            "user": user_data
        }), 200
    except Exception as e:
        print(f"❌ Error verifying admin {telegram_id}: {e}")
        return jsonify({"success": False, "message": "فشل التحقق من صلاحيات المدير"}), 500


@app.route('/api/admin/dashboard-stats', methods=['GET'])
def admin_dashboard_stats():
    """تزويد لوحة الإدارة بأرقام أرباح البوت والأرباح الفعلية"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    try:
        arena_data = _fetch_arena_current_stats()
        stats_summary = database.get_game_profit_stats() or {} if hasattr(database, 'get_game_profit_stats') else {}
        settings = database.get_game_settings() or {} if hasattr(database, 'get_game_settings') else {}

        total_bets = float(arena_data.get('total_bets', stats_summary.get('global_total_bets', 0.0)))
        total_payouts = float(arena_data.get('total_payouts', stats_summary.get('global_total_wins', 0.0)))
        
        bot_profit = round(max(0.0, total_bets - total_payouts), 2)
        user_profit = round(total_payouts, 2)
        
        actual_bot_percent = 0.0
        if total_bets > 0:
            actual_bot_percent = round(((total_bets - total_payouts) / total_bets) * 100.0, 1)

        target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))

        return jsonify({
            "status": "success",
            "success": True,
            "stats": {
                "total_bot_profit": bot_profit,
                "total_wins": user_profit,
                "total_user_profit": user_profit,
                "actual_bot_percent": actual_bot_percent,
                "actual_margin": actual_bot_percent,
                "target_margin_percent": target_margin_pct
            }
        }), 200
    except Exception as e:
        print(f"❌ Error fetching dashboard stats: {e}")
        return jsonify({"status": "error", "message": "حدث خطأ أثناء جلب بيانات لوحة التحكم"}), 500


@app.route('/api/admin/update-margin', methods=['POST'])
def update_margin():
    """تعديل وحفظ نسبة أرباح البوت في الكاش والـ Firebase"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    try:
        req_data = request.get_json(silent=True) or {}
        bot_margin = req_data.get('bot_margin')
        if bot_margin is None:
            bot_margin = req_data.get('target_margin')

        if bot_margin is None:
            return jsonify({"status": "error", "success": False, "message": "يرجى تحديد نسبة أرباح البوت"}), 400

        try:
            bot_margin = float(bot_margin)
        except (ValueError, TypeError):
            return jsonify({"status": "error", "success": False, "message": "قيمة النسبة غير صالحة"}), 400

        if bot_margin < 0 or bot_margin > 100:
            return jsonify({"status": "error", "success": False, "message": "النسبة يجب أن تكون بين 0 و 100"}), 400

        if hasattr(database, 'save_admin_settings'):
            ok, msg = database.save_admin_settings({"target_margin": bot_margin})
            if ok:
                return jsonify({"status": "success", "success": True, "message": msg or "تم تعديل نسبة التحكم بنجاح"}), 200

        if hasattr(database, 'update_game_settings'):
            database.update_game_settings({
                'target_margin': bot_margin,
                'player_margin': round(100.0 - bot_margin, 2),
                'updated_by': telegram_id
            })

        if hasattr(database, 'update_grid_game_config'):
            database.update_grid_game_config(target_margin=bot_margin)

        if hasattr(database, 'clear_settings_cache'):
            database.clear_settings_cache()

        return jsonify({"status": "success", "success": True, "message": "تم تعديل نسبة التحكم بنجاح"}), 200

    except Exception as e:
        print(f"❌ Error updating margin: {e}")
        return jsonify({"status": "error", "success": False, "message": "حدث خطأ أثناء تحديث نسبة التحكم"}), 500


@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    """جلب تفاصيل إحصائيات التحكم بالأرباح للاستخدام المباشر"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    try:
        arena_data = _fetch_arena_current_stats()
        settings = database.get_game_settings() or {} if hasattr(database, 'get_game_settings') else {}
        stats_summary = database.get_game_profit_stats() or {} if hasattr(database, 'get_game_profit_stats') else {}

        total_bets = float(arena_data.get('total_bets', stats_summary.get('global_total_bets', 0.0)))
        total_payouts = float(arena_data.get('total_payouts', stats_summary.get('global_total_wins', 0.0)))

        bot_profit = round(max(0.0, total_bets - total_payouts), 2)
        user_profit = round(total_payouts, 2)

        actual_margin = 0.0
        if total_bets > 0:
            actual_margin = round(((total_bets - total_payouts) / total_bets) * 100.0, 1)

        target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))
        player_margin_pct = round(max(0.0, 100.0 - target_margin_pct), 2)

        return jsonify({
            "status": "success",
            "success": True,
            "target_margin": target_margin_pct,
            "player_margin": player_margin_pct,
            "bot_margin": target_margin_pct,
            "commission_percent": player_margin_pct,
            "stats": {
                "total_bot_profit": bot_profit,
                "total_user_profit": user_profit,
                "total_wins": user_profit,
                "actual_margin": actual_margin,
                "actual_bot_percent": actual_margin,
                "actual_user_percent": round(100.0 - actual_margin, 1),
                "global_total_bets": total_bets,
                "global_total_wins": total_payouts
            }
        }), 200
    except Exception as e:
        print(f"❌ Error fetching admin stats: {e}")
        return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب إحصائيات الأرباح"}), 500


@app.route('/api/admin/settings', methods=['POST'])
def save_admin_settings_route():
    """حفظ الإعدادات الإدارية المباشرة"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    try:
        data = request.get_json(silent=True) or {}
        target_margin = data.get('target_margin') or data.get('bot_margin')
        player_margin = data.get('player_margin')

        if target_margin is None and player_margin is not None:
            try:
                target_margin = round(100.0 - float(player_margin), 2)
            except (ValueError, TypeError):
                target_margin = None

        if target_margin is not None:
            target_margin = float(target_margin)
            if target_margin < 0 or target_margin > 100:
                return jsonify({"status": "error", "success": False, "error": "النسبة يجب أن تكون بين 0 و 100"}), 400

            if hasattr(database, 'update_game_settings'):
                database.update_game_settings({
                    'target_margin': target_margin,
                    'player_margin': round(100.0 - target_margin, 2),
                    'updated_by': telegram_id
                })

            if hasattr(database, 'update_grid_game_config'):
                database.update_grid_game_config(target_margin=target_margin)

            if hasattr(database, 'clear_settings_cache'):
                database.clear_settings_cache()

            return jsonify({
                "status": "success",
                "success": True,
                "message": "تم حفظ نسبة البوت ونسبة اللاعبين بنجاح",
                "target_margin": target_margin,
                "player_margin": round(100.0 - target_margin, 2)
            }), 200
        return jsonify({"status": "error", "success": False, "error": "يرجى تحديد نسبة البوت أو نسبة اللاعبين"}), 400
    except Exception as e:
        print(f"❌ Error saving admin settings: {e}")
        return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء حفظ الإعدادات"}), 500


# ==========================================
# مسارات إعدادات اللعبة والأرباح (Game Settings)
# ==========================================

@app.route('/api/game-settings', methods=['GET', 'POST'])
def manage_game_settings():
    """جلب وتحديث إعدادات الأرباح من واجهة الأدمن"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if request.method == 'GET':
        try:
            arena_data = _fetch_arena_current_stats()
            settings = database.get_game_settings() or {} if hasattr(database, 'get_game_settings') else {}
            stats_summary = database.get_game_profit_stats() or {} if hasattr(database, 'get_game_profit_stats') else {}
            grid_cfg = settings.get('grid_game_config', {})

            total_bets = float(arena_data.get('total_bets', stats_summary.get('global_total_bets', 0.0)))
            total_payouts = float(arena_data.get('total_payouts', stats_summary.get('global_total_wins', 0.0)))

            bot_profit = round(max(0.0, total_bets - total_payouts), 2)
            user_profit = round(total_payouts, 2)

            actual_margin = 0.0
            if total_bets > 0:
                actual_margin = round(((total_bets - total_payouts) / total_bets) * 100.0, 1)

            target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))
            player_margin_pct = round(max(0.0, 100.0 - target_margin_pct), 2)

            return jsonify({
                "status": "success",
                "success": True,
                "target_margin": target_margin_pct,
                "player_margin": player_margin_pct,
                "commission_percent": player_margin_pct,
                "grid_game_config": grid_cfg,
                "stats": {
                    "total_bot_profit": bot_profit,
                    "total_user_profit": user_profit,
                    "total_wins": user_profit,
                    "actual_margin": actual_margin,
                    "actual_bot_percent": actual_margin,
                    "actual_user_percent": round(100.0 - actual_margin, 1),
                    "global_total_bets": total_bets,
                    "global_total_wins": total_payouts
                }
            }), 200
        except Exception as e:
            print(f"❌ Error fetching game settings: {e}")
            return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب إعدادات الأرباح"}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json(silent=True) or {}
            target_margin_input = data.get('target_margin') or data.get('bot_margin')
            commission_input = data.get('commission_percent') or data.get('player_margin')
            min_bet_input = data.get('min_bet')

            if target_margin_input is None and commission_input is not None:
                try:
                    target_margin_input = round(100.0 - float(commission_input), 2)
                except (ValueError, TypeError):
                    pass

            if target_margin_input is not None or min_bet_input is not None:
                if hasattr(database, 'update_grid_game_config'):
                    database.update_grid_game_config(
                        min_bet=min_bet_input,
                        target_margin=target_margin_input
                    )
            
            if hasattr(database, 'update_game_settings'):
                database.update_game_settings(data)

            if hasattr(database, 'clear_settings_cache'):
                database.clear_settings_cache()

            return jsonify({
                "status": "success",
                "success": True,
                "message": "تم تحديث إعدادات الأرباح ونسبة البوت بنجاح"
            }), 200
        except Exception as e:
            print(f"❌ Error updating game settings: {e}")
            return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء حفظ إعدادات الأرباح"}), 500


# ==========================================
# مسارات المشرفين واللوجات (Moderators & Admin Logs)
# ==========================================

@app.route('/api/moderators', methods=['GET', 'POST'])
def manage_moderators():
    """جلب وإضافة المشرفين من لوحة الأدمن"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if request.method == 'GET':
        try:
            moderators = database.get_moderators() if hasattr(database, 'get_moderators') else []
            return jsonify({"status": "success", "success": True, "moderators": moderators}), 200
        except Exception as e:
            print(f"❌ Error fetching moderators: {e}")
            return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب قائمة المشرفين"}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json(silent=True) or {}
            mod_id = data.get('id')
            mod_name = data.get('name')
            permissions = data.get('permissions', {})

            if not mod_id or not mod_name:
                return jsonify({"status": "error", "success": False, "error": "يرجى تحديد المعرف والاسم للمشرف"}), 400

            if hasattr(database, 'add_moderator'):
                database.add_moderator(mod_id, mod_name, permissions, added_by=telegram_id)

            return jsonify({"status": "success", "success": True, "message": "تمت إضافة المشرف بنجاح"}), 200
        except Exception as e:
            print(f"❌ Error adding moderator: {e}")
            return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء إضافة المشرف"}), 500


@app.route('/api/moderators/<mod_id>', methods=['DELETE'])
def delete_moderator_route(mod_id):
    """حذف مشرف وحظر صلاحياته"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    try:
        if hasattr(database, 'delete_moderator'):
            database.delete_moderator(mod_id, deleted_by=telegram_id)
        return jsonify({"status": "success", "success": True, "message": "تم حذف المشرف بنجاح"}), 200
    except Exception as e:
        print(f"❌ Error deleting moderator {mod_id}: {e}")
        return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء حذف المشرف"}), 500


@app.route('/api/admin-logs', methods=['GET'])
def get_admin_logs_route():
    """جلب سجل التحركات والنشاطات الإدارية"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    try:
        logs = database.get_admin_logs() if hasattr(database, 'get_admin_logs') else []
        return jsonify({"status": "success", "success": True, "logs": logs}), 200
    except Exception as e:
        print(f"❌ Error fetching admin logs: {e}")
        return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب السجلات"}), 500


# ==========================================
# الأمان ومعالجة الملفات الثابتة والأخطاء
# ==========================================

@app.after_request
def add_security_headers(response):
    """منع الكاش للـ API"""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({"status": "error", "success": False, "error": "حدث خطأ داخلي في سيرفر الإدارة"}), 500

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"status": "error", "success": False, "error": "مسار الإدارة غير موجود"}), 404
    return send_from_directory('.', 'index.html')

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

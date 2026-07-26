from flask import Blueprint, jsonify

# تعريف الـ Blueprint اللي ملف app.py بيدور عليه
friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/', methods=['GET'])
def get_friends():
    return jsonify({"success": True, "message": "Friends API works!"}), 200

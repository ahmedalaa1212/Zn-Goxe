# tasks/tasks_api.py
from flask import Blueprint, jsonify, request

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/', methods=['GET', 'POST'])
def tasks_index():
    return jsonify({
        "success": True,
        "message": "Tasks API is working!"
    }), 200

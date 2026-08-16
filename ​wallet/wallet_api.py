from flask import Blueprint, jsonify, request

# تعريف الموديول الأساسي للمحفظة
wallet_bp = Blueprint('wallet_bp', __name__)

@wallet_bp.route('/status', methods=['GET'])
def wallet_status():
    """مسار اختبار للتأكد من عمل API المحفظة"""
    return jsonify({
        "success": True,
        "message": "نظام المحفظة الرئيسي يعمل بنجاح ومستعد لاستقبال الطلبات"
    })

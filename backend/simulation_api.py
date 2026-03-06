"""
量化交易模拟 API
"""

from flask import Blueprint, jsonify
import json
import os

sim_api = Blueprint('simulation', __name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
TRADES_FILE = os.path.join(DATA_DIR, 'simulation_trades.json')


@sim_api.route('/api/simulation', methods=['GET'])
def get_simulation():
    """获取模拟交易结果"""
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
            return jsonify({'success': True, 'data': trades})
        except:
            pass
    return jsonify({'success': False, 'data': []})

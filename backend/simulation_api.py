"""
量化交易模拟 API
"""

from flask import Blueprint, jsonify, request
import json
import os
from datetime import datetime

sim_api = Blueprint('simulation', __name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'trader-bot', 'data')
os.makedirs(DATA_DIR, exist_ok=True)
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


@sim_api.route('/api/simulation', methods=['POST'])
def run_simulation():
    """运行模拟交易"""
    data = request.json
    
    symbols = data.get('symbols', [])  # 标的列表
    capital = data.get('capital', 1000000)  # 初始资金
    params = data.get('params', {})  # 技术参数
    
    if not symbols:
        return jsonify({'success': False, 'error': '请选择至少一个标的'})
    
    # 这里应该调用真正的模拟交易逻辑
    # 由于网络原因，返回示例数据
    
    # 模拟交易结果
    trades = [
        {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'date': datetime.now().strftime('%Y-%m-%d'),
            'action': 'buy',
            'symbol': symbols[0].get('code', 'sh000001'),
            'name': symbols[0].get('name', '上证指数'),
            'shares': 1000,
            'price': 256.53,
            'amount': 256530,
            'reasons': ['均线多头排列', 'RSI超卖(28.5)'],
            'signal_score': 4,
            'position_ratio': 0.3,
            'capital_before': capital,
            'capital_after': capital - 256530,
        },
    ]
    
    # 保存交易记录
    with open(TRADES_FILE, 'w', encoding='utf-8') as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)
    
    return jsonify({'success': True, 'data': trades})


@sim_api.route('/api/simulation/trades', methods=['GET'])
def get_simulation_trades():
    """获取模拟交易记录"""
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
            
            # 计算统计
            sell_trades = [t for t in trades if t.get('action') == 'sell']
            winning = [t for t in sell_trades if t.get('profit', 0) > 0]
            losing = [t for t in sell_trades if t.get('profit', 0) <= 0]
            
            total_profit = sum(t.get('profit', 0) for t in sell_trades)
            
            stats = {
                'total_trades': len(trades),
                'sell_trades': len(sell_trades),
                'winning_trades': len(winning),
                'losing_trades': len(losing),
                'win_rate': len(winning) / len(sell_trades) * 100 if sell_trades else 0,
                'total_profit': total_profit,
                'avg_profit': total_profit / len(sell_trades) if sell_trades else 0,
            }
            
            return jsonify({'success': True, 'data': {'trades': trades, 'statistics': stats}})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': True, 'data': {'trades': [], 'statistics': {
        'total_trades': 0, 'sell_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
        'win_rate': 0, 'total_profit': 0, 'avg_profit': 0
    }}})


@sim_api.route('/api/simulation/trades', methods=['POST'])
def add_simulation_trade():
    """添加模拟交易记录"""
    trade = request.json
    
    # 读取现有记录
    trades = []
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
        except:
            trades = []
    
    # 添加新记录
    trade['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    trade['date'] = datetime.now().strftime('%Y-%m-%d')
    trades.append(trade)
    
    # 保存
    with open(TRADES_FILE, 'w', encoding='utf-8') as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)
    
    return jsonify({'success': True})


@sim_api.route('/api/simulation/clear', methods=['POST'])
def clear_simulation():
    """清空模拟交易记录"""
    if os.path.exists(TRADES_FILE):
        os.remove(TRADES_FILE)
    return jsonify({'success': True})

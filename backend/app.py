"""
量化交易系统后端 API
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# 导入分析模块
from technical_analyzer import TechnicalAnalyzer
from trading_strategy import TradingLogger, TradingStrategy, TradingSignal

# 注册股票数据API
from stock_api import stock_api
app.register_blueprint(stock_api)

# 注册模拟交易API
from simulation_api import sim_api
app.register_blueprint(sim_api)

# 全局实例
analyzer = None
logger = TradingLogger(log_file=os.path.join(DATA_DIR, 'trading_log.json'))
strategy = TradingStrategy()


def get_default_params():
    """获取默认参数"""
    return {
        'ma_short': 5,
        'ma_medium': 10,
        'ma_long': 20,
        'ma_long_term': 60,
        'rsi_period': 14,
        'rsi_oversold': 30,
        'rsi_overbought': 70,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'bb_period': 20,
        'bb_std': 2,
        'volume_ma_period': 5,
        'volume_ratio_threshold': 1.5,
        'buy_score_threshold': 1,
        'strong_buy_score': 3,
        'sell_score_threshold': -1,
        'stop_loss_pct': 5,
        'take_profit_pct': 15,
    }


def load_params():
    """加载参数"""
    params_file = os.path.join(DATA_DIR, 'params.json')
    if os.path.exists(params_file):
        try:
            with open(params_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return get_default_params()


def save_params(params):
    """保存参数"""
    params_file = os.path.join(DATA_DIR, 'params.json')
    with open(params_file, 'w') as f:
        json.dump(params, f, indent=2)


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


@app.route('/api/params', methods=['GET'])
def get_params():
    return jsonify(load_params())


@app.route('/api/params', methods=['POST'])
def set_params():
    params = request.json
    save_params(params)
    global analyzer
    analyzer = TechnicalAnalyzer(params)
    return jsonify({'success': True, 'params': params})


@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json
    symbol = data.get('symbol', 'sh000001')
    days = data.get('days', 250)
    
    try:
        params = load_params()
        analyzer_obj = TechnicalAnalyzer(params)
        
        # 获取并计算历史数据与技术指标
        df = analyzer_obj.calculate_all(symbol, days=days)
        if df.empty:
            return jsonify({'success': False, 'error': '无法获取数据'})
        signals = analyzer_obj.get_latest_signals(df)
        history = df.tail(60).to_dict('records')
        
        return jsonify({
            'success': True,
            'data': {
                'signals': signals,
                'history': history,
                'params': params
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/auto_trade', methods=['POST'])
def auto_trade():
    """根据最新推理值（技术分析评分）自动给出买卖及仓位建议，并可记录到交易日志。"""
    data = request.json or {}
    symbol = data.get('symbol', 'sh000001')
    days = int(data.get('days', 250))
    capital = float(data.get('capital', 100000))  # 可用资金

    # 当前持仓信息（如果有）
    position_shares = float(data.get('position_shares', 0))
    entry_price = float(data.get('entry_price', 0))

    try:
        # 加载参数 & 构造分析器和策略
        params = load_params()
        analyzer_obj = TechnicalAnalyzer(params)

        df = analyzer_obj.calculate_all(symbol, days=days)
        if df.empty:
            return jsonify({'success': False, 'error': '无法获取数据'})

        signals = analyzer_obj.get_latest_signals(df)
        if not signals:
            return jsonify({'success': False, 'error': '历史数据不足，无法生成信号'})

        latest_price = float(signals['close'])

        # 构造交易信号对象（使用 overall_score 作为推理值）
        trade_signal = TradingSignal()
        trade_signal.from_analysis(signals)

        # 构造交易策略（会自动兼容 *_pct 参数）
        strategy_obj = TradingStrategy(params)

        decision = 'hold'
        trade_info = None

        # 无持仓 -> 判断是否买入
        if position_shares <= 0:
            if strategy_obj.should_buy(trade_signal, current_position=0):
                buy_amount = strategy_obj.calculate_position_size(trade_signal, total_capital=capital)
                buy_amount = min(buy_amount, capital)

                shares = int(buy_amount / latest_price / 100) * 100
                if shares > 0:
                    cost = shares * latest_price
                    decision = 'buy'
                    trade = {
                        'symbol': symbol,
                        'name': data.get('name', symbol),
                        'action': 'buy',
                        'shares': shares,
                        'price': latest_price,
                        'amount': cost,
                        'capital_before': capital,
                        'capital_after': capital - cost,
                        'signal_score': trade_signal.score,
                        'recommendation': trade_signal.recommendation,
                        'reasons': signals.get('reasons', []),
                    }
                    # 生成原因并记录
                    trade['reason'] = strategy_obj.generate_trade_reason(trade_signal, 'buy')
                    logger.add_trade(trade)
                    trade_info = trade
        else:
            # 有持仓 -> 判断是否卖出
            profit_pct = 0.0
            if entry_price > 0:
                profit_pct = (latest_price - entry_price) / entry_price * 100

            if strategy_obj.should_sell(trade_signal, profit_pct=profit_pct):
                revenue = position_shares * latest_price
                profit = revenue - position_shares * entry_price if entry_price > 0 else 0.0

                decision = 'sell'
                trade = {
                    'symbol': symbol,
                    'name': data.get('name', symbol),
                    'action': 'sell',
                    'shares': position_shares,
                    'price': latest_price,
                    'amount': revenue,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'capital_before': capital,
                    'capital_after': capital + revenue,
                    'signal_score': trade_signal.score,
                    'recommendation': trade_signal.recommendation,
                    'reasons': signals.get('reasons', []),
                }
                trade['reason'] = strategy_obj.generate_trade_reason(trade_signal, 'sell')
                logger.add_trade(trade)
                trade_info = trade

        return jsonify({
            'success': True,
            'data': {
                'decision': decision,
                'price': latest_price,
                'signal': trade_signal.to_dict(),
                'signals_raw': signals,
                'trade': trade_info,
                'params': params,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/trades', methods=['GET'])
def get_trades():
    symbol = request.args.get('symbol')
    limit = int(request.args.get('limit', 100))
    
    trades = logger.get_trades(symbol, limit)
    stats = logger.get_statistics(symbol)
    
    return jsonify({
        'success': True,
        'data': {
            'trades': trades,
            'statistics': stats
        }
    })


@app.route('/api/trades', methods=['POST'])
def add_trade():
    trade = request.json
    
    params = load_params()
    strategy = TradingStrategy(params)
    
    signal = TradingSignal()
    signal.recommendation = trade.get('action', 'buy')
    signal.score = trade.get('score', 0)
    signal.reasons = trade.get('reasons', [])
    
    trade['reason'] = strategy.generate_trade_reason(signal, trade.get('action', 'buy'))
    
    logger.add_trade(trade)
    
    return jsonify({'success': True})


@app.route('/api/symbols', methods=['GET'])
def get_symbols():
    symbols = [
        {'code': 'sh000001', 'name': '上证指数', 'type': 'index'},
        {'code': '399001', 'name': '深证成指', 'type': 'index'},
        {'code': '399006', 'name': '创业板指', 'type': 'index'},
        {'code': '000001', 'name': '平安银行', 'type': 'stock'},
        {'code': '600519', 'name': '贵州茅台', 'type': 'stock'},
        {'code': '000858', 'name': '五粮液', 'type': 'stock'},
        {'code': '601318', 'name': '中国平安', 'type': 'stock'},
        {'code': '600036', 'name': '招商银行', 'type': 'stock'},
        {'code': '000333', 'name': '美的集团', 'type': 'stock'},
        {'code': '002594', 'name': '比亚迪', 'type': 'stock'},
        {'code': '159919', 'name': '券商ETF', 'type': 'etf'},
    ]
    return jsonify({'success': True, 'data': symbols})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

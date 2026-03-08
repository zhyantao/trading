"""
量化交易模拟 API

基于真实历史数据 + 技术分析“推理值”(overall_score)，
自动决定何时买入、卖出以及买入/卖出金额，并返回完整回测结果。
"""

from flask import Blueprint, jsonify, request
import json
import os
from datetime import datetime
from typing import Dict, List, Any

from technical_analyzer import TechnicalAnalyzer
from trading_strategy import TradingStrategy, TradingSignal

sim_api = Blueprint('simulation', __name__)

# 用于前端展示的模拟交易结果文件（保持原路径兼容）
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'trader-bot', 'data')
os.makedirs(DATA_DIR, exist_ok=True)
TRADES_FILE = os.path.join(DATA_DIR, 'simulation_trades.json')


def _load_params() -> Dict[str, Any]:
    """从后端 data 目录加载参数（与 app.py 保持一致）"""
    backend_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    os.makedirs(backend_data_dir, exist_ok=True)
    params_file = os.path.join(backend_data_dir, 'params.json')
    if os.path.exists(params_file):
        try:
            with open(params_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    # 默认参数（与 app.get_default_params 一致）
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


@sim_api.route('/api/simulation', methods=['GET'])
def get_simulation():
    """获取最近一次模拟交易结果"""
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r', encoding='utf-8') as f:
                content = json.load(f)
            return jsonify({'success': True, 'data': content})
        except Exception:
            pass
    return jsonify({'success': False, 'data': []})


@sim_api.route('/api/simulation', methods=['POST'])
def run_simulation():
    """运行基于历史数据的自动化模拟交易"""
    data = request.json or {}

    symbols_input = data.get('symbols', [])  # 标的列表
    capital = float(data.get('capital', 1_000_000))  # 初始资金
    days = int(data.get('days', 120))  # 回测天数

    if not symbols_input:
        return jsonify({'success': False, 'error': '请选择至少一个标的'})

    # 归一化 symbols: 既兼容 [{code,name}] 也兼容 ['sh000001', ...]
    symbols: List[Dict[str, str]] = []
    for item in symbols_input:
        if isinstance(item, dict):
            symbols.append(
                {
                    'code': item.get('code') or item.get('symbol') or '',
                    'name': item.get('name') or item.get('code') or item.get('symbol') or '',
                }
            )
        else:
            symbols.append({'code': str(item), 'name': str(item)})

    symbols = [s for s in symbols if s['code']]
    if not symbols:
        return jsonify({'success': False, 'error': '标的代码无效'})

    # 加载参数、构造技术分析器和策略
    params = _load_params()
    analyzer = TechnicalAnalyzer(params)
    strategy = TradingStrategy(params)

    # 获取各标的历史数据 + 指标
    stock_data: Dict[str, Dict[str, Any]] = {}
    for s in symbols:
        df = analyzer.calculate_all(s['code'], days=days)
        if df.empty:
            # 某个标的取不到数据就跳过
            continue
        df = df.sort_values('date').reset_index(drop=True)
        stock_data[s['code']] = {
            'name': s['name'],
            'data': df,
        }

    if not stock_data:
        return jsonify({'success': False, 'error': '无法获取任何标的的历史数据'})

    # 统一交易日期：取所有标的日期的交集，防止数据对不齐
    all_dates_sets = [set(info['data']['date']) for info in stock_data.values()]
    common_dates = sorted(set.intersection(*all_dates_sets))
    if len(common_dates) < 2:
        return jsonify({'success': False, 'error': '可用的共同交易日太少，无法回测'})

    # 为了加快回测，只使用最近 days 天的共同日期
    trading_days = common_dates[-days:]

    trades: List[Dict[str, Any]] = []
    current_capital = capital
    position_symbol: str | None = None
    position_shares: float = 0
    entry_price: float = 0.0

    for day in trading_days:
        day_signals: Dict[str, Dict[str, Any]] = {}

        # 为每个标的在该日生成信号（基于截至该日的历史数据）
        for code, info in stock_data.items():
            df = info['data']
            # 找到当前日期在 df 中的位置
            df_day = df[df['date'] <= day]
            if len(df_day) < 30:
                continue  # 指标不稳定，跳过

            # 截止到当前日的子 DataFrame，用于计算“当时可见的”推理值
            signals = analyzer.get_latest_signals(df_day)
            if not signals:
                continue

            ts = TradingSignal()
            ts.from_analysis(signals)

            latest_row = df_day.iloc[-1]
            price = float(latest_row['close'])

            day_signals[code] = {
                'symbol': code,
                'name': info['name'],
                'signal_obj': ts,
                'signals_raw': signals,
                'price': price,
            }

        if not day_signals:
            continue

        # 先计算卖出，再计算买入（避免同一天频繁进出同一标的）
        date_str = day.strftime('%Y-%m-%d') if hasattr(day, 'strftime') else str(day)

        # 有持仓 -> 判断是否卖出
        if position_symbol is not None and position_shares > 0:
            cur_info = day_signals.get(position_symbol)
            if cur_info:
                cur_price = cur_info['price']
                profit_pct = 0.0
                if entry_price > 0:
                    profit_pct = (cur_price - entry_price) / entry_price * 100

                if strategy.should_sell(cur_info['signal_obj'], profit_pct=profit_pct):
                    revenue = position_shares * cur_price
                    profit = revenue - position_shares * entry_price

                    trade = {
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'date': date_str,
                        'action': 'sell',
                        'symbol': position_symbol,
                        'name': cur_info['name'],
                        'shares': position_shares,
                        'price': cur_price,
                        'amount': revenue,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'capital_before': current_capital,
                        'capital_after': current_capital + revenue,
                        'reasons': cur_info['signals_raw'].get('reasons', []),
                        'signal_score': cur_info['signal_obj'].score,
                    }
                    trade['reason'] = strategy.generate_trade_reason(cur_info['signal_obj'], 'sell')

                    trades.append(trade)
                    current_capital += revenue
                    position_symbol = None
                    position_shares = 0
                    entry_price = 0.0

        # 无持仓 -> 判断是否买入
        if position_symbol is None:
            # 选出所有给出买入建议的标的
            buy_candidates = []
            for code, info in day_signals.items():
                ts = info['signal_obj']
                if strategy.should_buy(ts, current_position=0):
                    buy_candidates.append(info)

            if buy_candidates:
                # 按推理值（score）从高到低排序，选择最优一个
                best = sorted(buy_candidates, key=lambda x: x['signal_obj'].score, reverse=True)[0]
                ts = best['signal_obj']
                price = best['price']

                # 使用策略计算应投入资金（基于推理值）
                buy_amount = strategy.calculate_position_size(ts, total_capital=current_capital)
                buy_amount = min(buy_amount, current_capital)

                # 向下取整到 100 股一手
                shares = int(buy_amount / price / 100) * 100
                if shares > 0:
                    cost = shares * price
                    trade = {
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'date': date_str,
                        'action': 'buy',
                        'symbol': best['symbol'],
                        'name': best['name'],
                        'shares': shares,
                        'price': price,
                        'amount': cost,
                        'capital_before': current_capital,
                        'capital_after': current_capital - cost,
                        'reasons': best['signals_raw'].get('reasons', []),
                        'signal_score': ts.score,
                    }
                    trade['reason'] = strategy.generate_trade_reason(ts, 'buy')

                    trades.append(trade)
                    current_capital -= cost
                    position_symbol = best['symbol']
                    position_shares = shares
                    entry_price = price

    # 若最终仍有持仓，则按最后一个可用价格做一次平仓视作结束（可选）
    if position_symbol is not None and position_shares > 0:
        info = stock_data[position_symbol]
        last_row = info['data'].iloc[-1]
        last_price = float(last_row['close'])
        profit = position_shares * (last_price - entry_price)
        profit_pct = (last_price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0

        trade = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'date': str(last_row['date'].date()),
            'action': 'sell',
            'symbol': position_symbol,
            'name': info['name'],
            'shares': position_shares,
            'price': last_price,
            'amount': position_shares * last_price,
            'profit': profit,
            'profit_pct': profit_pct,
            'capital_before': current_capital,
            'capital_after': current_capital + position_shares * last_price,
            'reasons': ['回测结束自动平仓'],
            'signal_score': 0,
        }
        trades.append(trade)
        current_capital += position_shares * last_price

    # 统计指标
    sell_trades = [t for t in trades if t.get('action') == 'sell']
    winning = [t for t in sell_trades if t.get('profit', 0) > 0]
    losing = [t for t in sell_trades if t.get('profit', 0) <= 0]
    total_profit = current_capital - capital

    stats = {
        'initial_capital': capital,
        'final_capital': current_capital,
        'total_profit': total_profit,
        'profit_pct': (total_profit / capital * 100) if capital > 0 else 0,
        'total_trades': len(trades),
        'buy_trades': len([t for t in trades if t.get('action') == 'buy']),
        'sell_trades': len(sell_trades),
        'winning_trades': len(winning),
        'losing_trades': len(losing),
        'win_rate': (len(winning) / len(sell_trades) * 100) if sell_trades else 0,
    }

    result = {
        'trades': trades,
        'statistics': stats,
        'symbols': symbols,
        'run_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    # 保存到文件，供前端查询
    with open(TRADES_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return jsonify({'success': True, 'data': result})


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

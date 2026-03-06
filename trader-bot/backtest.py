"""
量化交易回测系统 - 模拟数据版
使用100万本金，过去30天数据，30只股票/基金
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import random
import os

np.random.seed(2026)
random.seed(2026)

INITIAL_CAPITAL = 1000000

# 30只股票/基金
SYMBOLS = [
    {'code': '510300', 'name': '沪深300ETF', 'type': 'etf'},
    {'code': '159919', 'name': '券商ETF', 'type': 'etf'},
    {'code': '512880', 'name': '证券ETF', 'type': 'etf'},
    {'code': '159995', 'name': '券商ETF', 'type': 'etf'},
    {'code': '159792', 'name': 'TMT50ETF', 'type': 'etf'},
    {'code': '000001', 'name': '平安银行', 'type': 'stock'},
    {'code': '600036', 'name': '招商银行', 'type': 'stock'},
    {'code': '601398', 'name': '工商银行', 'type': 'stock'},
    {'code': '601939', 'name': '建设银行', 'type': 'stock'},
    {'code': '600519', 'name': '贵州茅台', 'type': 'stock'},
    {'code': '000858', 'name': '五粮液', 'type': 'stock'},
    {'code': '000333', 'name': '美的集团', 'type': 'stock'},
    {'code': '000568', 'name': '泸州老窖', 'type': 'stock'},
    {'code': '002594', 'name': '比亚迪', 'type': 'stock'},
    {'code': '600900', 'name': '长江电力', 'type': 'stock'},
    {'code': '601318', 'name': '中国平安', 'type': 'stock'},
    {'code': '600276', 'name': '恒瑞医药', 'type': 'stock'},
    {'code': '300750', 'name': '宁德时代', 'type': 'stock'},
    {'code': '002311', 'name': '海大集团', 'type': 'stock'},
    {'code': '600522', 'name': '中天科技', 'type': 'stock'},
    {'code': '002202', 'name': '金风科技', 'type': 'stock'},
    {'code': '600438', 'name': '通威股份', 'type': 'stock'},
    {'code': '688981', 'name': '中芯国际', 'type': 'stock'},
    {'code': '603986', 'name': '兆易创新', 'type': 'stock'},
    {'code': '002475', 'name': '立讯精密', 'type': 'stock'},
    {'code': '600030', 'name': '中信证券', 'type': 'stock'},
    {'code': '601211', 'name': '国泰君安', 'type': 'stock'},
    {'code': '688111', 'name': '金山办公', 'type': 'stock'},
    {'code': '000651', 'name': '格力电器', 'type': 'stock'},
    {'code': '600887', 'name': '伊利股份', 'type': 'stock'},
]


def generate_mock_data(symbol, name, days=40):
    """生成模拟股票数据 - 带趋势特征"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # 基础价格
    base_price = random.uniform(10, 500)
    volatility = random.uniform(0.02, 0.04)
    trend = random.uniform(-0.003, 0.005)  # 趋势
    
    prices = [base_price]
    for i in range(1, days):
        # 加入周期性波动
        cycle = 0.01 * np.sin(2 * np.pi * i / 10)
        change = trend + cycle + np.random.normal(0, volatility)
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, 1))
    
    df = pd.DataFrame({
        'date': dates,
        'Open': [p * random.uniform(0.98, 1.02) for p in prices],
        'High': [p * random.uniform(1.00, 1.05) for p in prices],
        'Low': [p * random.uniform(0.95, 1.00) for p in prices],
        'Close': prices,
        'Volume': [random.randint(1000000, 50000000) for _ in range(days)],
    })
    
    return df


def calculate_indicators(df):
    """计算技术指标"""
    df['ma5'] = df['Close'].rolling(window=5).mean()
    df['ma10'] = df['Close'].rolling(window=10).mean()
    df['ma20'] = df['Close'].rolling(window=20).mean()
    
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    return df


def generate_signal(df, prev_df):
    """生成交易信号"""
    if df.empty or prev_df.empty:
        return 'hold', 0, []
    
    latest = df.iloc[-1]
    prev = prev_df.iloc[-1]
    
    score = 0
    reasons = []
    
    # 均线趋势 - 降低门槛
    if pd.notna(latest['ma5']) and pd.notna(latest['ma10']):
        if latest['ma5'] > latest['ma10']:
            score += 1
            reasons.append('短期均线高于中期均线')
    
    # RSI - 更容易触发
    if pd.notna(latest['rsi']):
        if latest['rsi'] < 35:
            score += 2
            reasons.append(f'RSI超卖({latest["rsi"]:.1f})')
        elif latest['rsi'] > 65:
            score -= 2
            reasons.append(f'RSI超买({latest["rsi"]:.1f})')
    
    # MACD金叉/死叉
    if pd.notna(latest['macd']) and pd.notna(latest['macd_signal']):
        if latest['macd'] > latest['macd_signal']:
            score += 1
            reasons.append('MACD正向')
        else:
            score -= 1
            reasons.append('MACD负向')
        
        if latest['macd_hist'] > 0 and prev['macd_hist'] <= 0:
            score += 1
            reasons.append('MACD柱状图转正')
        elif latest['macd_hist'] < 0 and prev['macd_hist'] >= 0:
            score -= 1
            reasons.append('MACD柱状图转负')
    
    # 连续上涨/下跌
    if len(df) >= 3:
        recent = df.tail(3)['Close']
        if recent.iloc[2] > recent.iloc[1] > recent.iloc[0]:
            score += 1
            reasons.append('连续上涨')
        elif recent.iloc[2] < recent.iloc[1] < recent.iloc[0]:
            score -= 1
            reasons.append('连续下跌')
    
    if score >= 2:
        return 'strong_buy', score, reasons
    elif score >= 1:
        return 'buy', score, reasons
    elif score <= -2:
        return 'strong_sell', score, reasons
    elif score <= -1:
        return 'sell', score, reasons
    return 'hold', score, reasons


def run_backtest():
    """运行回测"""
    print(f"{'='*70}")
    print(f"量化交易回测系统")
    print(f"{'='*70}")
    print(f"初始资金: {INITIAL_CAPITAL:,.2f} 元")
    print(f"标的数量: {len(SYMBOLS)} 只")
    print(f"回测周期: 最近30个交易日")
    print(f"{'='*70}\n")
    
    # 生成模拟数据
    print("正在生成模拟股票数据...")
    stock_data = {}
    for sym in SYMBOLS:
        df = generate_mock_data(sym['code'], sym['name'], days=40)
        df = calculate_indicators(df)
        stock_data[sym['code']] = {
            'name': sym['name'],
            'type': sym['type'],
            'data': df
        }
    
    print(f"成功生成 {len(stock_data)} 只股票数据\n")
    
    # 模拟交易
    capital = INITIAL_CAPITAL
    position = 0
    position_symbol = None
    position_price = 0
    position_name = None
    trades = []
    
    trading_days = stock_data[list(stock_data.keys())[0]]['data'].tail(30)['date'].tolist()
    
    print(f"开始回测 (共 {len(trading_days)} 个交易日)")
    print(f"{'='*70}")
    
    for date in trading_days:
        signals = {}
        
        for sym, info in stock_data.items():
            df = info['data']
            if date in df['date'].values:
                idx = df[df['date'] == date].index[0]
                if idx > 0:
                    prev_df = df.iloc[:idx]
                    curr_df = df.iloc[:idx+1]
                    signal, score, reasons = generate_signal(curr_df, prev_df)
                    signals[sym] = {
                        'name': info['name'],
                        'signal': signal,
                        'score': score,
                        'reasons': reasons,
                        'price': curr_df.iloc[-1]['Close']
                    }
        
        if not signals:
            continue
        
        date_str = date.strftime('%Y-%m-%d')
        buy_signals = {k: v for k, v in signals.items() if v['signal'] in ['strong_buy', 'buy']}
        sell_signals = {k: v for k, v in signals.items() if v['signal'] in ['strong_sell', 'sell']}
        
        # 买入
        if buy_signals and position == 0:
            best = max(buy_signals.items(), key=lambda x: x[1]['score'])
            sym, sig = best
            
            buy_amount = capital * 0.3
            price = sig['price']
            shares = int(buy_amount / price)
            
            if shares > 0:
                cost = shares * price
                capital -= cost
                position = shares
                position_symbol = sym
                position_price = price
                position_name = sig['name']
                
                print(f"[{date_str}] 买入 {position_name}")
                print(f"         价格: ¥{price:.2f}, 数量: {shares}股")
                print(f"         金额: ¥{cost:,.2f}")
                print(f"         资金余额: ¥{capital:,.2f}")
                print(f"         信号: {', '.join(sig['reasons'])}")
                print()
                
                trades.append({
                    'date': date_str,
                    'action': 'buy',
                    'symbol': sym,
                    'name': position_name,
                    'shares': shares,
                    'price': price,
                    'amount': cost,
                    'capital_before': cost + capital,
                    'capital_after': capital,
                    'reasons': sig['reasons'],
                    'score': sig['score']
                })
        
        # 卖出
        elif position > 0 and sell_signals:
            price = sell_signals[position_symbol]['price'] if position_symbol in sell_signals else None
            if price:
                sig = sell_signals[position_symbol]
                revenue = position * price
                profit = revenue - (position * position_price)
                profit_pct = (profit / (position * position_price)) * 100
                
                print(f"[{date_str}] 卖出 {position_name}")
                print(f"         价格: ¥{price:.2f}, 数量: {position}股")
                print(f"         金额: ¥{revenue:,.2f}")
                print(f"         收益: ¥{profit:,.2f} ({profit_pct:+.2f}%)")
                print(f"         信号: {', '.join(sig['reasons'])}")
                print()
                
                trades.append({
                    'date': date_str,
                    'action': 'sell',
                    'symbol': position_symbol,
                    'name': position_name,
                    'shares': position,
                    'price': price,
                    'amount': revenue,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'capital_before': capital,
                    'capital_after': capital + revenue,
                    'reasons': sig['reasons'],
                    'score': sig['score']
                })
                
                capital += revenue
                position = 0
                position_symbol = None
                position_name = None
    
    print(f"{'='*70}")
    print(f"回测结束")
    print(f"{'='*70}")
    
    if position > 0:
        final_price = stock_data[position_symbol]['data'].iloc[-1]['Close']
        final_value = position * final_price
        unrealized = (final_price - position_price) / position_price * 100
        print(f"\n最终持仓:")
        print(f"  股票: {position_name}")
        print(f"  数量: {position}股")
        print(f"  价格: ¥{final_price:.2f}")
        print(f"  市值: ¥{final_value:,.2f}")
        print(f"  浮动盈亏: {unrealized:+.2f}%")
        capital = final_value
    
    sell_trades = [t for t in trades if t['action'] == 'sell']
    winning = [t for t in sell_trades if t.get('profit', 0) > 0]
    losing = [t for t in sell_trades if t.get('profit', 0) <= 0]
    
    print(f"\n{'='*70}")
    print(f"回测统计")
    print(f"{'='*70}")
    print(f"初始资金:    ¥{INITIAL_CAPITAL:>15,.2f}")
    print(f"最终资金:    ¥{capital:>15,.2f}")
    print(f"总收益:      ¥{capital - INITIAL_CAPITAL:>15,.2f}")
    print(f"收益率:      {(capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100:>14,.2f}%")
    print(f"交易次数:    {len(trades):>15}")
    
    if sell_trades:
        print(f"盈利次数:    {len(winning):>15}")
        print(f"亏损次数:    {len(losing):>15}")
        print(f"胜率:        {len(winning) / len(sell_trades) * 100:>14,.1f}%")
        if winning:
            print(f"最大盈利:    ¥{max(t['profit'] for t in winning):>15,.2f}")
        if losing:
            print(f"最大亏损:    ¥{min(t['profit'] for t in losing):>15,.2f}")
    elif trades:
        print(f"\n当前持仓中...")
    
    result = {
        'initial_capital': INITIAL_CAPITAL,
        'final_capital': capital,
        'total_profit': capital - INITIAL_CAPITAL,
        'profit_pct': (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100,
        'total_trades': len(trades),
        'buy_trades': len(trades) - len(sell_trades),
        'sell_trades': len(sell_trades),
        'winning_trades': len(winning),
        'losing_trades': len(losing),
        'win_rate': len(winning) / len(sell_trades) * 100 if sell_trades else 0,
        'trades': trades,
        'symbols': SYMBOLS,
        'run_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    os.makedirs('data', exist_ok=True)
    with open('data/backtest_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n回测结果已保存到 data/backtest_result.json")
    
    return result


if __name__ == '__main__':
    run_backtest()

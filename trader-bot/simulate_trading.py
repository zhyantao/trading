"""
量化交易模拟器 - 模拟数据版
使用100万人民币，基于模拟数据进行每日交易演示
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import random

# 设置随机种子以保证可复现
np.random.seed(42)
random.seed(42)

# 初始资金
INITIAL_CAPITAL = 1000000  # 100万人民币


def generate_mock_data(symbol, name, days=90):
    """生成模拟股票数据"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # 模拟价格走势
    base_price = random.uniform(10, 500)
    prices = [base_price]
    for i in range(1, days):
        change = np.random.normal(0, 0.02)  # 日波动约2%
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, 1))  # 确保价格不为负
    
    df = pd.DataFrame({
        'date': dates,
        'open': [p * random.uniform(0.98, 1.02) for p in prices],
        'high': [p * random.uniform(1.00, 1.05) for p in prices],
        'low': [p * random.uniform(0.95, 1.00) for p in prices],
        'close': prices,
        'volume': [random.randint(1000000, 10000000) for _ in range(days)],
    })
    
    return df


def calculate_indicators(df):
    """计算技术指标"""
    # 均线
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
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
    
    # 均线趋势
    if pd.notna(latest['ma5']) and pd.notna(latest['ma10']) and pd.notna(latest['ma20']):
        if latest['ma5'] > latest['ma10'] > latest['ma20']:
            score += 2
            reasons.append('均线多头排列')
        elif latest['ma5'] < latest['ma10'] < latest['ma20']:
            score -= 2
            reasons.append('均线空头排列')
    
    # RSI
    if pd.notna(latest['rsi']):
        if latest['rsi'] < 30:
            score += 2
            reasons.append(f'RSI超卖({latest["rsi"]:.1f})')
        elif latest['rsi'] > 70:
            score -= 2
            reasons.append(f'RSI超买({latest["rsi"]:.1f})')
    
    # MACD金叉/死叉
    if pd.notna(latest['macd']) and pd.notna(latest['macd_signal']):
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            score += 2
            reasons.append('MACD金叉')
        elif latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            score -= 2
            reasons.append('MACD死叉')
    
    # 给出建议
    if score >= 3:
        return 'strong_buy', score, reasons
    elif score >= 1:
        return 'buy', score, reasons
    elif score <= -3:
        return 'strong_sell', score, reasons
    elif score <= -1:
        return 'sell', score, reasons
    else:
        return 'hold', score, reasons


def run_simulation():
    """运行模拟交易"""
    print(f"{'='*70}")
    print(f"量化交易模拟器 (模拟数据演示)")
    print(f"{'='*70}")
    print(f"初始资金: {INITIAL_CAPITAL:,.2f} 元")
    print(f"模拟周期: 最近3个月 (60个交易日)")
    print(f"{'='*70}\n")
    
    # 模拟股票数据
    SYMBOLS = [
        {'code': 'SH000001', 'name': '上证指数', 'base_price': 3200},
        {'code': 'SH399001', 'name': '深证成指', 'base_price': 10500},
        {'code': 'SZ000001', 'name': '平安银行', 'base_price': 12.5},
        {'code': 'SH600519', 'name': '贵州茅台', 'base_price': 1650},
        {'code': 'SH600036', 'name': '招商银行', 'base_price': 35},
    ]
    
    print("正在生成模拟股票数据...")
    stock_data = {}
    for sym in SYMBOLS:
        df = generate_mock_data(sym['code'], sym['name'], days=90)
        df = calculate_indicators(df)
        stock_data[sym['code']] = {
            'name': sym['name'],
            'data': df
        }
        print(f"  - {sym['name']}: {len(df)} 条数据")
    
    # 模拟交易
    capital = INITIAL_CAPITAL
    position = 0
    position_symbol = None
    position_price = 0
    trades = []
    
    # 最近60个交易日
    first_symbol = list(stock_data.keys())[0]
    trading_days = stock_data[first_symbol]['data'].tail(60)['date'].tolist()
    
    print(f"\n开始模拟交易 (共 {len(trading_days)} 个交易日)")
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
                        'price': curr_df.iloc[-1]['close']
                    }
        
        if not signals:
            continue
        
        # 找到最强信号
        buy_signals = {k: v for k, v in signals.items() if v['signal'] in ['strong_buy', 'buy']}
        sell_signals = {k: v for k, v in signals.items() if v['signal'] in ['strong_sell', 'sell']}
        
        date_str = date.strftime('%Y-%m-%d')
        
        # 买入条件
        if buy_signals and position == 0:
            best = max(buy_signals.items(), key=lambda x: x[1]['score'])
            sym, sig = best
            
            # 用30%资金买入
            buy_amount = capital * 0.3
            price = sig['price']
            shares = int(buy_amount / price / 100) * 100
            if shares > 0:
                cost = shares * price
                capital -= cost
                position = shares
                position_symbol = sym
                position_price = price
                
                print(f"[{date_str}] 买入 {sig['name']}")
                print(f"         数量: {shares}股 @ ¥{price:.2f}")
                print(f"         金额: ¥{cost:,.2f}")
                print(f"         原因: {', '.join(sig['reasons'])}")
                print(f"         资金余额: ¥{capital:,.2f}")
                print()
                
                trades.append({
                    'date': date_str,
                    'action': 'buy',
                    'symbol': sym,
                    'name': sig['name'],
                    'shares': shares,
                    'price': price,
                    'amount': cost,
                    'reasons': sig['reasons']
                })
        
        # 卖出条件
        elif sell_signals and position > 0:
            sig = sell_signals.get(position_symbol)
            if sig:
                price = sig['price']
                revenue = position * price
                profit = revenue - (position * position_price)
                profit_pct = (profit / (position * position_price)) * 100
                
                print(f"[{date_str}] 卖出 {sig['name']}")
                print(f"         数量: {position}股 @ ¥{price:.2f}")
                print(f"         金额: ¥{revenue:,.2f}")
                print(f"         收益: ¥{profit:,.2f} ({profit_pct:+.2f}%)")
                print(f"         原因: {', '.join(sig['reasons'])}")
                print(f"         资金余额: ¥{capital + revenue:,.2f}")
                print()
                
                trades.append({
                    'date': date_str,
                    'action': 'sell',
                    'symbol': sym,
                    'name': sig['name'],
                    'shares': position,
                    'price': price,
                    'amount': revenue,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'reasons': sig['reasons']
                })
                
                capital += revenue
                position = 0
                position_symbol = None
    
    # 最终持仓
    print(f"{'='*70}")
    print(f"模拟结束")
    print(f"{'='*70}")
    
    if position > 0:
        final_price = stock_data[position_symbol]['data'].iloc[-1]['close']
        final_value = position * final_price
        unrealized = (final_price - position_price) / position_price * 100
        print(f"\n最终持仓:")
        print(f"  股票: {stock_data[position_symbol]['name']}")
        print(f"  数量: {position}股")
        print(f"  价格: ¥{final_price:.2f}")
        print(f"  市值: ¥{final_value:,.2f}")
        print(f"  浮动盈亏: {unrealized:+.2f}%")
        capital = final_value
    
    # 统计
    print(f"\n{'='*70}")
    print(f"交易统计")
    print(f"{'='*70}")
    print(f"初始资金:   ¥{INITIAL_CAPITAL:>15,.2f}")
    print(f"最终资金:   ¥{capital:>15,.2f}")
    print(f"总收益:     ¥{capital - INITIAL_CAPITAL:>15,.2f}")
    print(f"收益率:     {(capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100:>14,.2f}%")
    print(f"交易次数:   {len(trades):>15}")
    
    sell_trades = [t for t in trades if t['action'] == 'sell']
    if sell_trades:
        winning = [t for t in sell_trades if t.get('profit', 0) > 0]
        losing = [t for t in sell_trades if t.get('profit', 0) <= 0]
        print(f"盈利次数:   {len(winning):>15}")
        print(f"亏损次数:   {len(losing):>15}")
        print(f"胜率:       {len(winning) / len(sell_trades) * 100:>14,.1f}%")
        
        if winning:
            print(f"最大盈利:   ¥{max(t['profit'] for t in winning):>15,.2f}")
        if losing:
            print(f"最大亏损:   ¥{min(t['profit'] for t in losing):>15,.2f}")
    
    # 保存交易记录
    import os
    os.makedirs('data', exist_ok=True)
    with open('data/simulation_trades.json', 'w', encoding='utf-8') as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)
    
    print(f"\n交易记录已保存到 data/simulation_trades.json")
    
    return trades


if __name__ == '__main__':
    run_simulation()

"""
股票/基金数据查询API - 带模拟数据
"""

from flask import Blueprint, jsonify, request
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import random
import hashlib

stock_api = Blueprint('stock', __name__)

# 用股票代码生成固定的随机种子，保证相同股票数据一致
def get_seed(symbol):
    """根据股票代码生成随机种子"""
    hash_obj = hashlib.md5(symbol.encode())
    return int(hash_obj.hexdigest()[:8], 16)


def generate_mock_quote(symbol):
    """生成模拟报价数据 - 使用固定种子保证一致性"""
    rng = random.Random(get_seed(symbol))
    
    base_prices = {
        '510300': 3.85,
        '159919': 1.12,
        '000001': 12.50,
        '600519': 1650.00,
        'AAPL': 185.50,
        'MSFT': 420.00,
        'GOOGL': 175.00,
        'AMZN': 185.00,
        'TSLA': 245.00,
        'NVDA': 880.00,
    }
    
    base_price = base_prices.get(symbol, rng.uniform(10, 500))
    change = rng.uniform(-5, 5)
    
    return {
        'symbol': symbol,
        'name': f'{symbol}',
        'price': round(base_price, 2),
        'change': round(change, 2),
        'change_pct': round((change / base_price) * 100, 2),
        'volume': rng.randint(1000000, 50000000),
        'market_cap': rng.randint(1000000000, 100000000000),
        'pe_ratio': round(rng.uniform(10, 50), 2),
        'pb_ratio': round(rng.uniform(0.5, 10), 2),
    }


def generate_mock_history(symbol, days=30):
    """生成模拟历史数据 - 使用固定种子保证一致性"""
    rng = random.Random(get_seed(symbol))
    
    base_prices = {
        '510300': 3.85,
        '159919': 1.12,
        '000001': 12.50,
        '600519': 1650.00,
        'AAPL': 185.50,
        'MSFT': 420.00,
    }
    
    base_price = base_prices.get(symbol, 100)
    
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    data = []
    
    price = base_price
    for date in dates:
        change_pct = rng.uniform(-3, 3)
        price = price * (1 + change_pct / 100)
        
        open_price = price * rng.uniform(0.98, 1.02)
        high_price = price * rng.uniform(1.00, 1.05)
        low_price = price * rng.uniform(0.95, 1.00)
        volume = rng.randint(1000000, 50000000)
        
        data.append({
            'Date': date.strftime('%Y-%m-%d'),
            'Open': round(open_price, 2),
            'High': round(high_price, 2),
            'Low': round(low_price, 2),
            'Close': round(price, 2),
            'Volume': volume,
        })
    
    df = pd.DataFrame(data)
    df['涨跌幅'] = df['Close'].pct_change() * 100
    df['涨跌额'] = df['Close'].diff()
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df = df.fillna(0)
    return df.to_dict('records')


def generate_mock_info(symbol):
    """生成模拟详细信息 - 使用固定种子保证一致性"""
    rng = random.Random(get_seed(symbol))
    
    return {
        'basic': {
            'symbol': symbol,
            'name': f'{symbol}',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'industry': 'Software',
        },
        'price': {
            'current_price': round(rng.uniform(10, 500), 2),
            'open': round(rng.uniform(10, 500), 2),
            'previous_close': round(rng.uniform(10, 500), 2),
            'day_high': round(rng.uniform(10, 500), 2),
            'day_low': round(rng.uniform(10, 500), 2),
            '52w_high': round(rng.uniform(10, 500), 2),
            '52w_low': round(rng.uniform(10, 500), 2),
        },
        'market': {
            'market_cap': rng.randint(1000000000, 100000000000),
            'enterprise_value': rng.randint(1000000000, 100000000000),
            'shares_outstanding': rng.randint(100000000, 10000000000),
            'float_shares': rng.randint(100000000, 10000000000),
        },
        'valuation': {
            'pe_ratio': round(rng.uniform(10, 50), 2),
            'forward_pe': round(rng.uniform(10, 40), 2),
            'peg_ratio': round(rng.uniform(0.5, 3), 2),
            'pb_ratio': round(rng.uniform(0.5, 10), 2),
            'ps_ratio': round(rng.uniform(1, 20), 2),
        },
        'finance': {
            'eps': round(rng.uniform(1, 20), 2),
            'forward_eps': round(rng.uniform(1, 25), 2),
            'profit_margin': round(rng.uniform(0.05, 0.30), 4),
            'operating_margin': round(rng.uniform(0.10, 0.35), 4),
            'roe': round(rng.uniform(0.10, 0.30), 4),
            'roa': round(rng.uniform(0.05, 0.15), 4),
            'debt_to_equity': round(rng.uniform(0, 100), 2),
        },
        'dividend': {
            'dividend_yield': round(rng.uniform(0, 0.05), 4),
            'dividend_rate': round(rng.uniform(0, 5), 2),
            'payout_ratio': round(rng.uniform(0, 0.5), 4),
        },
        'risk': {
            'beta': round(rng.uniform(0.5, 2), 2),
            'alpha': round(rng.uniform(-0.2, 0.2), 4),
            'sharpe_ratio': round(rng.uniform(0, 2), 2),
        }
    }


@stock_api.route('/api/stock/quote', methods=['POST'])
def get_quote():
    """获取股票/基金实时报价"""
    data = request.json
    symbol = data.get('symbol', '')
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码'})
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        quote = {
            'symbol': symbol,
            'name': info.get('shortName', info.get('longName', symbol)),
            'price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
            'change': info.get('regularMarketChange', 0),
            'change_pct': info.get('regularMarketChangePercent', 0),
            'volume': info.get('regularMarketVolume', 0),
            'market_cap': info.get('marketCap', 0),
            'pe_ratio': info.get('trailingPE', 0),
            'pb_ratio': info.get('priceToBook', 0),
        }
        
        return jsonify({'success': True, 'data': quote})
        
    except Exception as e:
        error_msg = str(e)
        if 'Rate limited' in error_msg or 'Too Many Requests' in error_msg:
            return jsonify({
                'success': True, 
                'data': generate_mock_quote(symbol),
                'mock': True,
                'note': '使用模拟数据（yfinance频率限制）'
            })
        return jsonify({'success': False, 'error': error_msg})


@stock_api.route('/api/stock/history', methods=['POST'])
def get_history():
    """获取股票历史数据"""
    data = request.json
    symbol = data.get('symbol', '')
    period = data.get('period', '1mo')
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码'})
    
    try:
        ticker = yf.Ticker(symbol)
        period_map = {'1mo': '1mo', '3mo': '3mo', '6mo': '6mo', '1y': '1y'}
        yf_period = period_map.get(period, '1mo')
        
        df = ticker.history(period=yf_period, interval="1d")
        
        if df.empty:
            raise Exception("No data available")
        
        df = df.reset_index()
        df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits']
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        
        df['涨跌幅'] = df['Close'].pct_change() * 100
        df['涨跌额'] = df['Close'].diff()
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        df = df.fillna(0)
        
        return jsonify({
            'success': True, 
            'data': df.to_dict('records'),
            'symbol': symbol,
            'period': period
        })
        
    except Exception as e:
        error_msg = str(e)
        if 'Rate limited' in error_msg or 'Too Many Requests' in error_msg or 'No data' in error_msg:
            days = {'1mo': 30, '3mo': 90, '6mo': 180, '1y': 365}.get(period, 30)
            return jsonify({
                'success': True, 
                'data': generate_mock_history(symbol, days),
                'symbol': symbol,
                'period': period,
                'mock': True,
                'note': '使用模拟数据（yfinance频率限制）'
            })
        return jsonify({'success': False, 'error': error_msg})


@stock_api.route('/api/stock/info', methods=['POST'])
def get_info():
    """获取股票详细信息"""
    data = request.json
    symbol = data.get('symbol', '')
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码'})
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        result = {
            'basic': {
                'symbol': symbol,
                'name': info.get('shortName', info.get('longName', 'N/A')),
                'exchange': info.get('exchange', 'N/A'),
                'currency': info.get('currency', 'CNY'),
                'sector': info.get('sector', 'N/A'),
                'industry': info.get('industry', 'N/A'),
            },
            'price': {
                'current_price': info.get('currentPrice', 0),
                'open': info.get('regularMarketOpen', 0),
                'previous_close': info.get('regularMarketPreviousClose', 0),
                'day_high': info.get('regularMarketDayHigh', 0),
                'day_low': info.get('regularMarketDayLow', 0),
                '52w_high': info.get('fiftyTwoWeekHigh', 0),
                '52w_low': info.get('fiftyTwoWeekLow', 0),
            },
            'market': {
                'market_cap': info.get('marketCap', 0),
                'enterprise_value': info.get('enterpriseValue', 0),
                'shares_outstanding': info.get('sharesOutstanding', 0),
                'float_shares': info.get('floatShares', 0),
            },
            'valuation': {
                'pe_ratio': info.get('trailingPE', 0),
                'forward_pe': info.get('forwardPE', 0),
                'peg_ratio': info.get('pegRatio', 0),
                'pb_ratio': info.get('priceToBook', 0),
                'ps_ratio': info.get('priceToSalesTrailing12Months', 0),
            },
            'finance': {
                'eps': info.get('trailingEps', 0),
                'forward_eps': info.get('forwardEps', 0),
                'profit_margin': info.get('profitMargins', 0),
                'operating_margin': info.get('operatingMargins', 0),
                'roe': info.get('returnOnEquity', 0),
                'roa': info.get('returnOnAssets', 0),
                'debt_to_equity': info.get('debtToEquity', 0),
            },
            'dividend': {
                'dividend_yield': info.get('dividendYield', 0),
                'dividend_rate': info.get('dividendRate', 0),
                'payout_ratio': info.get('payoutRatio', 0),
            },
            'risk': {
                'beta': info.get('beta', 0),
                'alpha': info.get('alpha', 0),
                'sharpe_ratio': info.get('sharpeRatio', 0),
            }
        }
        
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        error_msg = str(e)
        if 'Rate limited' in error_msg or 'Too Many Requests' in error_msg:
            return jsonify({
                'success': True, 
                'data': generate_mock_info(symbol),
                'mock': True,
                'note': '使用模拟数据（yfinance频率限制）'
            })
        return jsonify({'success': False, 'error': error_msg})

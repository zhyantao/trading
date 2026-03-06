"""
股票/基金数据查询API
"""

from flask import Blueprint, jsonify, request
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta

stock_api = Blueprint('stock', __name__)


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
            'dividend': info.get('dividendYield', 0),
            'dividend_rate': info.get('dividendRate', 0),
            'eps': info.get('trailingEps', 0),
            'beta': info.get('beta', 0),
            'high_52w': info.get('fiftyTwoWeekHigh', 0),
            'low_52w': info.get('fiftyTwoWeekLow', 0),
            'open': info.get('regularMarketOpen', 0),
            'previous_close': info.get('regularMarketPreviousClose', 0),
            'day_high': info.get('regularMarketDayHigh', 0),
            'day_low': info.get('regularMarketDayLow', 0),
        }
        
        return jsonify({'success': True, 'data': quote})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@stock_api.route('/api/stock/history', methods=['POST'])
def get_history():
    """获取股票历史数据"""
    data = request.json
    symbol = data.get('symbol', '')
    period = data.get('period', '1mo')  # 1mo, 3mo, 6mo, 1y
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码'})
    
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d")
        
        if df.empty:
            return jsonify({'success': False, 'error': '无法获取数据'})
        
        df = df.reset_index()
        df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits']
        
        # 转换日期格式
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        
        # 选择需要的列
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        
        # 计算常用指标
        df['涨跌幅'] = df['Close'].pct_change() * 100
        df['涨跌额'] = df['Close'].diff()
        df['成交量'] = df['Volume']
        df['成交额'] = df['Close'] * df['Volume']
        
        # 计算均线
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        # 计算成交量均线
        df['VOL_MA5'] = df['Volume'].rolling(window=5).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 填充NaN
        df = df.fillna(0)
        
        # 转换为字典列表
        records = df.to_dict('records')
        
        return jsonify({
            'success': True, 
            'data': records,
            'symbol': symbol,
            'period': period
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


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
        
        # 基本信息
        basic = {
            'symbol': symbol,
            'name': info.get('shortName', info.get('longName', 'N/A')),
            'exchange': info.get('exchange', 'N/A'),
            'currency': info.get('currency', 'CNY'),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
        }
        
        # 股价数据
        price = {
            'current_price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
            'open': info.get('regularMarketOpen', 0),
            'previous_close': info.get('regularMarketPreviousClose', 0),
            'day_high': info.get('regularMarketDayHigh', 0),
            'day_low': info.get('regularMarketDayLow', 0),
            '52w_high': info.get('fiftyTwoWeekHigh', 0),
            '52w_low': info.get('fiftyTwoWeekLow', 0),
        }
        
        # 市值数据
        market = {
            'market_cap': info.get('marketCap', 0),
            'enterprise_value': info.get('enterpriseValue', 0),
            'shares_outstanding': info.get('sharesOutstanding', 0),
            'float_shares': info.get('floatShares', 0),
        }
        
        # 估值指标
        valuation = {
            'pe_ratio': info.get('trailingPE', 0),
            'forward_pe': info.get('forwardPE', 0),
            'peg_ratio': info.get('pegRatio', 0),
            'pb_ratio': info.get('priceToBook', 0),
            'ps_ratio': info.get('priceToSalesTrailing12Months', 0),
            'enterprise_pb': info.get('enterpriseToRevenue', 0),
        }
        
        # 财务指标
        finance = {
            'eps': info.get('trailingEps', 0),
            'forward_eps': info.get('forwardEps', 0),
            'revenue': info.get('totalRevenue', 0),
            'revenue_per_share': info.get('revenuePerShare', 0),
            'profit_margin': info.get('profitMargins', 0),
            'operating_margin': info.get('operatingMargins', 0),
            'roe': info.get('returnOnEquity', 0),
            'roa': info.get('returnOnAssets', 0),
            'debt_to_equity': info.get('debtToEquity', 0),
            'current_ratio': info.get('currentRatio', 0),
            'quick_ratio': info.get('quickRatio', 0),
        }
        
        # 分红送转
        dividend = {
            'dividend_yield': info.get('dividendYield', 0),
            'dividend_rate': info.get('dividendRate', 0),
            'ex_dividend_date': info.get('exDividendDate', 'N/A'),
            'payout_ratio': info.get('payoutRatio', 0),
        }
        
        # 风险指标
        risk = {
            'beta': info.get('beta', 0),
            'volatility': info.get('volatility', 0),
            'alpha': info.get('alpha', 0),
            'sharpe_ratio': info.get('sharpeRatio', 0),
        }
        
        return jsonify({
            'success': True,
            'data': {
                'basic': basic,
                'price': price,
                'market': market,
                'valuation': valuation,
                'finance': finance,
                'dividend': dividend,
                'risk': risk,
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

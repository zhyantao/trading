"""
股票/基金数据查询API - 支持多数据源
"""

from flask import Blueprint, jsonify, request
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta

stock_api = Blueprint('stock', __name__)

# A股常见股票的中文名称映射
STOCK_NAMES = {
    '510300': '沪深300ETF',
    '159919': '券商ETF',
    '512880': '证券ETF',
    '159995': '券商ETF',
    '159792': '科技ETF',
    '000001': '平安银行',
    '600036': '招商银行',
    '601398': '工商银行',
    '601939': '建设银行',
    '600519': '贵州茅台',
    '000858': '五粮液',
    '000333': '美的集团',
    '000568': '泸州老窖',
    '002594': '比亚迪',
    '600900': '长江电力',
    '601318': '中国平安',
    '600276': '恒瑞医药',
    '300750': '宁德时代',
    '002311': '海大集团',
    '600522': '中天科技',
    '002202': '金风科技',
    '600438': '通威股份',
    '688981': '中芯国际',
    '603986': '兆易创新',
    '002475': '立讯精密',
    '600030': '中信证券',
    '601211': '国泰君安',
    '688111': '华大基因',
    '000651': '格力电器',
    '600887': '伊利股份',
}


@stock_api.route('/api/stock/quote', methods=['POST'])
def get_quote():
    """获取股票/基金实时报价"""
    data = request.json
    symbol = data.get('symbol', '').strip().upper()
    source = data.get('source', 'yfinance')
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码', 'source': source})
    
    try:
        if source == 'yfinance':
            return get_quote_yfinance(symbol)
        else:
            return jsonify({'success': False, 'error': f'不支持的数据源: {source}', 'source': source})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'source': source})


def get_quote_yfinance(symbol):
    """使用yfinance获取报价"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        name = info.get('shortName') or info.get('longName') or STOCK_NAMES.get(symbol, symbol)
        
        quote = {
            'symbol': symbol,
            'name': name,
            'price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
            'change': info.get('regularMarketChange', 0),
            'change_pct': info.get('regularMarketChangePercent', 0),
            'volume': info.get('regularMarketVolume', 0),
            'market_cap': info.get('marketCap', 0),
            'pe_ratio': info.get('trailingPE', 0),
            'pb_ratio': info.get('priceToBook', 0),
        }
        
        return jsonify({'success': True, 'data': quote, 'source': 'yfinance'})
        
    except Exception as e:
        error_msg = str(e)
        
        # 详细错误分析
        if 'Rate limited' in error_msg or 'Too Many Requests' in error_msg:
            detail = 'yfinance请求被限流 (Too Many Requests)。可能原因：短时间内请求过多，或您的IP被Yahoo Finance限制。建议：等待几分钟后重试，或使用VPN/代理。'
        elif 'No credentials' in error_msg or 'authentication' in error_msg.lower():
            detail = 'yfinance认证失败。请检查网络连接。'
        elif 'Connection' in error_msg or 'timeout' in error_msg.lower() or 'SOCKS' in error_msg:
            detail = '无法连接到Yahoo Finance服务器。请检查网络连接，或使用VPN/代理解决中国大陆访问限制问题。'
        elif 'Symbol' in error_msg or 'Not Found' in error_msg:
            detail = f'股票代码 {symbol} 不存在或已下市。'
        else:
            detail = f'yfinance异常: {error_msg}'
        
        return jsonify({
            'success': False, 
            'error': detail,
            'error_raw': error_msg,
            'source': 'yfinance',
            'suggestion': '请检查网络连接，或使用VPN/代理访问Yahoo Finance'
        })


@stock_api.route('/api/stock/history', methods=['POST'])
def get_history():
    """获取股票历史数据"""
    data = request.json
    symbol = data.get('symbol', '').strip().upper()
    period = data.get('period', '1mo')
    source = data.get('source', 'yfinance')
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码', 'source': source})
    
    try:
        if source == 'yfinance':
            return get_history_yfinance(symbol, period)
        else:
            return jsonify({'success': False, 'error': f'不支持的数据源: {source}', 'source': source})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'source': source})


def get_history_yfinance(symbol, period):
    """使用yfinance获取历史数据"""
    try:
        ticker = yf.Ticker(symbol)
        
        period_map = {'1mo': '1mo', '3mo': '3mo', '6mo': '6mo', '1y': '1y', '1d': '5d'}
        yf_period = period_map.get(period, '1mo')
        
        df = ticker.history(period=yf_period, interval="1d")
        
        if df.empty:
            return jsonify({
                'success': False,
                'error': f'股票代码 {symbol} 无历史数据。可能原因：代码错误、已退市、或数据源不支持。',
                'source': 'yfinance'
            })
        
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
            'period': period,
            'source': 'yfinance'
        })
        
    except Exception as e:
        error_msg = str(e)
        
        if 'Rate limited' in error_msg or 'Too Many Requests' in error_msg:
            detail = 'yfinance请求被限流 (Too Many Requests)。建议：等待几分钟后重试。'
        elif 'Connection' in error_msg or 'timeout' in error_msg.lower() or 'SOCKS' in error_msg:
            detail = '无法连接到Yahoo Finance服务器。请检查网络连接，或使用VPN/代理。'
        elif 'Symbol' in error_msg or 'Not Found' in error_msg:
            detail = f'股票代码 {symbol} 不存在。'
        else:
            detail = f'yfinance异常: {error_msg}'
        
        return jsonify({
            'success': False, 
            'error': detail,
            'error_raw': error_msg,
            'source': 'yfinance',
            'suggestion': '请检查网络连接'
        })


@stock_api.route('/api/stock/info', methods=['POST'])
def get_info():
    """获取股票详细信息"""
    data = request.json
    symbol = data.get('symbol', '').strip().upper()
    source = data.get('source', 'yfinance')
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码', 'source': source})
    
    try:
        if source == 'yfinance':
            return get_info_yfinance(symbol)
        else:
            return jsonify({'success': False, 'error': f'不支持的数据源: {source}', 'source': source})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'source': source})


def get_info_yfinance(symbol):
    """使用yfinance获取详细信息"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        name = info.get('shortName') or info.get('longName') or STOCK_NAMES.get(symbol, symbol)
        
        result = {
            'basic': {
                'symbol': symbol,
                'name': name,
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
        
        return jsonify({'success': True, 'data': result, 'source': 'yfinance'})
        
    except Exception as e:
        error_msg = str(e)
        
        if 'Rate limited' in error_msg or 'Too Many Requests' in error_msg:
            detail = 'yfinance请求被限流。请稍后重试。'
        elif 'Connection' in error_msg or 'timeout' in error_msg.lower():
            detail = '无法连接到Yahoo Finance服务器。请检查网络连接。'
        else:
            detail = f'yfinance异常: {error_msg}'
        
        return jsonify({
            'success': False, 
            'error': detail,
            'error_raw': error_msg,
            'source': 'yfinance'
        })

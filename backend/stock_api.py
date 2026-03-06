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


def get_akshare():
    """获取akshare模块"""
    try:
        import akshare as ak
        return ak
    except ImportError:
        return None


@stock_api.route('/api/stock/quote', methods=['POST'])
def get_quote():
    """获取股票/基金实时报价"""
    data = request.json
    symbol = data.get('symbol', '').strip().upper()
    source = data.get('source', 'yfinance')
    
    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码', 'source': source})
    
    if source == 'yfinance':
        return get_quote_yfinance(symbol)
    elif source == 'akshare':
        return get_quote_akshare(symbol)
    elif source == 'tushare':
        return jsonify({'success': False, 'error': 'tushare需要token，请在环境变量中设置TUSHARE_TOKEN，或访问 https://tushare.pro 注册获取', 'source': 'tushare'})
    else:
        return jsonify({'success': False, 'error': f'不支持的数据源: {source}', 'source': source})


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


def get_quote_akshare(symbol):
    """使用akshare获取A股报价"""
    try:
        ak = get_akshare()
        if ak is None:
            return jsonify({'success': False, 'error': 'akshare未安装，请运行: pip install akshare', 'source': 'akshare'})
        
        # 判断是A股还是ETF
        if symbol.isdigit() and len(symbol) == 6:
            # A股代码
            if symbol.startswith('6'):
                stock_type = 'sh'
            else:
                stock_type = 'sz'
            full_symbol = f"{stock_type}{symbol}"
        else:
            full_symbol = symbol
        
        # 获取实时行情
        df = ak.stock_zh_a_spot_em()
        
        # 查找对应股票
        stock_info = df[df['代码'] == symbol]
        
        if stock_info.empty:
            # 尝试ETF
            try:
                df_etf = ak.fund_etf_spot_em()
                stock_info = df_etf[df_etf['代码'] == symbol]
                if stock_info.empty:
                    return jsonify({'success': False, 'error': f'未找到股票 {symbol}，请检查代码是否正确', 'source': 'akshare'})
                row = stock_info.iloc[0]
            except:
                return jsonify({'success': False, 'error': f'未找到股票 {symbol}，请检查代码是否正确', 'source': 'akshare'})
        else:
            row = stock_info.iloc[0]
        
        quote = {
            'symbol': symbol,
            'name': row.get('名称', symbol),
            'price': float(row.get('最新价', 0)) if pd.notna(row.get('最新价')) else 0,
            'change': float(row.get('涨跌幅', 0)) if pd.notna(row.get('涨跌幅')) else 0,
            'change_pct': float(row.get('涨跌幅', 0)) if pd.notna(row.get('涨跌幅')) else 0,
            'volume': int(row.get('成交量', 0)) if pd.notna(row.get('成交量')) else 0,
            'amount': float(row.get('成交额', 0)) if pd.notna(row.get('成交额')) else 0,
            'open': float(row.get('今开', 0)) if pd.notna(row.get('今开')) else 0,
            'high': float(row.get('最高', 0)) if pd.notna(row.get('最高')) else 0,
            'low': float(row.get('最低', 0)) if pd.notna(row.get('最低')) else 0,
            'prev_close': float(row.get('昨收', 0)) if pd.notna(row.get('昨收')) else 0,
        }
        
        return jsonify({'success': True, 'data': quote, 'source': 'akshare'})
        
    except Exception as e:
        error_msg = str(e)
        
        if 'Connection' in error_msg or 'timeout' in error_msg.lower():
            detail = '无法连接到东方财富服务器。请检查网络连接。'
        elif 'HTTPError' in error_msg:
            detail = '东方财富请求失败，可能需要代理或股票代码不存在。'
        else:
            detail = f'akshare异常: {error_msg}'
        
        return jsonify({
            'success': False, 
            'error': detail,
            'error_raw': error_msg,
            'source': 'akshare',
            'suggestion': '请检查网络连接，或使用VPN/代理'
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
    
    if source == 'yfinance':
        return get_history_yfinance(symbol, period)
    elif source == 'akshare':
        return get_history_akshare(symbol, period)
    elif source == 'tushare':
        return jsonify({'success': False, 'error': 'tushare需要token，请在环境变量中设置TUSHARE_TOKEN', 'source': 'tushare'})
    else:
        return jsonify({'success': False, 'error': f'不支持的数据源: {source}', 'source': source})


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


def get_history_akshare(symbol, period):
    """使用akshare获取A股历史数据"""
    try:
        ak = get_akshare()
        if ak is None:
            return jsonify({'success': False, 'error': 'akshare未安装，请运行: pip install akshare', 'source': 'akshare'})
        
        # 判断是A股还是ETF
        if symbol.isdigit() and len(symbol) == 6:
            if symbol.startswith('6'):
                stock_type = 'sh'
                full_symbol = f"sh{symbol}"
            else:
                stock_type = 'sz'
                full_symbol = f"sz{symbol}"
        else:
            full_symbol = symbol
            stock_type = None
        
        # 获取历史K线
        days_map = {'1mo': '30', '3mo': '90', '6mo': '180', '1y': '250', '1d': '5'}
        days = days_map.get(period, '30')
        
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=(datetime.now() - timedelta(days=int(days)+30)).strftime('%Y%m%d'), end_date=datetime.now().strftime('%Y%m%d'), adjust="qfq")
        except Exception as e:
            # 尝试不复权
            try:
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=(datetime.now() - timedelta(days=int(days)+30)).strftime('%Y%m%d'), end_date=datetime.now().strftime('%Y%m%d'), adjust="qfq")
            except:
                return jsonify({'success': False, 'error': f'获取历史数据失败: {str(e)}', 'source': 'akshare'})
        
        if df.empty:
            return jsonify({'success': False, 'error': f'股票 {symbol} 无历史数据', 'source': 'akshare'})
        
        # 整理数据
        df = df.rename(columns={
            '日期': 'Date',
            '开盘': 'Open',
            '收盘': 'Close',
            '最高': 'High',
            '最低': 'Low',
            '成交量': 'Volume',
            '成交额': 'Amount',
            '振幅': 'Amplitude',
            '涨跌幅': '涨跌幅',
            '涨跌额': '涨跌额',
            '换手率': 'Turnover'
        })
        
        # 转换日期格式
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        
        # 计算技术指标
        df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce').fillna(0)
        df['涨跌额'] = pd.to_numeric(df['涨跌额'], errors='coerce').fillna(0)
        
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        df = df.fillna(0)
        
        # 只返回需要的列
        result = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume', '涨跌幅', '涨跌额', 'MA5', 'MA10', 'MA20', 'RSI']].to_dict('records')
        
        return jsonify({
            'success': True, 
            'data': result,
            'symbol': symbol,
            'period': period,
            'source': 'akshare'
        })
        
    except Exception as e:
        error_msg = str(e)
        
        if 'Connection' in error_msg or 'timeout' in error_msg.lower():
            detail = '无法连接到东方财富服务器。请检查网络连接。'
        elif 'HTTPError' in error_msg:
            detail = '东方财富请求失败，可能需要代理或股票代码不存在。'
        else:
            detail = f'akshare异常: {error_msg}'
        
        return jsonify({
            'success': False, 
            'error': detail,
            'error_raw': error_msg,
            'source': 'akshare',
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
    
    if source == 'yfinance':
        return get_info_yfinance(symbol)
    elif source == 'akshare':
        return get_info_akshare(symbol)
    elif source == 'tushare':
        return jsonify({'success': False, 'error': 'tushare需要token，请在环境变量中设置TUSHARE_TOKEN', 'source': 'tushare'})
    else:
        return jsonify({'success': False, 'error': f'不支持的数据源: {source}', 'source': source})


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


def get_info_akshare(symbol):
    """使用akshare获取A股详细信息"""
    try:
        ak = get_akshare()
        if ak is None:
            return jsonify({'success': False, 'error': 'akshare未安装', 'source': 'akshare'})
        
        if not (symbol.isdigit() and len(symbol) == 6):
            return jsonify({'success': False, 'error': 'akshare暂仅支持A股(6位数字代码)', 'source': 'akshare'})
        
        # 获取股票基本信息
        try:
            df = ak.stock_individual_info_em(symbol=symbol)
            
            if df is None or df.empty:
                return jsonify({'success': False, 'error': f'未找到股票 {symbol} 的信息', 'source': 'akshare'})
            
            info_dict = dict(zip(df['item'], df['value']))
            
            result = {
                'basic': {
                    'symbol': symbol,
                    'name': info_dict.get('股票简称', symbol),
                    'exchange': '上交所' if symbol.startswith('6') else '深交所',
                    'sector': info_dict.get('行业', 'N/A'),
                    'industry': info_dict.get('细分行业', 'N/A'),
                },
                'price': {
                    'current_price': float(info_dict.get('最新价', 0)) if info_dict.get('最新价') else 0,
                },
                'market': {
                    'total_share': float(info_dict.get('总股本(万股)', 0)) * 10000 if info_dict.get('总股本(万股)') else 0,
                    'float_share': float(info_dict.get('流通股本(万股)', 0)) * 10000 if info_dict.get('流通股本(万股)') else 0,
                },
                'valuation': {
                    'pe_ratio': float(info_dict.get('市盈率-动态', 0)) if info_dict.get('市盈率-动态') else 0,
                    'pb_ratio': float(info_dict.get('市净率', 0)) if info_dict.get('市净率') else 0,
                },
                'finance': {
                    'eps': float(info_dict.get('每股收益', 0)) if info_dict.get('每股收益') else 0,
                    'roe': float(info_dict.get('净资产收益率', 0).replace('%', '')) / 100 if info_dict.get('净资产收益率') else 0,
                },
                'dividend': {
                    'dividend_yield': float(info_dict.get('股息率', 0).replace('%', '')) / 100 if info_dict.get('股息率') else 0,
                },
                'risk': {}
            }
            
            return jsonify({'success': True, 'data': result, 'source': 'akshare'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'获取信息失败: {str(e)}', 'source': 'akshare'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'akshare异常: {str(e)}', 'source': 'akshare'})

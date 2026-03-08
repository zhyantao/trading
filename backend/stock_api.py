"""
股票数据API - 使用东方财富直接API
"""

from flask import Blueprint, jsonify, request
import requests
import json
import logging
from datetime import datetime, timedelta
import pandas as pd

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

stock_api = Blueprint('stock', __name__)

# 东方财富 API
BASE_URL = "https://push2his.eastmoney.com"


def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
        'Referer': 'https://quote.eastmoney.com/',
        'Origin': 'https://quote.eastmoney.com'
    }


def get_session():
    """创建禁用代理的requests会话"""
    session = requests.Session()
    session.trust_env = False  # 禁用环境变量代理
    # 禁用连接复用可能导致问题，保持默认
    return session


def get_stock_code(symbol):
    """转换为东方财富需要的格式"""
    symbol = symbol.strip().upper()

    # 指数
    if symbol.startswith('SH') or symbol == '000001':
        return f"1.{symbol.replace('SH', '')}"
    elif symbol.startswith('SZ') or symbol.startswith('399'):
        return f"0.{symbol.replace('SZ', '')}"
    # 创业板
    elif len(symbol) == 6 and symbol.startswith('3'):
        return f"0.{symbol}"
    # 科创板
    elif len(symbol) == 6 and symbol.startswith('688'):
        return f"1.{symbol}"
    # 普通A股
    elif len(symbol) == 6:
        if symbol.startswith('6'):
            return f"1.{symbol}"
        else:
            return f"0.{symbol}"
    return symbol


@stock_api.route('/api/stock/quote', methods=['POST'])
def get_quote():
    """获取股票实时报价"""
    data = request.json
    symbol = data.get('symbol', '').strip()

    if not symbol:
        return jsonify({'success': False, 'error': '请输入股票代码'})

    secid = get_stock_code(symbol)
    url = f"{BASE_URL}/api/qt/stock/get"
    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'secid': secid
    }

    full_url = ""
    try:
        full_url = f"{url}?{'&'.join([f'{k}={v}' for k,v in params.items()])}"
        logger.info(f"[Quote] URL: {full_url}")

        r = get_session().get(url, params=params, headers=get_headers(), timeout=10)
        data = r.json()

        if data.get('data') is None:
            return jsonify({'success': False, 'error': f'未找到股票 {symbol}'})

        d = data['data']

        def get_val(key, default: float = 0.0, scale: float = 1.0):
            """
            从返回数据中安全读取数值字段。
            - 如果为 '-' 或 None，则返回 default
            - 自动转为 float
            - 可通过 scale 进行缩放（例如东方财富价格通常放大100倍）
            """
            val = d.get(key, None)
            if val in ('-', None, ''):
                return default
            try:
                v = float(val)
            except (TypeError, ValueError):
                return default
            return v / scale

        result = {
            'symbol': symbol,
            'name': d.get('f58', symbol),
            # f43 为最新价，东方财富通常放大100倍，缩放回真实价格
            'price': get_val('f43', default=0.0, scale=100.0),
            'change': get_val('f4', default=0.0, scale=100.0),
            'change_pct': get_val('f3', default=0.0),  # 已是百分比
            'open': get_val('f17', default=0.0, scale=100.0),
            'high': get_val('f15', default=0.0, scale=100.0),
            'low': get_val('f16', default=0.0, scale=100.0),
            'close': get_val('f2', default=0.0, scale=100.0),
            'volume': get_val('f5', default=0.0),
            'amount': get_val('f6', default=0.0),
            'turnover': get_val('f8', default=0.0),
            'pe': get_val('f12', default=0.0),
            'pb': get_val('f13', default=0.0),
            'high_52w': get_val('f33', default=0.0, scale=100.0),
            'low_52w': get_val('f34', default=0.0, scale=100.0),
            'market_cap': get_val('f20', default=0.0),
            'float_cap': get_val('f21', default=0.0),
        }

        return jsonify({'success': True, 'data': result, 'debug_url': full_url})
    except Exception as e:
        # full_url 可能在请求前就抛异常，这里做保护
        return jsonify({'success': False, 'error': str(e), 'debug_url': full_url if 'full_url' in locals() else ''})


@stock_api.route('/api/stock/history', methods=['POST'])
def get_history():
    """获取股票历史K线"""
    data = request.json
    symbol = data.get('symbol', '002497').strip()
    period = data.get('period', 'daily')  # daily, weekly, monthly
    start = data.get('start', '')
    end = data.get('end', '')

    # 默认获取最近180天
    if not start:
        start_date = datetime.now() - timedelta(days=180)
        start = start_date.strftime('%Y%m%d')
    if not end:
        end = datetime.now().strftime('%Y%m%d')

    # 周期映射
    klt_map = {'daily': 101, 'weekly': 102, 'monthly': 103}
    klt = klt_map.get(period, 101)

    secid = get_stock_code(symbol)
    url = f"{BASE_URL}/api/qt/stock/kline/get"
    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': klt,
        'fqt': 1,  # 1:前复权, 0:不复权, 2:后复权
        'secid': secid,
        'beg': start,
        'end': end
    }

    full_url = ""
    try:
        full_url = f"{url}?{'&'.join([f'{k}={v}' for k,v in params.items()])}"
        logger.info(f"[History] URL: {full_url}")

        r = get_session().get(url, params=params, headers=get_headers(), timeout=10)
        data = r.json()

        if not data.get('data') or not data['data'].get('klines'):
            return jsonify({'success': False, 'error': f'未找到股票 {symbol} 的数据'})

        klines = data['data']['klines']
        records = []

        for line in klines:
            fields = line.split(',')
            record = {
                'date': fields[0],
                'open': float(fields[1]) if fields[1] != '-' else None,
                'close': float(fields[2]) if fields[2] != '-' else None,
                'high': float(fields[3]) if fields[3] != '-' else None,
                'low': float(fields[4]) if fields[4] != '-' else None,
                'volume': float(fields[5]) if fields[5] != '-' else None,
                'amount': float(fields[6]) if len(fields) > 6 and fields[6] != '-' else None,
                'change_pct': float(fields[8]) if len(fields) > 8 and fields[8] != '-' else None,
            }
            records.append(record)

        return jsonify({
            'success': True,
            'symbol': symbol,
            'name': data['data'].get('name', symbol),
            'period': period,
            'data': records,
            'debug_url': full_url
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'debug_url': full_url if 'full_url' in locals() else ''})


@stock_api.route('/api/stock/overview', methods=['POST'])
def get_overview():
    """获取股票基本信息"""
    data = request.json
    symbol = data.get('symbol', '').strip()

    secid = get_stock_code(symbol)
    url = f"{BASE_URL}/api/qt/stock/get"
    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'secid': secid
    }

    full_url = ""
    try:
        full_url = f"{url}?{'&'.join([f'{k}={v}' for k,v in params.items()])}"
        logger.info(f"[Info] URL: {full_url}")

        r = get_session().get(url, params=params, headers=get_headers(), timeout=10)
        data = r.json()

        if data.get('data') is None:
            return jsonify({'success': False, 'error': f'未找到股票 {symbol}'})

        d = data['data']
        result = {
            'symbol': symbol,
            'name': d.get('f58'),
            'industry': d.get('f84'),
            'area': d.get('f85'),
            'pe': d.get('f116'),
            'pe_ttm': d.get('f117'),
            'pb': d.get('f127'),
            'market_cap': d.get('f163'),
            'float_cap': d.get('f164'),
            'total_shares': d.get('f167'),
            'float_shares': d.get('f168'),
            'free_shares': d.get('f169'),
            'total_mv': d.get('f170'),
            'circ_mv': d.get('f171'),
        }

        return jsonify({'success': True, 'data': result, 'debug_url': full_url})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'debug_url': full_url if 'full_url' in locals() else ''})


# 股票名称映射
STOCK_NAMES = {
    '600519': '贵州茅台',
    '000001': '平安银行',
    '600036': '招商银行',
    '601318': '中国平安',
    '002497': '雅克科技',
    '000333': '美的集团',
    '002594': '比亚迪',
    '000858': '五粮液',
    '600900': '长江电力',
    '000001': '上证指数',
}

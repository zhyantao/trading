"""
股票数据API - 使用东方财富直接API
"""

from flask import Blueprint, jsonify, request
import requests
import json
from datetime import datetime, timedelta
import pandas as pd

stock_api = Blueprint('stock', __name__)

# 东方财富 API
BASE_URL = "https://push2his.eastmoney.com"


def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    }


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
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'secid': secid,
        '_': int(datetime.now().timestamp() * 1000)
    }

    try:
        r = requests.get(url, params=params, headers=get_headers(), timeout=10)
        data = r.json()

        if data.get('data') is None:
            return jsonify({'success': False, 'error': f'未找到股票 {symbol}'})

        d = data['data']
        result = {
            'symbol': symbol,
            'name': d.get('name', symbol),
            'price': d.get('f2'),
            'change': d.get('f4'),
            'change_pct': d.get('f3'),
            'open': d.get('f17'),
            'high': d.get('f15'),
            'low': d.get('f16'),
            'close': d.get('f2'),
            'volume': d.get('f5'),
            'amount': d.get('f6'),
            'turnover': d.get('f8'),
            'pe': d.get('f12'),
            'pb': d.get('f13'),
            'high_52w': d.get('f33'),
            'low_52w': d.get('f34'),
            'market_cap': d.get('f20'),
            'float_cap': d.get('f21'),
        }

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


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
        'end': end,
        '_': int(datetime.now().timestamp() * 1000)
    }

    try:
        r = requests.get(url, params=params, headers=get_headers(), timeout=10)
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
            'period': period,
            'data': records
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@stock_api.route('/api/stock/overview', methods=['POST'])
def get_overview():
    """获取股票基本信息"""
    data = request.json
    symbol = data.get('symbol', '').strip()

    secid = get_stock_code(symbol)
    url = f"{BASE_URL}/api/qt/stock/get"
    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'fields1': 'f57,f58,f59,f60,f84,f85,f116,f117,f127,f128,f163,f164,f167,f168,f169,f170,f171,f172,f173,f174,f175,f176,f177,f178,f179,f180,f181,f182,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193,f194,f195,f196,f197,f198,f199,f200,f201,f202,f203,f204,f205,f206,f207,f208,f209,f210,f211,f212,f213,f214,f215,f216,f217,f218,f219,f220,f221,f222,f223,f224,f225,f226,f227,f228,f229,f230,f231,f232,f233,f234,f235,f236,f237,f238,f239,f240,f241,f242,f243,f244,f245,f246,f247,f248,f249,f250,f251,f252,f253,f254,f255,f256,f257,f258,f259,f260,f261,f262,f263,f264,f265,f266,f267,f268,f269,f270,f271,f272,f273,f274,f275,f276,f277,f278,f279,f280,f281,f282,f283,f284,f285,f286,f287,f288,f289,f290,f291,f292,f293,f294,f295,f296,f297,f298,f299,f300',
        'fields2': '',
        'secid': secid,
        '_': int(datetime.now().timestamp() * 1000)
    }

    try:
        r = requests.get(url, params=params, headers=get_headers(), timeout=10)
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

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


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

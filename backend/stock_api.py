"""
股票数据API - 使用东方财富直接API
"""

from flask import Blueprint, jsonify, request
import requests
import json
import logging
import random
import time
from datetime import datetime, timedelta
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

stock_api = Blueprint('stock', __name__)

# 东方财富 API
BASE_URL = "https://push2his.eastmoney.com"

# User-Agent 池，随机选择
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

def get_headers():
    """生成完整的浏览器请求头"""
    ua = random.choice(USER_AGENTS)
    return {
        'User-Agent': ua,
        'Accept': '*/*',  # 东方财富API通常返回JSON，但用*/*更安全
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Referer': 'https://quote.eastmoney.com/',
        'Origin': 'https://quote.eastmoney.com',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Sec-Fetch-Dest': 'script',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'same-site',
    }


def get_session():
    """创建配置完善的requests会话"""
    session = requests.Session()
    session.trust_env = False  # 禁用环境变量代理

    # 配置重试策略：连接错误时重试3次
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,  # 间隔 0.5, 1, 2 秒
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 先访问主站获取Cookie（模拟真实用户行为）
    try:
        # 预热请求：先访问东方财富主站建立会话
        warmup_resp = session.get(
            'https://quote.eastmoney.com/concept/sh600519.html',
            headers=get_headers(),
            timeout=5
        )
        logger.info(f"Warmup session cookies: {session.cookies.get_dict()}")
        time.sleep(random.uniform(0.5, 1.5))  # 随机延迟
    except Exception as e:
        logger.warning(f"Warmup request failed (non-critical): {e}")

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
    # 北交所
    elif len(symbol) == 6 and symbol.startswith('8'):
        return f"0.{symbol}"
    # 普通A股
    elif len(symbol) == 6:
        if symbol.startswith('6'):
            return f"1.{symbol}"
        else:
            return f"0.{symbol}"
    return symbol


def safe_request(url, params, max_retries=3):
    """带重试和随机延迟的安全请求"""
    for attempt in range(max_retries):
        try:
            # 随机延迟，避免触发频率限制 [^1^][^4^]
            if attempt > 0:
                sleep_time = random.uniform(2, 5) * attempt
                logger.info(f"Retry {attempt}, sleeping {sleep_time:.2f}s...")
                time.sleep(sleep_time)

            session = get_session()
            headers = get_headers()

            # 使用params参数让requests自动处理URL编码
            response = session.get(
                url,
                params=params,
                headers=headers,
                timeout=15,
                allow_redirects=True
            )

            # 检查响应
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"HTTP {response.status_code}: {response.text[:200]}")

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise
        except Exception as e:
            logger.error(f"Request error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise

    return None


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

    try:
        result_data = safe_request(url, params)

        if not result_data or result_data.get('data') is None:
            return jsonify({'success': False, 'error': f'未找到股票 {symbol}'})

        d = result_data['data']

        def get_val(key, default: float = 0.0, scale: float = 1.0):
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
            'price': get_val('f43', default=0.0, scale=100.0),
            'change': get_val('f4', default=0.0, scale=100.0),
            'change_pct': get_val('f3', default=0.0),
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

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        logger.exception("Quote request failed")
        return jsonify({'success': False, 'error': str(e)})


@stock_api.route('/api/stock/history', methods=['POST'])
def get_history():
    """获取股票历史K线"""
    data = request.json
    symbol = data.get('symbol', '002497').strip()
    period = data.get('period', 'daily')
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
        'fqt': 1,
        'secid': secid,
        'beg': start,
        'end': end
    }

    try:
        result_data = safe_request(url, params)

        if not result_data or not result_data.get('data') or not result_data['data'].get('klines'):
            return jsonify({'success': False, 'error': f'未找到股票 {symbol} 的数据'})

        klines = result_data['data']['klines']
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
            'name': result_data['data'].get('name', symbol),
            'period': period,
            'data': records
        })

    except Exception as e:
        logger.exception("History request failed")
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
        'secid': secid
    }

    try:
        result_data = safe_request(url, params)

        if not result_data or result_data.get('data') is None:
            return jsonify({'success': False, 'error': f'未找到股票 {symbol}'})

        d = result_data['data']
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
        logger.exception("Overview request failed")
        return jsonify({'success': False, 'error': str(e)})

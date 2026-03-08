"""
量化交易系统 - 技术指标分析器
基于趋势投资的量化分析工具
使用东方财富API获取数据
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import requests


class TechnicalAnalyzer:
    """技术指标分析器"""
    
    def __init__(self, params: Optional[Dict] = None):
        # 默认参数
        self.params = params or {
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
            'trend_confirm_days': 3,
            'stop_loss_pct': 5,
            'take_profit_pct': 15,
        }
        
    def get_stock_data(self, symbol: str, days: int = 250) -> pd.DataFrame:
        """获取股票历史数据 - 从本地API获取"""
        try:
            # 从本地API获取数据
            start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y%m%d')
            end_date = datetime.now().strftime('%Y%m%d')
            
            url = 'http://localhost:5001/api/stock/history'
            response = requests.post(url, json={
                'symbol': symbol,
                'start': start_date,
                'end': end_date
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    df = pd.DataFrame(data['data'])
                    df = df.rename(columns={
                        'date': 'Date',
                        'open': 'Open',
                        'high': 'High',
                        'low': 'Low',
                        'close': 'Close',
                        'volume': 'Volume'
                    })
                    df['Date'] = pd.to_datetime(df['Date'])
                    df = df.set_index('Date').sort_index()
                    return df
            
            return pd.DataFrame()
        except Exception as e:
            print(f"获取数据失败: {e}")
            return pd.DataFrame()
    
    def calculate_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算移动平均线"""
        if df.empty or 'Close' not in df.columns:
            return df
            
        for period in [5, 10, 20, 60]:
            df[f'MA{period}'] = df['Close'].rolling(window=period).mean()
        return df
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算RSI"""
        if df.empty or 'Close' not in df.columns:
            return df
            
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        return df
    
    def calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算MACD"""
        if df.empty or 'Close' not in df.columns:
            return df
            
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Histogram'] = df['MACD'] - df['Signal']
        return df
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
        """计算布林带"""
        if df.empty or 'Close' not in df.columns:
            return df
            
        df['BB_Middle'] = df['Close'].rolling(window=period).mean()
        df['BB_Std'] = df['Close'].rolling(window=period).std()
        df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * std_dev)
        df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * std_dev)
        return df
    
    def calculate_volume_ma(self, df: pd.DataFrame, period: int = 5) -> pd.DataFrame:
        """计算成交量均线"""
        if df.empty or 'Volume' not in df.columns:
            return df
        df['Volume_MA'] = df['Volume'].rolling(window=period).mean()
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算所有技术指标"""
        if df.empty:
            return df
        df = self.calculate_ma(df)
        df = self.calculate_rsi(df, self.params.get('rsi_period', 14))
        df = self.calculate_macd(df)
        df = self.calculate_bollinger_bands(df)
        df = self.calculate_volume_ma(df)
        return df
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """生成交易信号"""
        if df.empty or len(df) < 30:
            return {'action': 'hold', 'reason': '数据不足'}
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        scores = []
        reasons = []
        
        # MA 趋势判断
        if latest.get('MA5', 0) > latest.get('MA20', 0):
            scores.append(1)
            reasons.append('短期均线上穿长期均线')
        elif latest.get('MA5', 0) < latest.get('MA20', 0):
            scores.append(-1)
            reasons.append('短期均线下穿长期均线')
        
        # RSI 判断
        rsi = latest.get('RSI', 50)
        if rsi < self.params.get('rsi_oversold', 30):
            scores.append(1)
            reasons.append(f'RSI超卖({rsi:.1f})')
        elif rsi > self.params.get('rsi_overbought', 70):
            scores.append(-1)
            reasons.append(f'RSI超买({rsi:.1f})')
        
        # MACD 判断
        if latest.get('MACD', 0) > latest.get('Signal', 0) and prev.get('MACD', 0) <= prev.get('Signal', 0):
            scores.append(1)
            reasons.append('MACD金叉')
        elif latest.get('MACD', 0) < latest.get('Signal', 0) and prev.get('MACD', 0) >= prev.get('Signal', 0):
            scores.append(-1)
            reasons.append('MACD死叉')
        
        # 布林带判断
        if latest.get('Close', 0) < latest.get('BB_Lower', 0):
            scores.append(1)
            reasons.append('价格触及布林下轨')
        elif latest.get('Close', 0) > latest.get('BB_Upper', 0):
            scores.append(-1)
            reasons.append('价格触及布林上轨')
        
        total_score = sum(scores)
        
        if total_score >= self.params.get('strong_buy_score', 3):
            action = 'strong_buy'
        elif total_score >= self.params.get('buy_score_threshold', 1):
            action = 'buy'
        elif total_score <= -self.params.get('sell_score_threshold', -1):
            action = 'sell'
        else:
            action = 'hold'
        
        return {
            'action': action,
            'score': total_score,
            'reasons': reasons
        }

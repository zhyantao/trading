"""
量化交易系统 - 技术指标分析器
基于趋势投资的量化分析工具
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json


class TechnicalAnalyzer:
    """技术指标分析器"""
    
    def __init__(self, params: Optional[Dict] = None):
        # 默认参数
        self.params = params or {
            # 移动平均线参数
            'ma_short': 5,      # 短期均线周期
            'ma_medium': 10,     # 中期均线周期  
            'ma_long': 20,      # 长期均线周期
            'ma_long_term': 60, # 长期均线周期
            
            # RSI 参数
            'rsi_period': 14,    # RSI 周期
            'rsi_oversold': 30, # RSI 超卖阈值
            'rsi_overbought': 70, # RSI 超买阈值
            
            # MACD 参数
            'macd_fast': 12,    # MACD 快线周期
            'macd_slow': 26,    # MACD 慢线周期
            'macd_signal': 9,    # MACD 信号线周期
            
            # 布林带参数
            'bb_period': 20,     # 布林带周期
            'bb_std': 2,        # 布林带标准差倍数
            
            # 成交量参数
            'volume_ma_period': 5,  # 成交量均线周期
            'volume_ratio_threshold': 1.5,  # 成交量放大倍数阈值
            
            # 趋势确认参数
            'trend_confirm_days': 3,  # 趋势确认天数
            
            # 止损止盈参数
            'stop_loss_pct': 5,   # 止损百分比
            'take_profit_pct': 15, # 止盈百分比
        }
        
    def get_stock_data(self, symbol: str, days: int = 250) -> pd.DataFrame:
        """获取股票历史数据"""
        # 转换为 akshare 需要的格式
        symbol_map = {
            '000001': '000001',  # 平安银行
            '399001': '399001',  # 深证成指
            '399006': '399006',  # 创业板指
            'sh000001': 'sh000001', # 上证指数
        }
        
        # 尝试获取数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y%m%d')
        
        try:
            # 尝试获取 A 股数据
            if symbol.isdigit():
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust=""
                )
            else:
                # ETF 或其他
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust=""
                )
            
            # 数据清洗
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'change_pct',
                '涨跌额': 'change',
                '换手率': 'turnover'
            })
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            print(f"获取数据失败: {e}")
            return pd.DataFrame()
    
    def calculate_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算移动平均线"""
        for period in [self.params['ma_short'], self.params['ma_medium'], 
                       self.params['ma_long'], self.params['ma_long_term']]:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        return df
    
    def calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算 RSI 指标"""
        period = self.params['rsi_period']
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    def calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算 MACD 指标"""
        fast = self.params['macd_fast']
        slow = self.params['macd_slow']
        signal = self.params['macd_signal']
        
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        return df
    
    def calculate_bollinger_bands(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算布林带"""
        period = self.params['bb_period']
        std = self.params['bb_std']
        
        df['bb_middle'] = df['close'].rolling(window=period).mean()
        df['bb_std'] = df['close'].rolling(window=period).std()
        df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * std)
        df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * std)
        
        return df
    
    def calculate_volume_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算成交量均线"""
        period = self.params['volume_ma_period']
        df['volume_ma'] = df['volume'].rolling(window=period).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        return df
    
    def calculate_volatility(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """计算波动率"""
        df['volatility'] = df['close'].pct_change().rolling(window=period).std() * np.sqrt(252) * 100
        return df
    
    def calculate_all(self, symbol: str) -> pd.DataFrame:
        """计算所有指标"""
        df = self.get_stock_data(symbol)
        
        if df.empty:
            return df
            
        df = self.calculate_ma(df)
        df = self.calculate_rsi(df)
        df = self.calculate_macd(df)
        df = self.calculate_bollinger_bands(df)
        df = self.calculate_volume_ma(df)
        df = self.calculate_volatility(df)
        
        return df
    
    def get_latest_signals(self, df: pd.DataFrame) -> Dict:
        """获取最新交易信号"""
        if df.empty or len(df) < 30:
            return {}
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        signals = {
            'date': str(latest['date']),
            'close': float(latest['close']),
            'change_pct': float(latest.get('change_pct', 0)),
            
            # 均线信号
            'ma_signals': self._get_ma_signals(df),
            
            # RSI 信号
            'rsi': float(latest['rsi']),
            'rsi_signal': self._get_rsi_signal(latest['rsi']),
            
            # MACD 信号
            'macd_signal': self._get_macd_signal(df),
            
            # 布林带信号
            'bb_signal': self._get_bb_signal(latest),
            
            # 成交量信号
            'volume_signal': self._get_volume_signal(latest),
            
            # 综合评分
            'overall_score': 0,
            'recommendation': 'hold',
            'reasons': []
        }
        
        # 计算综合评分
        score = 0
        reasons = []
        
        # 均线趋势评分
        if signals['ma_signals']['trend'] == '上涨':
            score += 2
            reasons.append('均线呈上涨趋势')
        elif signals['ma_signals']['trend'] == '下跌':
            score -= 2
            reasons.append('均线呈下跌趋势')
        
        # RSI 评分
        if latest['rsi'] < self.params['rsi_oversold']:
            score += 2
            reasons.append(f"RSI 超卖({latest['rsi']:.1f}),可能反弹")
        elif latest['rsi'] > self.params['rsi_overbought']:
            score -= 2
            reasons.append(f"RSI 超买({latest['rsi']:.1f}),注意风险")
        
        # MACD 评分
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            score += 2
            reasons.append('MACD 金叉,买入信号')
        elif latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            score -= 2
            reasons.append('MACD 死叉,卖出信号')
        
        # 成交量评分
        if latest.get('volume_ratio', 1) > self.params['volume_ratio_threshold']:
            score += 1
            reasons.append('成交量放大')
        
        # 布林带评分
        if signals['bb_signal'] == '触及下轨':
            score += 1
            reasons.append('触及布林下轨,可能反弹')
        elif signals['bb_signal'] == '触及上轨':
            score -= 1
            reasons.append('触及布林上轨,注意风险')
        
        signals['overall_score'] = score
        signals['reasons'] = reasons
        
        # 给出建议
        if score >= 3:
            signals['recommendation'] = 'strong_buy'
        elif score >= 1:
            signals['recommendation'] = 'buy'
        elif score <= -3:
            signals['recommendation'] = 'strong_sell'
        elif score <= -1:
            signals['recommendation'] = 'sell'
        else:
            signals['recommendation'] = 'hold'
            
        return signals
    
    def _get_ma_signals(self, df: pd.DataFrame) -> Dict:
        """获取均线信号"""
        if len(df) < 5:
            return {'trend': '震荡', 'golden_cross': False, 'death_cross': False}
        
        latest = df.iloc[-1]
        
        ma5 = latest.get(f"ma{self.params['ma_short']}", 0)
        ma10 = latest.get(f"ma{self.params['ma_medium']}", 0)
        ma20 = latest.get(f"ma{self.params['ma_long']}", 0)
        
        # 判断趋势
        if ma5 > ma10 > ma20:
            trend = '上涨'
        elif ma5 < ma10 < ma20:
            trend = '下跌'
        else:
            trend = '震荡'
        
        # 金叉/死叉
        prev = df.iloc[-2]
        prev_ma5 = prev.get(f"ma{self.params['ma_short']}", 0)
        prev_ma10 = prev.get(f"ma{self.params['ma_medium']}", 0)
        
        golden_cross = (prev_ma5 <= prev_ma10) and (ma5 > ma10)
        death_cross = (prev_ma5 >= prev_ma10) and (ma5 < ma10)
        
        return {
            'trend': trend,
            'golden_cross': golden_cross,
            'death_cross': death_cross
        }
    
    def _get_rsi_signal(self, rsi: float) -> str:
        """获取 RSI 信号"""
        if rsi < self.params['rsi_oversold']:
            return '超卖'
        elif rsi > self.params['rsi_overbought']:
            return '超买'
        elif rsi > 50:
            return '偏强'
        else:
            return '偏弱'
    
    def _get_macd_signal(self, df: pd.DataFrame) -> str:
        """获取 MACD 信号"""
        if len(df) < 2:
            return '震荡'
        
        latest = df.iloc[-1]
        
        if latest['macd'] > latest['macd_signal']:
            if latest['macd_hist'] > 0:
                return '强势上涨'
            return '开始上涨'
        else:
            if latest['macd_hist'] < 0:
                return '强势下跌'
            return '开始下跌'
    
    def _get_bb_signal(self, latest: pd.Series) -> str:
        """获取布林带信号"""
        close = latest['close']
        
        if close <= latest['bb_lower']:
            return '触及下轨'
        elif close >= latest['bb_upper']:
            return '触及上轨'
        elif close > latest['bb_middle']:
            return '中轨上方'
        else:
            return '中轨下方'
    
    def _get_volume_signal(self, latest: pd.Series) -> str:
        """获取成交量信号"""
        vol_ratio = latest.get('volume_ratio', 1)
        
        if vol_ratio > self.params['volume_ratio_threshold'] * 2:
            return '成交量激增'
        elif vol_ratio > self.params['volume_ratio_threshold']:
            return '成交量放大'
        elif vol_ratio < 0.5:
            return '成交量萎缩'
        else:
            return '成交量正常'


if __name__ == '__main__':
    # 测试
    analyzer = TechnicalAnalyzer()
    
    # 测试获取上证指数
    print("=== 上证指数分析 ===")
    df = analyzer.get_stock_data('sh000001')
    print(f"获取数据 {len(df)} 条")
    
    if not df.empty:
        df = analyzer.calculate_all('sh000001')
        signals = analyzer.get_latest_signals(df)
        print(json.dumps(signals, ensure_ascii=False, indent=2))

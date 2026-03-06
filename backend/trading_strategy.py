"""
交易信号和策略模块
"""

from datetime import datetime
from typing import Dict, List, Optional
import json
import os


class TradingSignal:
    """交易信号"""
    
    def __init__(self):
        self.recommendation = 'hold'  # strong_buy, buy, hold, sell, strong_sell
        self.score = 0
        self.reasons = []
        self.timestamp = None
        
    def from_analysis(self, analysis: Dict):
        """从分析结果创建交易信号"""
        self.recommendation = analysis.get('recommendation', 'hold')
        self.score = analysis.get('overall_score', 0)
        self.reasons = analysis.get('reasons', [])
        self.timestamp = datetime.now()
        
    def to_dict(self) -> Dict:
        return {
            'recommendation': self.recommendation,
            'score': self.score,
            'reasons': self.reasons,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None
        }


class TradingLogger:
    """交易日志记录器"""
    
    def __init__(self, log_file: str = 'data/trading_log.json'):
        self.log_file = log_file
        self.trades: List[Dict] = []
        self._load()
        
    def _load(self):
        """加载历史交易记录"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    self.trades = json.load(f)
            except:
                self.trades = []
                
    def _save(self):
        """保存交易记录"""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.trades, f, ensure_ascii=False, indent=2)
    
    def add_trade(self, trade: Dict):
        """添加交易记录"""
        trade['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.trades.append(trade)
        self._save()
        
    def get_trades(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取交易记录"""
        trades = self.trades
        if symbol:
            trades = [t for t in trades if t.get('symbol') == symbol]
        return trades[-limit:]
    
    def get_statistics(self, symbol: Optional[str] = None) -> Dict:
        """获取交易统计"""
        trades = self.get_trades(symbol, limit=1000)
        
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_profit': 0,
                'avg_profit': 0
            }
        
        winning = [t for t in trades if t.get('profit', 0) > 0]
        losing = [t for t in trades if t.get('profit', 0) < 0]
        
        total_profit = sum(t.get('profit', 0) for t in trades)
        
        return {
            'total_trades': len(trades),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': len(winning) / len(trades) * 100 if trades else 0,
            'total_profit': total_profit,
            'avg_profit': total_profit / len(trades) if trades else 0
        }


class TradingStrategy:
    """交易策略"""
    
    def __init__(self, params: Optional[Dict] = None):
        # 默认策略参数
        self.params = params or {
            # 仓位管理
            'max_position': 100,      # 最大持仓比例 (%)
            'single_position': 30,     # 单只股票最大持仓 (%)
            
            # 买入条件
            'buy_score_threshold': 1,  # 买入评分阈值
            'strong_buy_score': 3,     # 强买评分
            
            # 卖出条件
            'sell_score_threshold': -1, # 卖出评分阈值
            'stop_loss': 5,             # 止损比例 (%)
            'take_profit': 15,         # 止盈比例 (%)
            
            # 趋势过滤
            'require_uptrend': True,    # 只在上涨趋势买入
            'avoid_downtrend': True,   # 下跌趋势不买入
        }
        
    def should_buy(self, signal: TradingSignal, current_position: float = 0) -> bool:
        """判断是否应该买入"""
        if signal.recommendation in ['strong_buy', 'buy']:
            # 检查评分
            if signal.score >= self.params['strong_buy_score']:
                return True
            elif signal.score >= self.params['buy_score_threshold']:
                # 检查持仓
                if current_position < self.params['max_position']:
                    return True
        return False
    
    def should_sell(self, signal: TradingSignal, profit_pct: float = 0) -> bool:
        """判断是否应该卖出"""
        # 止损
        if profit_pct <= -self.params['stop_loss']:
            return True
            
        # 止盈
        if profit_pct >= self.params['take_profit']:
            return True
            
        # 卖出信号
        if signal.recommendation in ['strong_sell', 'sell']:
            return True
            
        return False
    
    def calculate_position_size(self, signal: TradingSignal, total_capital: float) -> float:
        """计算建仓金额"""
        if signal.score >= self.params['strong_buy_score']:
            # 强买信号，使用较大仓位
            return total_capital * (self.params['single_position'] / 100)
        else:
            # 普通买入信号，使用较小仓位
            return total_capital * (self.params['single_position'] / 100) * 0.5
            
    def generate_trade_reason(self, signal: TradingSignal, action: str) -> str:
        """生成交易原因说明"""
        reasons = signal.reasons.copy()
        
        if action == 'buy':
            if signal.recommendation == 'strong_buy':
                reasons.insert(0, '【强买信号】多个指标同时显示买入机会')
            else:
                reasons.insert(0, '【买入信号】技术指标显示买入机会')
        elif action == 'sell':
            if signal.score <= -self.params['stop_loss']:
                reasons.insert(0, '【止损】触发止损条件')
            elif signal.score >= self.params['take_profit']:
                reasons.insert(0, '【止盈】达到预期收益')
            else:
                reasons.insert(0, '【卖出信号】技术指标显示卖出')
                
        return '; '.join(reasons) if reasons else '系统自动交易'


if __name__ == '__main__':
    # 测试
    logger = TradingLogger()
    print("交易日志测试:")
    print(f"当前记录: {len(logger.trades)} 条")
    print(f"统计: {logger.get_statistics()}")

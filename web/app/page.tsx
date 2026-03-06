'use client';

import { useState, useEffect, useCallback } from 'react';

interface Trade {
  timestamp: string;
  symbol: string;
  action: string;
  price: number;
  reason: string;
  reasons?: string[];
}

interface Stats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_profit: number;
  avg_profit: number;
}

interface Symbol {
  code: string;
  name: string;
  type: string;
}

const DEFAULT_PARAMS = {
  ma_short: 5,
  ma_medium: 10,
  ma_long: 20,
  rsi_period: 14,
  rsi_oversold: 30,
  rsi_overbought: 70,
  buy_score_threshold: 1,
  strong_buy_score: 3,
  sell_score_threshold: -1,
  stop_loss_pct: 5,
  take_profit_pct: 15,
};

const DEFAULT_SYMBOLS = [
  { code: 'sh000001', name: '上证指数', type: 'index' },
  { code: '399001', name: '深证成指', type: 'index' },
  { code: '399006', name: '创业板指', type: 'index' },
];

export default function Home() {
  // 页面状态: analyze, simulation, stock
  const [page, setPage] = useState<'analyze' | 'simulation' | 'stock'>('analyze');

  // 股票查询相关状态
  const [stockSymbol, setStockSymbol] = useState('');
  const [stockSource, setStockSource] = useState('yfinance');
  const [stockLoading, setStockLoading] = useState(false);
  const [stockLogs, setStockLogs] = useState<LogEntry[]>([]);
  const [stockInfo, setStockInfo] = useState<StockInfo | null>(null);
  const [stockHistory, setStockHistory] = useState<HistoryData[]>([]);
  const [stockDetail, setStockDetail] = useState<any>(null);

  interface LogEntry {
    time: string;
    message: string;
    type: 'info' | 'success' | 'error' | 'loading';
  }

  interface StockInfo {
    symbol: string;
    name: string;
    price: number;
    change: number;
    change_pct: number;
  }

  interface HistoryData {
    Date: string;
    Open: number;
    High: number;
    Low: number;
    Close: number;
    Volume: number;
    涨跌幅: number;
    MA5: number;
    MA10: number;
    RSI: number;
  }

  const addStockLog = (message: string, type: LogEntry['type'] = 'info') => {
    const time = new Date().toLocaleTimeString();
    setStockLogs(prev => [...prev, { time, message, type }]);
  };

  const clearStockLogs = () => setStockLogs([]);

  const handleStockSearch = async () => {
    if (!stockSymbol) {
      addStockLog('请输入股票代码', 'error');
      return;
    }
    
    setStockLoading(true);
    clearStockLogs();
    addStockLog(`开始查询股票: ${stockSymbol} (数据源: ${stockSource})`, 'info');
    setStockInfo(null);
    setStockHistory([]);
    setStockDetail(null);

    try {
      addStockLog('正在获取实时报价...', 'loading');
      const quoteRes = await fetch('http://localhost:5001/api/stock/quote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: stockSymbol, source: stockSource }),
      });
      const quoteData = await quoteRes.json();
      
      if (quoteData.success) {
        setStockInfo(quoteData.data);
        addStockLog(`✓ 实时报价获取成功: $${quoteData.data.price?.toFixed(2)}`, 'success');
      } else {
        addStockLog(`✗ 实时报价失败: ${quoteData.error}`, 'error');
        if (quoteData.suggestion) {
          addStockLog(`💡 建议: ${quoteData.suggestion}`, 'info');
        }
      }

      addStockLog('正在获取历史行情数据...', 'loading');
      const historyRes = await fetch('http://localhost:5001/api/stock/history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: stockSymbol, period: '1mo', source: stockSource }),
      });
      const historyData = await historyRes.json();
      
      if (historyData.success) {
        setStockHistory(historyData.data);
        addStockLog(`✓ 历史数据获取成功: ${historyData.data.length} 条记录`, 'success');
      } else {
        addStockLog(`✗ 历史数据失败: ${historyData.error}`, 'error');
        if (historyData.suggestion) {
          addStockLog(`💡 建议: ${historyData.suggestion}`, 'info');
        }
      }

      addStockLog('正在获取详细信息...', 'loading');
      const infoRes = await fetch('http://localhost:5001/api/stock/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: stockSymbol, source: stockSource }),
      });
      const infoData = await infoRes.json();
      
      if (infoData.success) {
        setStockDetail(infoData.data);
        addStockLog(`✓ 详细信息获取成功`, 'success');
      } else {
        addStockLog(`✗ 详细信息失败: ${infoData.error}`, 'error');
        if (infoData.suggestion) {
          addStockLog(`💡 建议: ${infoData.suggestion}`, 'info');
        }
      }

      addStockLog('查询完成', 'info');
    } catch (e: any) {
      addStockLog(`✗ 查询异常: ${e.message || e}`, 'error');
    } finally {
      setStockLoading(false);
    }
  };

  const formatNumber = (num: number) => {
    if (!num && num !== 0) return '-';
    if (num >= 100000000) return (num / 100000000).toFixed(2) + '亿';
    if (num >= 10000) return (num / 10000).toFixed(2) + '万';
    return num.toFixed(2);
  };
  const [symbols, setSymbols] = useState<Symbol[]>(DEFAULT_SYMBOLS);
  const [selectedSymbol, setSelectedSymbol] = useState('sh000001');
  const [signal, setSignal] = useState<any>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<Stats>({ total_trades: 0, winning_trades: 0, losing_trades: 0, win_rate: 0, total_profit: 0, avg_profit: 0 });
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [loading, setLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [newSymbol, setNewSymbol] = useState({ code: '', name: '' });

  // 模拟交易参数
  const [simCapital, setSimCapital] = useState(1000000);
  const [simPosition, setSimPosition] = useState<any>(null);
  const [simTrades, setSimTrades] = useState<any[]>([]);

  useEffect(() => {
    fetch('http://localhost:5001/api/symbols')
      .then(res => res.json())
      .then(data => { if (data.success) setSymbols(data.data); });
    fetch('http://localhost:5001/api/params')
      .then(res => res.json())
      .then(data => setParams(data));
    fetch('http://localhost:5001/api/trades')
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setTrades(data.data.trades);
          setStats(data.data.statistics);
        }
      });
  }, []);

  const handleAnalyze = useCallback(() => {
    setLoading(true);
    fetch('http://localhost:5001/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: selectedSymbol }),
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setSignal(data.data.signals);
          setParams(data.data.params);
        }
      })
      .finally(() => setLoading(false));
  }, [selectedSymbol]);

  const handleSaveParams = () => {
    fetch('http://localhost:5001/api/params', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }).then(() => {
      setShowSettings(false);
      handleAnalyze();
    });
  };

  const handleAddTrade = (action: string) => {
    if (!signal) return;
    fetch('http://localhost:5001/api/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: selectedSymbol,
        action,
        price: signal.close,
        score: signal.overall_score,
        reasons: signal.reasons,
      }),
    }).then(() => {
      fetch('http://localhost:5001/api/trades')
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setTrades(data.data.trades);
            setStats(data.data.statistics);
          }
        });
    });
  };

  // 添加标的
  const addSymbol = () => {
    if (newSymbol.code && newSymbol.name) {
      setSymbols([...symbols, { ...newSymbol, type: 'stock' }]);
      setNewSymbol({ code: '', name: '' });
    }
  };

  // 删除标的
  const removeSymbol = (code: string) => {
    setSymbols(symbols.filter(s => s.code !== code));
  };

  const getRecColor = (rec: string) => {
    if (rec?.includes('strong_buy') || rec?.includes('buy')) return '#16a34a';
    if (rec?.includes('sell')) return '#dc2626';
    return '#6b7280';
  };

  const getRecText = (rec: string) => {
    if (rec === 'strong_buy') return '强烈买入';
    if (rec === 'buy') return '买入';
    if (rec === 'strong_sell') return '强烈卖出';
    if (rec === 'sell') return '卖出';
    return '持有';
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb' }}>
      {/* 导航 */}
      <nav style={{ backgroundColor: 'white', borderBottom: '1px solid #e5e7eb', padding: '0 16px' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', gap: '24px' }}>
          <button
            onClick={() => setPage('analyze')}
            style={{ padding: '16px 0', border: 'none', background: 'none', cursor: 'pointer', borderBottom: page === 'analyze' ? '2px solid #2563eb' : '2px solid transparent', color: page === 'analyze' ? '#2563eb' : '#6b7280', fontWeight: 500 }}
          >
            📊 技术分析
          </button>
          <button
            onClick={() => setPage('stock')}
            style={{ padding: '16px 0', border: 'none', background: 'none', cursor: 'pointer', borderBottom: page === 'stock' ? '2px solid #2563eb' : '2px solid transparent', color: page === 'stock' ? '#2563eb' : '#6b7280', fontWeight: 500 }}
          >
            📈 数据查询
          </button>
          <button
            onClick={() => setPage('simulation')}
            style={{ padding: '16px 0', border: 'none', background: 'none', cursor: 'pointer', borderBottom: page === 'simulation' ? '2px solid #2563eb' : '2px solid transparent', color: page === 'simulation' ? '#2563eb' : '#6b7280', fontWeight: 500 }}
          >
            🎮 模拟交易
          </button>
        </div>
      </nav>

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px 16px' }}>
        {/* 技术分析页面 */}
        {page === 'analyze' && (
          <>
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '16px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <label style={{ fontSize: '14px', fontWeight: 500 }}>选择标的:</label>
                  <select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)} style={{ border: '1px solid #d1d5db', borderRadius: '6px', padding: '8px 12px' }}>
                    {symbols.map((s) => (<option key={s.code} value={s.code}>{s.name} ({s.code})</option>))}
                  </select>
                </div>
                <button onClick={handleAnalyze} disabled={loading} style={{ padding: '8px 24px', backgroundColor: '#2563eb', color: 'white', borderRadius: '6px', border: 'none', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.5 : 1 }}>
                  {loading ? '分析中...' : '🔍 分析'}
                </button>
                <button onClick={() => setShowSettings(!showSettings)} style={{ padding: '8px 16px', backgroundColor: '#e5e7eb', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>⚙️ 参数设置</button>
              </div>
            </div>

            {showSettings && (
              <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>参数设置</h2>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '24px' }}>
                  <div>
                    <h3 style={{ fontWeight: 500, marginBottom: '8px' }}>均线参数</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <label style={{ fontSize: '14px' }}>短期均线: {params.ma_short}</label>
                      <input type="range" min="3" max="20" value={params.ma_short} onChange={(e) => setParams({...params, ma_short: parseInt(e.target.value)})} style={{ width: '100%' }} />
                      <label style={{ fontSize: '14px' }}>长期均线: {params.ma_long}</label>
                      <input type="range" min="10" max="60" value={params.ma_long} onChange={(e) => setParams({...params, ma_long: parseInt(e.target.value)})} style={{ width: '100%' }} />
                    </div>
                  </div>
                  <div>
                    <h3 style={{ fontWeight: 500, marginBottom: '8px' }}>RSI 参数</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <label style={{ fontSize: '14px' }}>超卖: {params.rsi_oversold}</label>
                      <input type="range" min="10" max="40" value={params.rsi_oversold} onChange={(e) => setParams({...params, rsi_oversold: parseInt(e.target.value)})} style={{ width: '100%' }} />
                      <label style={{ fontSize: '14px' }}>超买: {params.rsi_overbought}</label>
                      <input type="range" min="60" max="90" value={params.rsi_overbought} onChange={(e) => setParams({...params, rsi_overbought: parseInt(e.target.value)})} style={{ width: '100%' }} />
                    </div>
                  </div>
                </div>
                <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
                  <button onClick={handleSaveParams} style={{ padding: '8px 16px', backgroundColor: '#16a34a', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>保存并分析</button>
                  <button onClick={() => setParams(DEFAULT_PARAMS)} style={{ padding: '8px 16px', backgroundColor: '#e5e7eb', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>恢复默认</button>
                </div>
              </div>
            )}

            {signal && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px', marginBottom: '24px' }}>
                <div style={{ backgroundColor: getRecColor(signal.recommendation), borderRadius: '8px', padding: '24px', color: 'white' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>交易建议</h3>
                  <div style={{ fontSize: '36px', fontWeight: 'bold', marginBottom: '8px' }}>{getRecText(signal.recommendation)}</div>
                  <div style={{ fontSize: '14px', opacity: 0.9 }}>综合评分: {signal.overall_score} 分</div>
                  <div style={{ fontSize: '14px', marginTop: '8px' }}>当前价格: ¥{signal.close?.toFixed(2)}</div>
                </div>
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>技术指标</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div><div style={{ fontSize: '12px', color: '#6b7280' }}>均线趋势</div><div style={{ fontWeight: 500 }}>{signal.ma_signals?.trend || '震荡'}</div></div>
                    <div><div style={{ fontSize: '12px', color: '#6b7280' }}>RSI</div><div style={{ fontWeight: 500 }}>{signal.rsi?.toFixed(1)} ({signal.rsi_signal})</div></div>
                    <div><div style={{ fontSize: '12px', color: '#6b7280' }}>MACD</div><div style={{ fontWeight: 500 }}>{signal.macd_signal}</div></div>
                    <div><div style={{ fontSize: '12px', color: '#6b7280' }}>布林带</div><div style={{ fontWeight: 500 }}>{signal.bb_signal}</div></div>
                  </div>
                </div>
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>交易原因</h3>
                  {signal.reasons?.length > 0 ? (
                    <ul style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {signal.reasons.map((reason: string, i: number) => (<li key={i} style={{ fontSize: '14px', display: 'flex', gap: '8px' }}><span style={{ color: '#3b82f6' }}>•</span>{reason}</li>))}
                    </ul>
                  ) : <p style={{ color: '#6b7280' }}>暂无具体原因</p>}
                  <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
                    {signal.recommendation?.includes('buy') && <button onClick={() => handleAddTrade('buy')} style={{ flex: 1, padding: '8px', backgroundColor: '#16a34a', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>记录买入</button>}
                    {signal.recommendation?.includes('sell') && <button onClick={() => handleAddTrade('sell')} style={{ flex: 1, padding: '8px', backgroundColor: '#dc2626', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>记录卖出</button>}
                  </div>
                </div>
              </div>
            )}

            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>交易日志</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '16px', marginBottom: '24px' }}>
                <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.total_trades}</div><div style={{ fontSize: '12px', color: '#6b7280' }}>总交易</div></div>
                <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#f0fdf4', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold', color: '#16a34a' }}>{stats.winning_trades}</div><div style={{ fontSize: '12px', color: '#6b7280' }}>盈利</div></div>
                <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#fef2f2', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold', color: '#dc2626' }}>{stats.losing_trades}</div><div style={{ fontSize: '12px', color: '#6b7280' }}>亏损</div></div>
                <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#eff6ff', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold', color: '#2563eb' }}>{stats.win_rate.toFixed(1)}%</div><div style={{ fontSize: '12px', color: '#6b7280' }}>胜率</div></div>
              </div>
              {trades.length > 0 ? (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', fontSize: '14px' }}>
                    <thead style={{ backgroundColor: '#f9fafb' }}>
                      <tr><th style={{ padding: '12px', textAlign: 'left' }}>时间</th><th style={{ padding: '12px', textAlign: 'left' }}>标的</th><th style={{ padding: '12px', textAlign: 'left' }}>操作</th><th style={{ padding: '12px', textAlign: 'right' }}>价格</th><th style={{ padding: '12px', textAlign: 'left' }}>原因</th></tr>
                    </thead>
                    <tbody>
                      {trades.map((trade, i) => (
                        <tr key={i} style={{ borderTop: '1px solid #e5e7eb' }}>
                          <td style={{ padding: '12px' }}>{trade.timestamp}</td>
                          <td style={{ padding: '12px' }}>{trade.symbol}</td>
                          <td style={{ padding: '12px' }}><span style={{ padding: '4px 8px', borderRadius: '4px', color: 'white', backgroundColor: trade.action === 'buy' ? '#16a34a' : '#dc2626' }}>{trade.action === 'buy' ? '买入' : '卖出'}</span></td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>¥{trade.price?.toFixed(2)}</td>
                          <td style={{ padding: '12px', color: '#6b7280' }}>{trade.reason || trade.reasons?.join('; ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p style={{ textAlign: 'center', color: '#6b7280', padding: '32px' }}>暂无交易记录</p>}
            </div>
          </>
        )}

        {/* 数据查询页面 */}
        {page === 'stock' && (
          <>
            {/* 搜索框 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
                <select
                  value={stockSource}
                  onChange={(e) => setStockSource(e.target.value)}
                  style={{ padding: '12px 16px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '16px', backgroundColor: 'white', minWidth: '160px' }}
                >
                  <option value="yfinance">Yahoo Finance</option>
                  <option value="akshare">Akshare (A股)</option>
                  <option value="tushare">Tushare</option>
                </select>
                <input
                  type="text"
                  value={stockSymbol}
                  onChange={(e) => setStockSymbol(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === 'Enter' && handleStockSearch()}
                  placeholder="输入股票代码，如: 600519, AAPL, 510300"
                  style={{ flex: 1, minWidth: '200px', padding: '12px 16px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '16px' }}
                />
                <button
                  onClick={handleStockSearch}
                  disabled={stockLoading || !stockSymbol}
                  style={{ padding: '12px 24px', backgroundColor: '#2563eb', color: 'white', border: 'none', borderRadius: '6px', cursor: stockLoading ? 'not-allowed' : 'pointer', opacity: stockLoading ? 0.5 : 1 }}
                >
                  {stockLoading ? '查询中...' : '🔍 查询'}
                </button>
              </div>
              
              {/* 快捷选择 */}
              <div style={{ marginTop: '8px' }}>
                <span style={{ fontSize: '14px', color: '#6b7280', marginRight: '12px' }}>快速选择:</span>
                {[{ code: '510300', name: '沪深300ETF' }, { code: '159919', name: '券商ETF' }, { code: '000001', name: '平安银行' }, { code: '600519', name: '贵州茅台' }, { code: 'AAPL', name: '苹果' }, { code: 'MSFT', name: '微软' }].map((s) => (
                  <button
                    key={s.code}
                    onClick={() => setStockSymbol(s.code)}
                    style={{ margin: '4px', padding: '4px 12px', backgroundColor: stockSymbol === s.code ? '#2563eb' : '#f3f4f6', color: stockSymbol === s.code ? 'white' : '#374151', border: 'none', borderRadius: '16px', cursor: 'pointer', fontSize: '13px' }}
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            </div>

            {/* 日志面板 */}
            <div style={{ backgroundColor: '#1f2937', borderRadius: '8px', padding: '16px', marginBottom: '24px', maxHeight: '200px', overflowY: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ color: '#9ca3af', fontSize: '14px', fontWeight: 600 }}>📝 查询日志</span>
                <button onClick={clearStockLogs} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: '12px' }}>清空</button>
              </div>
              {stockLogs.length === 0 ? (
                <div style={{ color: '#6b7280', fontSize: '13px' }}>暂无日志...</div>
              ) : (
                stockLogs.map((log, i) => (
                  <div key={i} style={{ display: 'flex', gap: '12px', marginBottom: '6px', fontSize: '13px' }}>
                    <span style={{ color: '#9ca3af', minWidth: '80px' }}>{log.time}</span>
                    <span style={{ color: log.type === 'success' ? '#16a34a' : log.type === 'error' ? '#dc2626' : log.type === 'loading' ? '#2563eb' : '#6b7280' }}>{log.message}</span>
                  </div>
                ))
              )}
            </div>

            {/* 实时报价 */}
            {stockInfo && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <div style={{ fontSize: '14px', color: '#6b7280' }}>股票名称</div>
                  <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stockInfo.name}</div>
                </div>
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <div style={{ fontSize: '14px', color: '#6b7280' }}>当前价格</div>
                  <div style={{ fontSize: '24px', fontWeight: 'bold' }}>${stockInfo.price?.toFixed(2)}</div>
                </div>
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <div style={{ fontSize: '14px', color: '#6b7280' }}>涨跌额</div>
                  <div style={{ fontSize: '24px', fontWeight: 'bold', color: (stockInfo.change || 0) >= 0 ? '#16a34a' : '#dc2626' }}>
                    {stockInfo.change >= 0 ? '+' : ''}{stockInfo.change?.toFixed(2)}
                  </div>
                </div>
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <div style={{ fontSize: '14px', color: '#6b7280' }}>涨跌幅</div>
                  <div style={{ fontSize: '24px', fontWeight: 'bold', color: (stockInfo.change_pct || 0) >= 0 ? '#16a34a' : '#dc2626' }}>
                    {stockInfo.change_pct >= 0 ? '+' : ''}{stockInfo.change_pct?.toFixed(2)}%
                  </div>
                </div>
              </div>
            )}

            {/* 历史数据表格 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>历史行情数据 (近一月)</h2>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse', minWidth: '600px' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f9fafb' }}>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600, whiteSpace: 'nowrap' }}>日期</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>开盘</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>最高</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>最低</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>收盘</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>涨跌幅</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>成交量</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>MA5</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>MA10</th>
                      <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>RSI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stockHistory.length > 0 ? (
                      stockHistory.slice().reverse().map((row, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                          <td style={{ padding: '10px 8px', textAlign: 'center', whiteSpace: 'nowrap' }}>{row.Date}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>{row.Open?.toFixed(2)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>{row.High?.toFixed(2)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>{row.Low?.toFixed(2)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center', fontWeight: 500 }}>{row.Close?.toFixed(2)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center', color: (row.涨跌幅 || 0) >= 0 ? '#16a34a' : '#dc2626' }}>
                            {row.涨跌幅 >= 0 ? '+' : ''}{row.涨跌幅?.toFixed(2)}%
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>{formatNumber(row.Volume)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center', color: row.Close > row.MA5 ? '#16a34a' : '#dc2626' }}>{row.MA5?.toFixed(2)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center', color: row.Close > row.MA10 ? '#16a34a' : '#dc2626' }}>{row.MA10?.toFixed(2)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>{row.RSI?.toFixed(1)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: '#9ca3af' }}>
                          {stockLoading ? '正在加载数据...' : '暂无数据，请输入股票代码查询'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 详细信息 */}
            {stockDetail && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
                {/* 基本信息 */}
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #e5e7eb' }}>📋 基本信息</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '14px' }}>
                    <div><span style={{ color: '#6b7280' }}>股票代码:</span></div>
                    <div>{stockDetail.basic?.symbol}</div>
                    <div><span style={{ color: '#6b7280' }}>股票名称:</span></div>
                    <div>{stockDetail.basic?.name}</div>
                    <div><span style={{ color: '#6b7280' }}>交易所:</span></div>
                    <div>{stockDetail.basic?.exchange}</div>
                  </div>
                </div>

                {/* 市值数据 */}
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #e5e7eb' }}>💰 市值数据</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '14px' }}>
                    <div><span style={{ color: '#6b7280' }}>总市值:</span></div>
                    <div>{formatNumber(stockDetail.market?.market_cap)}</div>
                    <div><span style={{ color: '#6b7280' }}>总股本:</span></div>
                    <div>{formatNumber(stockDetail.market?.shares_outstanding)}</div>
                  </div>
                </div>

                {/* 估值指标 */}
                <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #e5e7eb' }}>📊 估值指标</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '14px' }}>
                    <div><span style={{ color: '#6b7280' }}>市盈率(PE):</span></div>
                    <div>{stockDetail.valuation?.pe_ratio?.toFixed(2)}</div>
                    <div><span style={{ color: '#6b7280' }}>市净率(PB):</span></div>
                    <div>{stockDetail.valuation?.pb_ratio?.toFixed(2)}</div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* 模拟交易页面 */}
        {page === 'simulation' && (
          <>
            {/* 标的管理 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>📈 标的池管理</h2>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                <input placeholder="股票代码" value={newSymbol.code} onChange={(e) => setNewSymbol({...newSymbol, code: e.target.value})} style={{ border: '1px solid #d1d5db', borderRadius: '6px', padding: '8px 12px', width: '150px' }} />
                <input placeholder="股票名称" value={newSymbol.name} onChange={(e) => setNewSymbol({...newSymbol, name: e.target.value})} style={{ border: '1px solid #d1d5db', borderRadius: '6px', padding: '8px 12px', width: '150px' }} />
                <button onClick={addSymbol} style={{ padding: '8px 16px', backgroundColor: '#2563eb', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>添加</button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {symbols.map((s) => (
                  <span key={s.code} style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '6px 12px', backgroundColor: '#f3f4f6', borderRadius: '20px', fontSize: '14px' }}>
                    {s.name} ({s.code})
                    <button onClick={() => removeSymbol(s.code)} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#6b7280', fontSize: '16px' }}>×</button>
                  </span>
                ))}
              </div>
            </div>

            {/* 模拟交易控制 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>🎮 模拟交易</h2>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <label style={{ fontSize: '14px', fontWeight: 500 }}>初始资金:</label>
                  <input type="number" value={simCapital} onChange={(e) => setSimCapital(parseInt(e.target.value))} style={{ border: '1px solid #d1d5db', borderRadius: '6px', padding: '8px 12px', width: '150px' }} />
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <label style={{ fontSize: '14px', fontWeight: 500 }}>选择标的:</label>
                  <select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)} style={{ border: '1px solid #d1d5db', borderRadius: '6px', padding: '8px 12px' }}>
                    {symbols.map((s) => (<option key={s.code} value={s.code}>{s.name} ({s.code})</option>))}
                  </select>
                </div>
              </div>
            </div>

            {/* 模拟结果展示 - 由于网络原因显示说明 */}
            <div style={{ backgroundColor: '#fef3c7', borderRadius: '8px', padding: '24px', marginBottom: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px', color: '#92400e' }}>⚠️ 说明</h3>
              <p style={{ color: '#92400e', fontSize: '14px' }}>
                由于当前网络环境无法访问股票数据接口（akshare 需要连接东方财富网），模拟交易功能需要以下条件才能运行：
              </p>
              <ul style={{ marginTop: '12px', color: '#92400e', fontSize: '14px', paddingLeft: '20px' }}>
                <li>1. 需要能够访问国内股票数据接口</li>
                <li>2. 或使用 VPN/代理连接网络</li>
                <li>3. 或修改代码使用其他数据源（如 yfinance）</li>
              </ul>
            </div>
          </>
        )}
      </main>

      <footer style={{ backgroundColor: '#1f2937', color: 'white', padding: '16px 0', marginTop: '48px' }}>
        <div style={{ textAlign: 'center', fontSize: '14px' }}>量化交易分析系统 - 仅供参考，不构成投资建议</div>
      </footer>
    </div>
  );
}

'use client';

import { useState, useEffect, useCallback } from 'react';

interface Signal {
  date: string;
  close: number;
  change_pct: number;
  ma_signals: { trend: string };
  rsi: number;
  rsi_signal: string;
  macd_signal: string;
  bb_signal: string;
  volume_signal: string;
  overall_score: number;
  recommendation: string;
  reasons: string[];
}

interface Symbol {
  code: string;
  name: string;
}

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

export default function Home() {
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState('sh000001');
  const [signal, setSignal] = useState<Signal | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<Stats>({ total_trades: 0, winning_trades: 0, losing_trades: 0, win_rate: 0, total_profit: 0, avg_profit: 0 });
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [loading, setLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    fetch('http://localhost:5000/api/symbols')
      .then(res => res.json())
      .then(data => { if (data.success) setSymbols(data.data); });
    
    fetch('http://localhost:5000/api/params')
      .then(res => res.json())
      .then(data => setParams(data));
  }, []);

  const handleAnalyze = useCallback(() => {
    setLoading(true);
    fetch('http://localhost:5000/api/analyze', {
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

  useEffect(() => {
    fetch('http://localhost:5000/api/trades')
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setTrades(data.data.trades);
          setStats(data.data.statistics);
        }
      });
  }, []);

  const handleSaveParams = () => {
    fetch('http://localhost:5000/api/params', {
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
    fetch('http://localhost:5000/api/trades', {
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
      fetch('http://localhost:5000/api/trades')
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setTrades(data.data.trades);
            setStats(data.data.statistics);
          }
        });
    });
  };

  const getRecColor = (rec: string) => {
    if (rec.includes('strong_buy') || rec.includes('buy')) return '#16a34a';
    if (rec.includes('sell')) return '#dc2626';
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
      <header style={{ background: 'linear-gradient(to right, #2563eb, #4f46e5)', color: 'white', padding: '24px 0' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 16px' }}>
          <h1 style={{ fontSize: '30px', fontWeight: 'bold' }}>📈 量化交易分析系统</h1>
          <p style={{ marginTop: '8px', opacity: 0.9 }}>基于技术指标的趋势交易分析工具</p>
        </div>
      </header>

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px 16px' }}>
        {/* 控制栏 */}
        <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '16px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <label style={{ fontSize: '14px', fontWeight: 500 }}>选择标的:</label>
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                style={{ border: '1px solid #d1d5db', borderRadius: '6px', padding: '8px 12px' }}
              >
                {symbols.map((s) => (
                  <option key={s.code} value={s.code}>{s.name} ({s.code})</option>
                ))}
              </select>
            </div>
            <button
              onClick={handleAnalyze}
              disabled={loading}
              style={{ padding: '8px 24px', backgroundColor: '#2563eb', color: 'white', borderRadius: '6px', border: 'none', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.5 : 1 }}
            >
              {loading ? '分析中...' : '🔍 分析'}
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              style={{ padding: '8px 16px', backgroundColor: '#e5e7eb', borderRadius: '6px', border: 'none', cursor: 'pointer' }}
            >
              ⚙️ 参数设置
            </button>
          </div>
        </div>

        {/* 参数设置 */}
        {showSettings && (
          <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>参数设置</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '24px' }}>
              <div>
                <h3 style={{ fontWeight: 500, marginBottom: '8px' }}>均线参数</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ fontSize: '14px' }}>短期均线: {params.ma_short}</label>
                  <input type="range" min="3" max="20" value={params.ma_short} onChange={(e) => setParams({...params, ma_short: parseInt(e.target.value)})} style={{ width: '100%' }} />
                  <label style={{ fontSize: '14px' }}>中期均线: {params.ma_medium}</label>
                  <input type="range" min="5" max="30" value={params.ma_medium} onChange={(e) => setParams({...params, ma_medium: parseInt(e.target.value)})} style={{ width: '100%' }} />
                  <label style={{ fontSize: '14px' }}>长期均线: {params.ma_long}</label>
                  <input type="range" min="10" max="60" value={params.ma_long} onChange={(e) => setParams({...params, ma_long: parseInt(e.target.value)})} style={{ width: '100%' }} />
                </div>
              </div>
              <div>
                <h3 style={{ fontWeight: 500, marginBottom: '8px' }}>RSI 参数</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ fontSize: '14px' }}>RSI 周期: {params.rsi_period}</label>
                  <input type="range" min="5" max="28" value={params.rsi_period} onChange={(e) => setParams({...params, rsi_period: parseInt(e.target.value)})} style={{ width: '100%' }} />
                  <label style={{ fontSize: '14px' }}>超卖: {params.rsi_oversold}</label>
                  <input type="range" min="10" max="40" value={params.rsi_oversold} onChange={(e) => setParams({...params, rsi_oversold: parseInt(e.target.value)})} style={{ width: '100%' }} />
                  <label style={{ fontSize: '14px' }}>超买: {params.rsi_overbought}</label>
                  <input type="range" min="60" max="90" value={params.rsi_overbought} onChange={(e) => setParams({...params, rsi_overbought: parseInt(e.target.value)})} style={{ width: '100%' }} />
                </div>
              </div>
              <div>
                <h3 style={{ fontWeight: 500, marginBottom: '8px' }}>策略参数</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ fontSize: '14px' }}>买入阈值: {params.buy_score_threshold}</label>
                  <input type="range" min="-2" max="5" value={params.buy_score_threshold} onChange={(e) => setParams({...params, buy_score_threshold: parseInt(e.target.value)})} style={{ width: '100%' }} />
                  <label style={{ fontSize: '14px' }}>强买阈值: {params.strong_buy_score}</label>
                  <input type="range" min="1" max="8" value={params.strong_buy_score} onChange={(e) => setParams({...params, strong_buy_score: parseInt(e.target.value)})} style={{ width: '100%' }} />
                  <label style={{ fontSize: '14px' }}>止损: {params.stop_loss_pct}%</label>
                  <input type="range" min="1" max="15" value={params.stop_loss_pct} onChange={(e) => setParams({...params, stop_loss_pct: parseInt(e.target.value)})} style={{ width: '100%' }} />
                  <label style={{ fontSize: '14px' }}>止盈: {params.take_profit_pct}%</label>
                  <input type="range" min="5" max="30" value={params.take_profit_pct} onChange={(e) => setParams({...params, take_profit_pct: parseInt(e.target.value)})} style={{ width: '100%' }} />
                </div>
              </div>
            </div>
            <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
              <button onClick={handleSaveParams} style={{ padding: '8px 16px', backgroundColor: '#16a34a', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>保存并分析</button>
              <button onClick={() => setParams(DEFAULT_PARAMS)} style={{ padding: '8px 16px', backgroundColor: '#e5e7eb', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>恢复默认</button>
            </div>
          </div>
        )}

        {/* 分析结果 */}
        {signal && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px', marginBottom: '24px' }}>
              <div style={{ backgroundColor: getRecColor(signal.recommendation), borderRadius: '8px', padding: '24px', color: 'white' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>交易建议</h3>
                <div style={{ fontSize: '36px', fontWeight: 'bold', marginBottom: '8px' }}>{getRecText(signal.recommendation)}</div>
                <div style={{ fontSize: '14px', opacity: 0.9 }}>综合评分: {signal.overall_score} 分</div>
                <div style={{ fontSize: '14px', marginTop: '8px' }}>当前价格: ¥{signal.close.toFixed(2)}</div>
              </div>
              
              <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>技术指标</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div><div style={{ fontSize: '12px', color: '#6b7280' }}>均线趋势</div><div style={{ fontWeight: 500 }}>{signal.ma_signals?.trend || '震荡'}</div></div>
                  <div><div style={{ fontSize: '12px', color: '#6b7280' }}>RSI</div><div style={{ fontWeight: 500 }}>{signal.rsi?.toFixed(1)} ({signal.rsi_signal})</div></div>
                  <div><div style={{ fontSize: '12px', color: '#6b7280' }}>MACD</div><div style={{ fontWeight: 500 }}>{signal.macd_signal}</div></div>
                  <div><div style={{ fontSize: '12px', color: '#6b7280' }}>布林带</div><div style={{ fontWeight: 500 }}>{signal.bb_signal}</div></div>
                  <div><div style={{ fontSize: '12px', color: '#6b7280' }}>成交量</div><div style={{ fontWeight: 500 }}>{signal.volume_signal}</div></div>
                </div>
              </div>
              
              <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>交易原因</h3>
                {signal.reasons && signal.reasons.length > 0 ? (
                  <ul style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {signal.reasons.map((reason, i) => (
                      <li key={i} style={{ fontSize: '14px', display: 'flex', gap: '8px' }}><span style={{ color: '#3b82f6' }}>•</span>{reason}</li>
                    ))}
                  </ul>
                ) : <p style={{ color: '#6b7280' }}>暂无具体原因</p>}
                
                <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
                  {signal.recommendation.includes('buy') && (
                    <button onClick={() => handleAddTrade('buy')} style={{ flex: 1, padding: '8px', backgroundColor: '#16a34a', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>记录买入</button>
                  )}
                  {signal.recommendation.includes('sell') && (
                    <button onClick={() => handleAddTrade('sell')} style={{ flex: 1, padding: '8px', backgroundColor: '#dc2626', color: 'white', borderRadius: '6px', border: 'none', cursor: 'pointer' }}>记录卖出</button>
                  )}
                </div>
              </div>
            </div>
          </>
        )}

        {/* 交易日志 */}
        <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>交易日志</h2>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.total_trades}</div><div style={{ fontSize: '12px', color: '#6b7280' }}>总交易</div></div>
            <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#f0fdf4', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold', color: '#16a34a' }}>{stats.winning_trades}</div><div style={{ fontSize: '12px', color: '#6b7280' }}>盈利</div></div>
            <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#fef2f2', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold', color: '#dc2626' }}>{stats.losing_trades}</div><div style={{ fontSize: '12px', color: '#6b7280' }}>亏损</div></div>
            <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#eff6ff', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold', color: '#2563eb' }}>{stats.win_rate.toFixed(1)}%</div><div style={{ fontSize: '12px', color: '#6b7280' }}>胜率</div></div>
            <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#faf5ff', borderRadius: '8px' }}><div style={{ fontSize: '24px', fontWeight: 'bold', color: stats.total_profit >= 0 ? '#16a34a' : '#dc2626' }}>{stats.total_profit.toFixed(2)}%</div><div style={{ fontSize: '12px', color: '#6b7280' }}>总收益</div></div>
          </div>
          
          {trades.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', fontSize: '14px' }}>
                <thead style={{ backgroundColor: '#f9fafb' }}>
                  <tr>
                    <th style={{ padding: '12px', textAlign: 'left' }}>时间</th>
                    <th style={{ padding: '12px', textAlign: 'left' }}>标的</th>
                    <th style={{ padding: '12px', textAlign: 'left' }}>操作</th>
                    <th style={{ padding: '12px', textAlign: 'right' }}>价格</th>
                    <th style={{ padding: '12px', textAlign: 'left' }}>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade, i) => (
                    <tr key={i} style={{ borderTop: '1px solid #e5e7eb' }}>
                      <td style={{ padding: '12px' }}>{trade.timestamp}</td>
                      <td style={{ padding: '12px' }}>{trade.symbol}</td>
                      <td style={{ padding: '12px' }}>
                        <span style={{ padding: '4px 8px', borderRadius: '4px', color: 'white', backgroundColor: trade.action === 'buy' ? '#16a34a' : '#dc2626' }}>
                          {trade.action === 'buy' ? '买入' : '卖出'}
                        </span>
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right' }}>¥{trade.price?.toFixed(2)}</td>
                      <td style={{ padding: '12px', color: '#6b7280' }}>{trade.reason || trade.reasons?.join('; ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ textAlign: 'center', color: '#6b7280', padding: '32px' }}>暂无交易记录</p>
          )}
        </div>
      </main>
      
      <footer style={{ backgroundColor: '#1f2937', color: 'white', padding: '16px 0', marginTop: '48px' }}>
        <div style={{ textAlign: 'center', fontSize: '14px' }}>量化交易分析系统 - 仅供参考，不构成投资建议</div>
      </footer>
    </div>
  );
}

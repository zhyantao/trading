'use client';

import { useState } from 'react';

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
  涨跌额: number;
  MA5: number;
  MA10: number;
  MA20: number;
  VOL_MA5: number;
  RSI: number;
}

interface StockDetail {
  basic: any;
  price: any;
  market: any;
  valuation: any;
  finance: any;
  dividend: any;
  risk: any;
}

const SAMPLE_SYMBOLS = [
  { code: '510300', name: '沪深300ETF' },
  { code: '159919', name: '券商ETF' },
  { code: '000001', name: '平安银行' },
  { code: '600519', name: '贵州茅台' },
  { code: 'AAPL', name: '苹果' },
  { code: 'MSFT', name: '微软' },
];

export default function StockPage() {
  const [symbol, setSymbol] = useState('');
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [stockInfo, setStockInfo] = useState<StockInfo | null>(null);
  const [history, setHistory] = useState<HistoryData[]>([]);
  const [stockDetail, setStockDetail] = useState<StockDetail | null>(null);

  const addLog = (message: string, type: LogEntry['type'] = 'info') => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { time, message, type }]);
  };

  const clearLogs = () => setLogs([]);

  const handleSearch = async () => {
    if (!symbol) {
      addLog('请输入股票代码', 'error');
      return;
    }
    
    setLoading(true);
    clearLogs();
    addLog(`开始查询股票: ${symbol}`, 'info');
    setStockInfo(null);
    setHistory([]);
    setStockDetail(null);

    try {
      // 获取实时报价
      addLog('正在获取实时报价...', 'loading');
      const quoteRes = await fetch('http://localhost:5001/api/stock/quote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      });
      const quoteData = await quoteRes.json();
      
      if (quoteData.success) {
        setStockInfo(quoteData.data);
        addLog(`✓ 实时报价获取成功: $${quoteData.data.price?.toFixed(2)}`, 'success');
      } else {
        addLog(`✗ 实时报价获取失败: ${quoteData.error}`, 'error');
      }

      // 获取历史数据
      addLog('正在获取历史行情数据...', 'loading');
      const historyRes = await fetch('http://localhost:5001/api/stock/history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, period: '1mo' }),
      });
      const historyData = await historyRes.json();
      
      if (historyData.success) {
        setHistory(historyData.data);
        addLog(`✓ 历史数据获取成功: ${historyData.data.length} 条记录`, 'success');
      } else {
        addLog(`✗ 历史数据获取失败: ${historyData.error}`, 'error');
      }

      // 获取详细信息
      addLog('正在获取详细信息...', 'loading');
      const infoRes = await fetch('http://localhost:5001/api/stock/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      });
      const infoData = await infoRes.json();
      
      if (infoData.success) {
        setStockDetail(infoData.data);
        addLog(`✓ 详细信息获取成功`, 'success');
      } else {
        addLog(`✗ 详细信息获取失败: ${infoData.error}`, 'error');
      }

      addLog('查询完成', 'info');
    } catch (e: any) {
      addLog(`✗ 查询异常: ${e.message || e}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const formatNumber = (num: number) => {
    if (!num && num !== 0) return '-';
    if (num >= 100000000) return (num / 100000000).toFixed(2) + '亿';
    if (num >= 10000) return (num / 10000).toFixed(2) + '万';
    return num.toFixed(2);
  };

  const getLogColor = (type: LogEntry['type']) => {
    switch (type) {
      case 'success': return '#16a34a';
      case 'error': return '#dc2626';
      case 'loading': return '#2563eb';
      default: return '#6b7280';
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb' }}>
      {/* 头部 */}
      <header style={{ background: 'linear-gradient(to right, #2563eb, #4f46e5)', color: 'white', padding: '24px 0' }}>
        <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '0 16px' }}>
          <h1 style={{ fontSize: '30px', fontWeight: 'bold' }}>📊 股票数据查询</h1>
          <p style={{ marginTop: '8px', opacity: 0.9 }}>查询股票/基金的实时报价、历史数据和相关指标</p>
        </div>
      </header>

      <main style={{ maxWidth: '1400px', margin: '0 auto', padding: '24px 16px' }}>
        {/* 搜索框 */}
        <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="输入股票代码，如: 600519, AAPL, 510300"
              style={{ flex: 1, minWidth: '200px', padding: '12px 16px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '16px' }}
            />
            <button
              onClick={handleSearch}
              disabled={loading || !symbol}
              style={{ padding: '12px 24px', backgroundColor: '#2563eb', color: 'white', border: 'none', borderRadius: '6px', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.5 : 1 }}
            >
              {loading ? '查询中...' : '🔍 查询'}
            </button>
          </div>
          
          {/* 快捷选择 */}
          <div style={{ marginTop: '12px' }}>
            <span style={{ fontSize: '14px', color: '#6b7280', marginRight: '12px' }}>快速选择:</span>
            {SAMPLE_SYMBOLS.map((s) => (
              <button
                key={s.code}
                onClick={() => setSymbol(s.code)}
                style={{ margin: '4px', padding: '4px 12px', backgroundColor: symbol === s.code ? '#2563eb' : '#f3f4f6', color: symbol === s.code ? 'white' : '#374151', border: 'none', borderRadius: '16px', cursor: 'pointer', fontSize: '13px' }}
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
            <button onClick={clearLogs} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: '12px' }}>清空</button>
          </div>
          {logs.length === 0 ? (
            <div style={{ color: '#6b7280', fontSize: '13px' }}>暂无日志...</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} style={{ display: 'flex', gap: '12px', marginBottom: '6px', fontSize: '13px' }}>
                <span style={{ color: '#9ca3af', minWidth: '80px' }}>{log.time}</span>
                <span style={{ color: getLogColor(log.type) }}>{log.message}</span>
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

        {/* 历史数据表格 - 始终显示表头 */}
        <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px' }}>历史行情数据 (近一月)</h2>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse', minWidth: '800px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb' }}>
                  <th style={{ padding: '12px 8px', textAlign: 'left', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>日期</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>开盘</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>最高</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>最低</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>收盘</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>涨跌幅</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>成交量</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>MA5</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>MA10</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', borderBottom: '2px solid #e5e7eb', fontWeight: 600 }}>RSI</th>
                </tr>
              </thead>
              <tbody>
                {history.length > 0 ? (
                  history.slice().reverse().map((row, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '10px 8px' }}>{row.Date}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right' }}>{row.Open?.toFixed(2)}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right' }}>{row.High?.toFixed(2)}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right' }}>{row.Low?.toFixed(2)}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 500 }}>{row.Close?.toFixed(2)}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right', color: (row.涨跌幅 || 0) >= 0 ? '#16a34a' : '#dc2626' }}>
                        {row.涨跌幅 >= 0 ? '+' : ''}{row.涨跌幅?.toFixed(2)}%
                      </td>
                      <td style={{ padding: '10px 8px', textAlign: 'right' }}>{formatNumber(row.Volume)}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right', color: row.Close > row.MA5 ? '#16a34a' : '#dc2626' }}>{row.MA5?.toFixed(2)}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right', color: row.Close > row.MA10 ? '#16a34a' : '#dc2626' }}>{row.MA10?.toFixed(2)}</td>
                      <td style={{ padding: '10px 8px', textAlign: 'right' }}>{row.RSI?.toFixed(1)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: '#9ca3af' }}>
                      {loading ? '正在加载数据...' : '暂无数据，请输入股票代码查询'}
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
                <div><span style={{ color: '#6b7280' }}>所属行业:</span></div>
                <div>{stockDetail.basic?.sector}</div>
              </div>
            </div>

            {/* 市值数据 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #e5e7eb' }}>💰 市值数据</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '14px' }}>
                <div><span style={{ color: '#6b7280' }}>总市值:</span></div>
                <div>{formatNumber(stockDetail.market?.market_cap)}</div>
                <div><span style={{ color: '#6b7280' }}>企业价值:</span></div>
                <div>{formatNumber(stockDetail.market?.enterprise_value)}</div>
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
                <div><span style={{ color: '#6b7280' }}>PEG:</span></div>
                <div>{stockDetail.valuation?.peg_ratio?.toFixed(2)}</div>
              </div>
            </div>

            {/* 财务指标 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #e5e7eb' }}>💵 财务指标</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '14px' }}>
                <div><span style={{ color: '#6b7280' }}>每股收益(EPS):</span></div>
                <div>{stockDetail.finance?.eps?.toFixed(2)}</div>
                <div><span style={{ color: '#6b7280' }}>净利润率:</span></div>
                <div>{(stockDetail.finance?.profit_margin * 100)?.toFixed(2)}%</div>
                <div><span style={{ color: '#6b7280' }}>ROE:</span></div>
                <div>{(stockDetail.finance?.roe * 100)?.toFixed(2)}%</div>
              </div>
            </div>

            {/* 分红送转 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #e5e7eb' }}>🎁 分红送转</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '14px' }}>
                <div><span style={{ color: '#6b7280' }}>股息率:</span></div>
                <div>{(stockDetail.dividend?.dividend_yield * 100)?.toFixed(2)}%</div>
                <div><span style={{ color: '#6b7280' }}>分红率:</span></div>
                <div>{stockDetail.dividend?.dividend_rate?.toFixed(2)}</div>
              </div>
            </div>

            {/* 风险指标 */}
            <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', paddingBottom: '12px', borderBottom: '1px solid #e5e7eb' }}>⚠️ 风险指标</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '14px' }}>
                <div><span style={{ color: '#6b7280' }}>Beta:</span></div>
                <div>{stockDetail.risk?.beta?.toFixed(2)}</div>
                <div><span style={{ color: '#6b7280' }}>Alpha:</span></div>
                <div>{stockDetail.risk?.alpha?.toFixed(2)}</div>
                <div><span style={{ color: '#6b7280' }}>夏普比率:</span></div>
                <div>{stockDetail.risk?.sharpe_ratio?.toFixed(2)}</div>
              </div>
            </div>
          </div>
        )}

        {/* 无数据提示 */}
        {!loading && !stockInfo && !stockDetail && (
          <div style={{ textAlign: 'center', padding: '60px', color: '#6b7280' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>📈</div>
            <div style={{ fontSize: '18px' }}>请输入股票代码查询数据</div>
            <div style={{ fontSize: '14px', marginTop: '8px' }}>支持A股、港股、美股、ETF等</div>
          </div>
        )}
      </main>

      <footer style={{ backgroundColor: '#1f2937', color: 'white', padding: '16px 0', marginTop: '48px' }}>
        <div style={{ textAlign: 'center', fontSize: '14px' }}>股票数据查询 - 仅供学习研究，不构成投资建议</div>
      </footer>
    </div>
  );
}

'use client';

import { useState, useEffect } from 'react';

interface Trade {
  date: string;
  action: string;
  symbol: string;
  name: string;
  shares: number;
  price: number;
  amount: number;
  profit?: number;
  profit_pct?: number;
  reasons: string[];
}

const INITIAL_CAPITAL = 1000000;

export default function Home() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(false);

  // 加载模拟交易数据
  useEffect(() => {
    fetch('/api/simulation')
      .then(res => res.json())
      .then(data => {
        if (data.success) setTrades(data.data);
      })
      .catch(() => {
        // 使用默认模拟数据
        setTrades([
          { date: '2026-02-08', action: 'buy', symbol: 'SH000001', name: '上证指数', shares: 1100, price: 256.53, amount: 282181.31, reasons: ['均线多头排列'] },
          { date: '2026-02-26', action: 'sell', symbol: 'SH600036', name: '上证指数', shares: 1100, price: 260.15, amount: 286162.64, profit: 3981.33, profit_pct: 1.41, reasons: ['MACD死叉'] },
        ]);
      });
  }, []);

  // 计算统计
  const finalCapital = trades.length > 0 && trades[trades.length-1].action === 'sell' 
    ? trades.reduce((acc, t) => t.action === 'buy' ? acc - t.amount : acc + (t.amount + (t.profit || 0)), INITIAL_CAPITAL)
    : trades.reduce((acc, t) => t.action === 'buy' ? acc - t.amount : acc + t.amount, INITIAL_CAPITAL);
  
  const totalProfit = finalCapital - INITIAL_CAPITAL;
  const profitPct = (totalProfit / INITIAL_CAPITAL) * 100;
  
  const sellTrades = trades.filter(t => t.action === 'sell');
  const winning = sellTrades.filter(t => (t.profit || 0) > 0);
  const losing = sellTrades.filter(t => (t.profit || 0) <= 0);
  const winRate = sellTrades.length > 0 ? (winning.length / sellTrades.length) * 100 : 0;

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb' }}>
      <header style={{ background: 'linear-gradient(to right, #2563eb, #4f46e5)', color: 'white', padding: '24px 0' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 16px' }}>
          <h1 style={{ fontSize: '30px', fontWeight: 'bold' }}>📈 量化交易模拟</h1>
          <p style={{ marginTop: '8px', opacity: 0.9 }}>100万人民币初始资金 · 过去3个月数据</p>
        </div>
      </header>

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px 16px' }}>
        {/* 统计卡片 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '4px' }}>初始资金</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>¥1,000,000</div>
          </div>
          <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '4px' }}>最终资金</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: profitPct >= 0 ? '#16a34a' : '#dc2626' }}>
              ¥{finalCapital.toLocaleString()}
            </div>
          </div>
          <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '4px' }}>总收益</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: profitPct >= 0 ? '#16a34a' : '#dc2626' }}>
              {profitPct >= 0 ? '+' : ''}{profitPct.toFixed(2)}%
            </div>
          </div>
          <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '4px' }}>交易次数</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{trades.length}</div>
          </div>
          <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '4px' }}>胜率</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{winRate.toFixed(1)}%</div>
          </div>
        </div>

        {/* 交易记录 */}
        <div style={{ backgroundColor: 'white', borderRadius: '8px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <h2 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '16px' }}>交易记录</h2>
          
          {trades.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', fontSize: '14px' }}>
                <thead style={{ backgroundColor: '#f9fafb' }}>
                  <tr>
                    <th style={{ padding: '12px', textAlign: 'left' }}>日期</th>
                    <th style={{ padding: '12px', textAlign: 'left' }}>标的</th>
                    <th style={{ padding: '12px', textAlign: 'left' }}>操作</th>
                    <th style={{ padding: '12px', textAlign: 'right' }}>数量</th>
                    <th style={{ padding: '12px', textAlign: 'right' }}>价格</th>
                    <th style={{ padding: '12px', textAlign: 'right' }}>金额</th>
                    <th style={{ padding: '12px', textAlign: 'right' }}>收益</th>
                    <th style={{ padding: '12px', textAlign: 'left' }}>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade, i) => (
                    <tr key={i} style={{ borderTop: '1px solid #e5e7eb' }}>
                      <td style={{ padding: '12px' }}>{trade.date}</td>
                      <td style={{ padding: '12px' }}>{trade.name}</td>
                      <td style={{ padding: '12px' }}>
                        <span style={{ 
                          padding: '4px 8px', 
                          borderRadius: '4px', 
                          color: 'white', 
                          backgroundColor: trade.action === 'buy' ? '#16a34a' : '#dc2626' 
                        }}>
                          {trade.action === 'buy' ? '买入' : '卖出'}
                        </span>
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right' }}>{trade.shares}</td>
                      <td style={{ padding: '12px', textAlign: 'right' }}>¥{trade.price.toFixed(2)}</td>
                      <td style={{ padding: '12px', textAlign: 'right' }}>¥{trade.amount.toLocaleString()}</td>
                      <td style={{ padding: '12px', textAlign: 'right', color: (trade.profit || 0) >= 0 ? '#16a34a' : '#dc2626' }}>
                        {trade.profit ? `¥${trade.profit.toFixed(2)} (${trade.profit_pct?.toFixed(2)}%)` : '-'}
                      </td>
                      <td style={{ padding: '12px', color: '#6b7280' }}>{trade.reasons.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ textAlign: 'center', color: '#6b7280', padding: '32px' }}>暂无交易记录</p>
          )}
        </div>

        {/* 说明 */}
        <div style={{ marginTop: '24px', padding: '16px', backgroundColor: '#fef3c7', borderRadius: '8px', fontSize: '14px', color: '#92400e' }}>
          <strong>说明：</strong> 由于网络原因无法获取实时股票数据，当前展示为模拟数据演示。实际使用时需要安装 akshare 并确保网络畅通。
        </div>
      </main>

      <footer style={{ backgroundColor: '#1f2937', color: 'white', padding: '16px 0', marginTop: '48px' }}>
        <div style={{ textAlign: 'center', fontSize: '14px' }}>量化交易模拟系统 - 仅供学习研究，不构成投资建议</div>
      </footer>
    </div>
  );
}

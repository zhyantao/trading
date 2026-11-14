/* ============================================================
 * 量化交易研究 - 纯静态前端
 * 页面壳仅含容器，全部数据由 fetch data/{date}/*.json 在浏览器渲染。
 * 数据由 src/generate_static.py 产出（本地或 GitHub Actions 定时）。
 * ============================================================ */
(function () {
  'use strict';

  var PAGE = document.body.dataset.page;
  var root = document.getElementById('page-root');
  var PER_PAGE = 50;

  /* ---------------- URL 状态 ---------------- */
  var params = new URLSearchParams(location.search);
  var state = {
    date: params.get('date') || '',
    page: Math.max(1, parseInt(params.get('page') || '1', 10) || 1),
    type: params.get('type') || '',
    view: params.get('view') || '',
    minDays: parseInt(params.get('min_days') || '180', 10) || 180,
  };

  /* ---------------- 工具 ---------------- */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function fmtDate(d) {
    return d && d.length === 8 ? d.slice(0, 4) + '-' + d.slice(4, 6) + '-' + d.slice(6, 8) : d || '';
  }
  function num(v) {
    var f = parseFloat(v);
    return isNaN(f) ? null : f;
  }
  function num2(v) {
    var f = num(v);
    return f === null ? esc(v) : f.toFixed(2);
  }
  /* 涨跌配色（与原模板一致：正=绿，负=红） */
  function pc(v) {
    var f = num(v);
    if (f === null) return '';
    return f > 0 ? 'color:var(--green);' : (f < 0 ? 'color:var(--red);' : '');
  }
  function pageUrl(page, extra) {
    var p = new URLSearchParams(location.search);
    p.set('page', String(page));
    if (extra) Object.keys(extra).forEach(function (k) {
      if (extra[k] === null) p.delete(k); else p.set(k, extra[k]);
    });
    if (page === 1) p.delete('page');
    var q = p.toString();
    return location.pathname + (q ? '?' + q : '');
  }
  function setParam(key, val) {
    var p = new URLSearchParams(location.search);
    if (val) p.set(key, val); else p.delete(key);
    var q = p.toString();
    history.replaceState(null, '', location.pathname + (q ? '?' + q : ''));
  }

  var _cache = {};
  function getJSON(url) {
    if (_cache[url]) return _cache[url];
    _cache[url] = fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url);
      return r.json();
    });
    return _cache[url];
  }

  /* ---------------- 页眉（站点导航 + 应用导航） ---------------- */
  function navLink(href, page, label, date) {
    return '<a href="' + href + '?date=' + date + '" class="' +
      (PAGE === page ? 'active' : '') + '">' + label + '</a>';
  }

  function buildHeader(manifest) {
    var dates = manifest.dates || [];
    if (!state.date || dates.indexOf(state.date) < 0) state.date = manifest.latest || dates[0] || '';

    var dateOpts = dates.map(function (d) {
      return '<option value="' + d + '"' + (d === state.date ? ' selected' : '') + '>' +
        fmtDate(d) + '</option>';
    }).join('');

    document.getElementById('site-header').innerHTML =
      '<nav class="site-nav" aria-label="站点导航"><div class="nav-inner">' +
      '<a href="index.html"><img class="nav-badge" src="favicon.svg" alt="TRADING"></a>' +
      '<a href="https://zhyantao.github.io/">ZHYANTAO</a>' +
      '<a href="https://zhyantao.github.io/docs/">DOCS</a>' +
      '<a href="https://zhyantao.github.io/PS1-generator/">PS1</a>' +
      '<a href="https://zhyantao.github.io/callgraphs-generator/">CALLGRAPH</a>' +
      '<a href="https://zhyantao.github.io/riscv-bitlab/">RISC-V</a>' +
      '<a href="index.html" class="active">TRADING</a>' +
      '</div></nav>' +
      '<nav class="app-nav"><div class="nav-inner">' +
      '<a href="index.html?date=' + state.date + '" class="brand">量化信号</a>' +
      '<input type="checkbox" id="nav-toggle">' +
      '<div class="nav-links">' +
      navLink('index.html', 'dashboard', '总览', state.date) +
      navLink('signals.html', 'signals', '每日信号', state.date) +
      navLink('holdings.html', 'holdings', '我的持仓', state.date) +
      navLink('managers.html', 'managers', '经理排名', state.date) +
      navLink('funds.html', 'funds', '基金排名', state.date) +
      navLink('elite.html', 'elite', '绩优标的', state.date) +
      navLink('backtest.html', 'backtest', '回测', state.date) +
      navLink('pipeline.html', 'pipeline', '流水线', state.date) +
      '</div>' +
      '<div class="nav-actions">' +
      (dates.length
        ? '<select id="date-select" class="nav-date-select" aria-label="选择数据日期">' + dateOpts + '</select>'
        : '') +
      '<label for="nav-toggle" class="nav-toggle-btn" aria-label="菜单"><span></span><span></span><span></span></label>' +
      '</div></div></nav>';

    var sel = document.getElementById('date-select');
    if (sel) sel.addEventListener('change', function () {
      var p = new URLSearchParams(location.search);
      p.set('date', sel.value);
      p.delete('page');
      location.href = location.pathname + '?' + p.toString();
    });
  }

  /* ---------------- 通用渲染 ---------------- */
  function table(headersHtml, rowsHtml, extraCls) {
    return '<div class="table-wrap"><table class="' + (extraCls || '') + '">' +
      '<thead><tr>' + headersHtml + '</tr></thead><tbody>' + rowsHtml +
      '</tbody></table></div>';
  }
  function card(title, inner) {
    return '<div class="card">' + (title ? '<div class="card-header">' + title + '</div>' : '') +
      inner + '</div>';
  }
  function emptyState(icon, text, hint) {
    return '<div class="card"><div class="empty-state"><div class="empty-icon">' + icon +
      '</div><div class="empty-text">' + text + '</div>' +
      (hint ? '<div class="empty-hint">' + hint + '</div>' : '') + '</div></div>';
  }
  function pager(totalRows, extra) {
    var totalPages = Math.max(1, Math.ceil(totalRows / PER_PAGE));
    var page = Math.min(state.page, totalPages);
    var html = '<div style="margin-top:12px; display:flex; gap:8px; justify-content:center;">';
    if (page > 1) html += '<a class="btn btn-sm btn-outline" href="' + pageUrl(page - 1, extra) + '">上一页</a>';
    html += '<span style="padding:5px 12px; font-size:13px;">' + page + ' / ' + totalPages +
      '（共 ' + totalRows + ' 条）</span>';
    if (page < totalPages) html += '<a class="btn btn-sm btn-outline" href="' + pageUrl(page + 1, extra) + '">下一页</a>';
    return html + '</div>';
  }
  function pageSlice(rows) {
    var totalPages = Math.max(1, Math.ceil(rows.length / PER_PAGE));
    var page = Math.min(state.page, totalPages);
    return rows.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  }
  function errorCard(msg) {
    return emptyState('⚠️', '数据加载失败', esc(msg) +
      '。若通过 file:// 打开，浏览器会拦截 fetch，请使用本地 HTTP 服务或线上站点。');
  }

  /* ---------------- 环形图 ---------------- */
  function donutSvg(segments, centerLabel) {
    var R = 60, C = 2 * Math.PI * R, offset = 0;
    var circles = '<circle cx="80" cy="80" r="60" fill="none" stroke="var(--tufte-hairline,#e0e0e0)" stroke-width="24"/>';
    segments.forEach(function (s) {
      if (s.value <= 0) return;
      var dash = s.value * C;
      circles += '<circle cx="80" cy="80" r="60" fill="none" stroke="' + s.color +
        '" stroke-width="24" stroke-dasharray="' + dash + ' ' + (C - dash) +
        '" stroke-dashoffset="' + -offset + '" transform="rotate(-90 80 80)"/>';
      offset += dash;
    });
    circles += '<text x="80" y="84" text-anchor="middle" font-size="13" fill="var(--text-secondary)">' +
      centerLabel + '</text>';
    var legend = segments.map(function (s) {
      return '<div><span class="donut-dot" style="background:' + s.color + ';"></span>' +
        s.label + ' ' + Math.round(s.value * 100) + '%</div>';
    }).join('');
    return '<div class="donut-wrap"><svg width="160" height="160" viewBox="0 0 160 160">' + circles +
      '</svg><div class="donut-legend">' + legend + '</div></div>';
  }

  /* ---------------- 页面：总览 ---------------- */
  function renderDashboard(data) {
    var st = data.signal_stats || {};
    var html = '';

    if (st.total > 0) {
      html += '<a href="signals.html?date=' + state.date + '" style="text-decoration:none; color:inherit;">' +
        card('今日信号摘要 <span style="font-size:12px;color:var(--text-secondary);">&rarr;</span>',
          '<div style="display:flex; gap:16px; text-align:center;">' +
          '<div style="flex:1; padding:12px;"><div style="font-size:24px; font-weight:700; color:var(--green);">' + st.buy +
          '</div><div style="font-size:13px; color:var(--text-secondary);">关注买入</div></div>' +
          '<div style="flex:1; padding:12px;"><div style="font-size:24px; font-weight:700; color:var(--gold,#b7950b);">' + st.hold +
          '</div><div style="font-size:13px; color:var(--text-secondary);">继续关注</div></div>' +
          '<div style="flex:1; padding:12px;"><div style="font-size:24px; font-weight:700; color:var(--red);">' + st.sell +
          '</div><div style="font-size:13px; color:var(--text-secondary);">关注卖出</div></div>' +
          '</div>') + '</a>';
    } else {
      html += card('今日信号摘要',
        '<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-text">暂无信号数据</div>' +
        '<div class="empty-hint">数据由 GitHub Actions 每个交易日 22:00 自动更新</div></div>');
    }

    /* 周期 + 持仓配置 */
    var grid = '';
    var ci = data.cycle_info;
    if (ci && ci.weights) {
      var w = ci.weights;
      grid += card('市场周期定位（Dalio 框架）',
        '<div style="display:flex; gap:16px; margin-bottom:20px; text-align:center;">' +
        '<div style="flex:1; padding:10px;"><div style="font-size:13px; color:var(--text-secondary);">当前阶段</div>' +
        '<div style="font-size:16px; font-weight:700; color:var(--accent);">' + esc(ci.phase_label) + '</div></div>' +
        '<div style="flex:1; padding:10px;"><div style="font-size:13px; color:var(--text-secondary);">置信度</div>' +
        '<div style="font-size:16px; font-weight:700;">' + esc(ci.confidence) + '</div></div></div>' +
        donutSvg([
          { value: num(w.return) || 0, color: 'var(--green)', label: '长期回报' },
          { value: num(w.risk) || 0, color: 'var(--red)', label: '风险调整' },
          { value: num(w.stability) || 0, color: 'var(--accent)', label: '稳定性' },
          { value: num(w.quality) || 0, color: 'var(--gold,#b7950b)', label: '质量' },
        ], '因子权重') +
        '<div style="margin-top:12px; font-size:12px; color:var(--text-secondary); line-height:1.6;">' +
        esc(ci.description) + '</div>');
    }
    if (data.holdings && data.holdings.length) {
      grid += card('持仓配置', donutSvg([
        { value: (data.stock_sum || 0) / ((data.stock_sum || 0) + (data.fund_sum || 0) || 1), color: 'var(--accent)', label: '股票' },
        { value: (data.fund_sum || 0) / ((data.stock_sum || 0) + (data.fund_sum || 0) || 1), color: 'var(--green)', label: '基金' },
      ], '配置比例'));
    }
    if (grid) html += '<div class="dashboard-grid">' + grid + '</div>';

    /* 经理 Top5 */
    var tm = data.top_managers || [];
    if (tm.length) {
      var rows = tm.map(function (m) {
        return '<tr><td>' + esc(m['排名']) + '</td><td>' + esc(m['姓名']) + '</td><td>' + esc(m['所属公司']) +
          '</td><td>' + num2(m['管理基金数']) +
          '</td><td style="' + pc(m['平均收益率']) + ';">' + num2(m['平均收益率']) +
          '</td><td style="' + pc(m['最佳收益率']) + ';">' + num2(m['最佳收益率']) + '</td></tr>';
      }).join('');
      html += card('基金经理 Top5 <a href="managers.html?date=' + state.date +
        '" style="float:right;font-size:13px;font-weight:400;">查看全部 →</a>',
        table('<th>排名</th><th>姓名</th><th>所属公司</th><th>管理基金数</th><th>平均收益率(%)</th><th>最佳收益率(%)</th>', rows));
    }
    root.innerHTML = html;
  }

  /* ---------------- 页面：每日信号 ---------------- */
  function renderSignals(data) {
    var rows = data.rows || [];
    if (!rows.length) {
      root.innerHTML = emptyState('📭', '该日期暂无信号数据',
        '换个日期，或等待 GitHub Actions 22:00 自动更新');
      return;
    }
    var types = ['', '关注买入', '关注卖出', '继续关注'];
    var labels = ['全部', '关注买入', '关注卖出', '继续关注'];
    var btns = types.map(function (t, i) {
      var active = (state.type || '') === t;
      return '<button class="btn btn-sm ' + (active ? 'btn-primary' : 'btn-outline') +
        '" data-type="' + esc(t) + '">' + labels[i] + '</button>';
    }).join('');

    var filtered = state.type ? rows.filter(function (r) {
      return r['建议标签(非投资建议)'] === state.type;
    }) : rows;

    var body = pageSlice(filtered).map(function (s) {
      var tag = s['建议标签(非投资建议)'] || '';
      var tagCls = tag.indexOf('买入') >= 0 ? 'tag-buy' :
        (tag.indexOf('卖出') >= 0 ? 'tag-sell' :
          (tag.indexOf('继续') >= 0 ? 'tag-hold' : 'tag-nosig'));
      return '<tr>' +
        '<td><span class="tag ' + (s['资产类型'] === '股票' ? 'tag-stock' : 'tag-fund') + '">' + esc(s['资产类型']) + '</span></td>' +
        '<td>' + esc(s['代码']) + '</td>' +
        '<td>' + esc(s['名称']) + '</td>' +
        '<td>' + esc(s['是否持有']) + '</td>' +
        '<td><span class="tag ' + tagCls + '">' + esc(tag) + '</span></td>' +
        '<td style="' + pc(s['净强度']) + ' font-weight:600;">' + num2(s['净强度']) + '</td>' +
        '<td>' + num2(s['买入强度']) + '</td>' +
        '<td>' + num2(s['卖出强度']) + '</td>' +
        '<td style="font-size:11px; max-width:250px;">' + esc(s['关联经理Top3(净强度)']) + '</td></tr>';
    }).join('');

    root.innerHTML = card('',
      '<div style="display:flex; gap:8px; margin-bottom:12px;" id="sig-filter">' + btns + '</div>' +
      table('<th>资产类型</th><th>代码</th><th>名称</th><th>是否持有</th><th>建议标签</th><th>净强度</th><th>买入强度</th><th>卖出强度</th><th>关联经理</th>', body) +
      pager(filtered.length, { type: state.type || null }));

    document.getElementById('sig-filter').addEventListener('click', function (e) {
      var t = e.target.getAttribute && e.target.getAttribute('data-type');
      if (t === null || t === undefined) return;
      state.type = t;
      setParam('type', t || null);
      renderSignals(data);
    });
  }

  /* ---------------- 页面：我的持仓 ---------------- */
  function renderHoldings(data) {
    var rows = data.rows || [];
    if (!rows.length) {
      root.innerHTML = emptyState('📋', '暂无持仓数据', '运行优化持仓脚本自动生成，或手动创建 out/我的持仓.csv');
      return;
    }
    var maxPct = 0;
    rows.forEach(function (h) { var f = num(h['比例(%)']); if (f !== null && f > maxPct) maxPct = f; });
    var body = rows.map(function (h) {
      var pct = num(h['比例(%)']) || 0;
      var color = h['类型'] === '股票' ? 'var(--accent)' : 'var(--green)';
      return '<tr>' +
        '<td><span class="tag ' + (h['类型'] === '股票' ? 'tag-stock' : 'tag-fund') + '">' + esc(h['类型']) + '</span></td>' +
        '<td>' + esc(h['代码']) + '</td>' +
        '<td>' + esc(h['名称']) + '</td>' +
        '<td style="font-weight:600;">' + num2(pct) + '%</td>' +
        '<td style="width:120px;"><div style="height:8px; background:#e0e0e0; overflow:hidden;">' +
        '<div style="height:100%; width:' + (maxPct > 0 ? pct / maxPct * 100 : 0) + '%; background:' + color + ';"></div>' +
        '</div></td></tr>';
    }).join('');
    root.innerHTML = card('当前持仓配置',
      table('<th>类型</th><th>代码</th><th>名称</th><th>比例(%)</th><th>比例柱</th>', body));
  }

  /* ---------------- 页面：经理排名 ---------------- */
  function renderManagers(data) {
    var rows = data.rows || [];
    if (!rows.length) {
      root.innerHTML = emptyState('🏆', '暂无排名数据', '数据由 GitHub Actions 每个交易日自动更新');
      return;
    }
    var body = pageSlice(rows).map(function (m) {
      return '<tr>' +
        '<td style="font-weight:600;">' + esc(m['排名']) + '</td>' +
        '<td>' + esc(m['姓名']) + '</td>' +
        '<td>' + esc(m['所属公司']) + '</td>' +
        '<td>' + num2(m['管理基金数']) + '</td>' +
        '<td>' + num2(m['有效基金数']) + '</td>' +
        '<td style="' + pc(m['平均收益率']) + ' font-weight:600;">' + num2(m['平均收益率']) + '</td>' +
        '<td>' + num2(m['中位数收益率']) + '</td>' +
        '<td style="color:var(--green);">' + num2(m['最佳收益率']) + '</td>' +
        '<td style="color:var(--red);">' + num2(m['最差收益率']) + '</td></tr>';
    }).join('');
    root.innerHTML = card('',
      '<div style="margin-bottom:12px; color:var(--text-secondary); font-size:13px;">共 ' + rows.length + ' 位经理</div>' +
      table('<th>排名</th><th>姓名</th><th>所属公司</th><th>管理基金数</th><th>有效基金数</th><th>平均收益率</th><th>中位数收益率</th><th>最佳收益率</th><th>最差收益率</th>', body) +
      pager(rows.length));
  }

  /* ---------------- 页面：基金排名 ---------------- */
  function renderFunds(data) {
    var rows = data.rows || [];
    if (!rows.length) {
      root.innerHTML = emptyState('📊', '暂无符合条件的数据');
      return;
    }
    var days = [90, 180, 365, 730, 1095];
    var dayLabels = ['90 天', '180 天', '1 年', '2 年', '3 年'];
    var btns = days.map(function (d, i) {
      return '<button class="btn btn-sm ' + (state.minDays === d ? 'btn-primary' : 'btn-outline') +
        '" data-days="' + d + '">' + dayLabels[i] + '</button>';
    }).join('');

    var filtered = rows.filter(function (r) {
      var f = num(r['成立天数']);
      return f !== null && f >= state.minDays;
    });

    var body = pageSlice(filtered).map(function (f) {
      return '<tr>' +
        '<td style="font-weight:600;">' + esc(f['排名']) + '</td>' +
        '<td>' + esc(f['基金代码']) + '</td>' +
        '<td>' + esc(f['基金简称']) + '</td>' +
        '<td style="' + pc(f['成立来年化']) + ' font-weight:600;">' + num2(f['成立来年化']) + '</td>' +
        '<td>' + num2(f['成立来']) + '</td>' +
        '<td>' + num2(f['成立天数']) + '</td>' +
        '<td style="' + pc(f['近1年']) + ';">' + num2(f['近1年']) + '</td>' +
        '<td>' + num2(f['近2年']) + '</td>' +
        '<td>' + num2(f['近3年']) + '</td>' +
        '<td>' + num2(f['今年来']) + '</td></tr>';
    }).join('');

    root.innerHTML = card('',
      '<div style="display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap; align-items:center;" id="funds-filter">' +
      '<span style="font-size:13px; color:var(--text-secondary);">成立天数 &ge;</span>' + btns +
      '<span style="font-size:13px; color:var(--text-secondary); margin-left:16px;">共 ' + filtered.length +
      ' 只基金' + (data.max_rows && rows.length >= data.max_rows ? '（仅展示前 ' + data.max_rows + ' 名）' : '') + '</span></div>' +
      table('<th>排名</th><th>基金代码</th><th>基金简称</th><th>成立来年化</th><th>成立来</th><th>成立天数</th><th>近1年</th><th>近2年</th><th>近3年</th><th>今年来</th>', body) +
      pager(filtered.length, { min_days: String(state.minDays) }));

    document.getElementById('funds-filter').addEventListener('click', function (e) {
      var d = e.target.getAttribute && e.target.getAttribute('data-days');
      if (!d) return;
      state.minDays = parseInt(d, 10);
      setParam('min_days', d);
      renderFunds(data);
    });
  }

  /* ---------------- 页面：绩优标的 ---------------- */
  function renderElite(data) {
    var ef = data.funds || [], es = data.stocks || [];
    var fundRows = ef.map(function (f) {
      return '<tr>' +
        '<td>' + esc(f['经理排名']) + '</td><td>' + esc(f['姓名']) + '</td><td>' + esc(f['所属公司']) + '</td>' +
        '<td>' + esc(f['基金代码']) + '</td><td>' + esc(f['基金简称']) + '</td>' +
        '<td style="' + pc(f['成立来年化']) + ' font-weight:600;">' + num2(f['成立来年化']) + '</td>' +
        '<td>' + num2(f['成立来']) + '</td><td>' + num2(f['近1年']) + '</td></tr>';
    }).join('');
    var stockRows = es.map(function (s) {
      return '<tr>' +
        '<td>' + esc(s['经理排名']) + '</td><td>' + esc(s['姓名']) + '</td><td>' + esc(s['所属公司']) + '</td>' +
        '<td>' + esc(s['股票代码']) + '</td><td>' + esc(s['股票名称']) + '</td>' +
        '<td style="font-weight:600;">' + num2(s['汇总占净值比例']) + '</td>' +
        '<td>' + num2(s['出现基金数']) + '</td><td>' + esc(s['最新季度']) + '</td></tr>';
    }).join('');

    root.innerHTML = card('',
      '<div class="tabs">' +
      '<button class="tab-btn active" id="tab-btn-funds">基金 Top3</button>' +
      '<button class="tab-btn" id="tab-btn-stocks">股票 Top10</button></div>' +
      '<div id="tab-funds" class="tab-panel active">' +
      (ef.length ? table('<th>经理排名</th><th>姓名</th><th>所属公司</th><th>基金代码</th><th>基金简称</th><th>成立来年化</th><th>成立来</th><th>近1年</th>', fundRows, 'elite-table')
        : '<div class="empty-state"><div class="empty-icon">📊</div><div class="empty-text">暂无绩优基金数据</div></div>') +
      '</div>' +
      '<div id="tab-stocks" class="tab-panel">' +
      (es.length ? table('<th>经理排名</th><th>姓名</th><th>所属公司</th><th>股票代码</th><th>股票名称</th><th>汇总占净值比例</th><th>出现基金数</th><th>最新季度</th>', stockRows, 'elite-table')
        : '<div class="empty-state"><div class="empty-icon">📊</div><div class="empty-text">暂无绩优股票数据</div></div>') +
      '</div>');

    function tab(name) {
      document.getElementById('tab-btn-funds').classList.toggle('active', name === 'funds');
      document.getElementById('tab-btn-stocks').classList.toggle('active', name === 'stocks');
      document.getElementById('tab-funds').classList.toggle('active', name === 'funds');
      document.getElementById('tab-stocks').classList.toggle('active', name === 'stocks');
    }
    document.getElementById('tab-btn-funds').addEventListener('click', function () { tab('funds'); });
    document.getElementById('tab-btn-stocks').addEventListener('click', function () { tab('stocks'); });
  }

  /* ---------------- 页面：回测 ---------------- */
  function renderBacktest(data) {
    var results = data.results || [];
    if (!results.length) {
      root.innerHTML = emptyState('📈', '该日期暂无回测结果', '回测由本地或 CI 运行生成');
      return;
    }
    var current = results.filter(function (r) { return r.id === state.view; })[0] || results[0];

    var list = results.map(function (r) {
      return '<a href="backtest.html?date=' + state.date + '&view=' + encodeURIComponent(r.id) +
        '" class="backtest-record ' + (r.id === current.id ? 'active' : '') + '">' +
        '<span style="font-size:13px;">' + (r.id.indexOf('fund') === 0 ? '基金回测' : '股票回测') + '</span>' +
        '<span style="font-size:11px; color:var(--text-secondary);">' + esc(r.stamp) + '</span>' +
        (r.chart ? '<span style="font-size:11px; color:var(--green);">含图表</span>' : '') +
        '</a>';
    }).join('');

    var detail = '';
    if (current.summary_html) {
      detail += card('回测摘要',
        '<div class="md-content" id="summary-content">' + current.summary_html + '</div>');
    }
    if (current.chart) {
      detail += card('回测图表',
        '<img src="charts/' + encodeURIComponent(current.chart) + '" class="backtest-chart" alt="回测图表">');
    }
    if (!detail) detail = '<div class="card"><div class="empty-state"><div class="empty-text">该回测无摘要与图表</div></div></div>';

    root.innerHTML = '<div class="backtest-layout">' +
      '<div class="card" style="height:fit-content;"><div class="card-header">回测记录</div>' + list + '</div>' +
      '<div>' + detail + '</div></div>';
  }

  /* ---------------- 启动 ---------------- */
  function run() {
    getJSON('data/manifest.json')
      .then(function (manifest) {
        buildHeader(manifest);
        if (PAGE === 'pipeline') return; /* 静态壳自带内容 */

        if (!state.date) {
          root.innerHTML = emptyState('📭', '暂无数据', '数据由 GitHub Actions 每个交易日 22:00 自动生成');
          return;
        }

        var loaders = {
          dashboard: function () {
            return getJSON('data/' + state.date + '/dashboard.json').then(renderDashboard);
          },
          signals: function () {
            return getJSON('data/' + state.date + '/signals.json').then(renderSignals);
          },
          holdings: function () {
            return getJSON('data/holdings.json').then(renderHoldings);
          },
          managers: function () {
            return getJSON('data/' + state.date + '/managers.json').then(renderManagers);
          },
          funds: function () {
            return getJSON('data/' + state.date + '/funds.json').then(renderFunds);
          },
          elite: function () {
            return getJSON('data/' + state.date + '/elite.json').then(renderElite);
          },
          backtest: function () {
            return getJSON('data/' + state.date + '/backtest.json').then(renderBacktest);
          },
        };

        return (loaders[PAGE] || function () {
          root.innerHTML = '';
        })();
      })
      .catch(function (err) {
        console.error(err);
        root.innerHTML = errorCard(err.message || err);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();

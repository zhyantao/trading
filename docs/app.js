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
    name: params.get('name') || '',   /* 基金经理个人页 */
    minDays: parseInt(params.get('min_days') || '180', 10) || 180,
    minMgr: Math.max(1, parseInt(params.get('min_mgr') || '1', 10) || 1),
  };

  /* ---------------- 工具 ---------------- */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
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
  /* ---------------- 外链：天天基金 / 雪球 ---------------- */
  function stockPrefix(code) {
    var c = String(code || '');
    if (/^(6|9)/.test(c)) return 'SH';
    if (/^(0|2|3)/.test(c)) return 'SZ';
    if (/^(4|8)/.test(c)) return 'BJ';
    return '';
  }
  function codeLink(type, code) {
    if (!code) return '';
    var url;
    if (type === '股票') {
      /* 只有 6 位纯数字的 A 股代码才能生成雪球链接；美股/港股代码原样显示 */
      if (!/^\d{6}$/.test(String(code))) return esc(code);
      var p = stockPrefix(code);
      if (!p) return esc(code);
      url = 'https://xueqiu.com/S/' + p + code;
    } else {
      url = 'https://fund.eastmoney.com/' + code + '.html';
    }
    return '<a class="code-link" href="' + url + '" target="_blank" rel="noopener noreferrer" title="查看行情">' +
      esc(code) + '</a>';
  }

  /* ---------------- 基金经理个人页 ----------------
     后端把「关联经理」拼成纯文本（信号列：姓名(公司):数值; …，股票列：
     姓名、姓名 等 N 位）。这里把它拆成逐条经理链接，配合 .mgr-cell 的
     自动换行，避免长文本把表格撑出卡片边界。 */
  function managerUrl(name) {
    return 'manager.html?date=' + encodeURIComponent(state.date) +
      '&name=' + encodeURIComponent(name);
  }
  function managerLink(name, title) {
    return '<a class="mgr-link" href="' + managerUrl(name) + '" title="' +
      esc(title || ('查看 ' + name + ' 的个人页面')) + '">' + esc(name) + '</a>';
  }
  function managerCell(text) {
    var raw = String(text == null ? '' : text).trim();
    if (!raw) return '<td class="mgr-cell">—</td>';
    var items = [];
    raw.split(/\s*;\s*/).forEach(function (part) {
      var p = part.trim();
      if (!p) return;
      /* "等 N 位" 单独成行，不作为经理名字 */
      var more = '';
      var mMore = p.match(/\s*等\s*\d+\s*位\s*$/);
      if (mMore) {
        more = mMore[0].trim();
        p = p.slice(0, p.length - mMore[0].length).trim();
      }
      var entries = p.indexOf('、') >= 0 ? p.split(/\s*、\s*/) : [p];
      entries.forEach(function (entry) {
        var e = entry.trim();
        if (!e) return;
        /* 信号列：姓名(所属公司):净强度 / 姓名(所属公司) 经理排名=N */
        var m = e.match(/^([^()]+?)\(([^)]*)\)\s*(.*)$/);
        if (m && m[1].trim()) {
          var meta = [m[2].trim(), m[3].replace(/^[:：]\s*/, '').trim()]
            .filter(Boolean).join(' · ');
          items.push('<div class="mgr-item">' + managerLink(m[1].trim()) +
            (meta ? '<span class="mgr-meta">' + esc(meta) + '</span>' : '') + '</div>');
        } else if (/^[^()：:；;、\s]{2,12}$/.test(e)) {
          /* 股票列：纯姓名 */
          items.push('<div class="mgr-item">' + managerLink(e) + '</div>');
        } else {
          /* 无法识别的片段保持纯文本，避免生成错误链接 */
          items.push('<div class="mgr-item">' + esc(e) + '</div>');
        }
      });
      if (more) items.push('<div class="mgr-item mgr-more">' + esc(more) + '</div>');
    });
    return '<td class="mgr-cell">' + items.join('') + '</td>';
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
  /* GitHub Pages / 浏览器会缓存 JSON（Cache-Control: max-age=600）。
     若不加版本参数，数据更新后 manifest.json 可能仍是旧内容，日期下拉就会
     继续列出已删除的历史日期。http(s) 下给请求加版本参数并禁用 manifest 缓存；
     file:// 本地预览保持原样（带 query 的 file URL 反而读不到文件）。 */
  var BUST_CACHE = /^https?:$/.test(location.protocol || '');
  var DATA_VERSION = '';
  function dataUrl(url) {
    if (!BUST_CACHE) return url;
    var isManifest = url.indexOf('manifest.json') >= 0;
    var v = isManifest ? 't' + Date.now() : 'd' + (DATA_VERSION || 'init');
    return url + (url.indexOf('?') < 0 ? '?' : '&') + 'v=' + encodeURIComponent(v);
  }
  function getJSON(url) {
    var key = dataUrl(url);
    if (_cache[key]) return _cache[key];
    /* manifest 必须每次回源；数据文件带版本号后可由浏览器正常缓存 */
    var opts = BUST_CACHE
      ? { cache: url.indexOf('manifest.json') >= 0 ? 'no-store' : 'default' }
      : undefined;
    _cache[key] = fetch(key, opts).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url);
      return r.json();
    });
    return _cache[key];
  }

  /* ---------------- 页眉（站点导航 + 应用导航） ---------------- */
  function navLink(href, page, label, date) {
    /* 经理个人页归属在「经理排名」栏目下 */
    var active = PAGE === page || (page === 'managers' && PAGE === 'manager');
    return '<a href="' + href + '?date=' + date + '" class="' +
      (active ? 'active' : '') + '">' + label + '</a>';
  }

  function buildHeader(manifest) {
    var dates = manifest.dates || [];
    if (!state.date || dates.indexOf(state.date) < 0) state.date = manifest.latest || dates[0] || '';
    /* URL / 书签里残留的过期日期参数一并纠正，避免继续指向已删除的旧数据。
       file:// 下 replaceState 可能因 null origin 抛错，本地预览时不动 URL。 */
    if (BUST_CACHE && params.get('date') && params.get('date') !== state.date) {
      setParam('date', state.date);
    }

    /* 站上只保留最新一天的数据，因此不再提供日期下拉；URL 中的旧日期由上面统一纠正 */
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
      navLink('stocks.html', 'stocks', '股票排名', state.date) +
      navLink('elite.html', 'elite', '绩优标的', state.date) +
      navLink('backtest.html', 'backtest', '回测', state.date) +
      navLink('formulas.html', 'formulas', '公式', state.date) +
      navLink('pipeline.html', 'pipeline', '流水线', state.date) +
      '</div>' +
      '<div class="nav-actions">' +
      '<button id="ci-run" class="btn btn-sm btn-outline ci-btn" title="打开 GitHub Actions 手动运行数据更新">' +
      '&#10227; 更新数据</button>' +
      '<span id="ci-status" class="ci-status" title="最近一次数据更新（GitHub Actions）"></span>' +
      '<label for="nav-toggle" class="nav-toggle-btn" aria-label="菜单"><span></span><span></span><span></span></label>' +
      '</div></div></nav>';

    /* 数据更新按钮：打开 Actions 触发页 + 显示最近一次运行状态 */
    var runBtn = document.getElementById('ci-run');
    if (runBtn) runBtn.addEventListener('click', function () {
      window.open('https://github.com/zhyantao/trading/actions/workflows/update.yml', '_blank');
    });
    refreshCiStatus();
    setInterval(refreshCiStatus, 60 * 1000);
  }

  function refreshCiStatus() {
    var el = document.getElementById('ci-status');
    if (!el) return;
    fetch('https://api.github.com/repos/zhyantao/trading/actions/workflows/update.yml/runs?per_page=1')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var run = d && d.workflow_runs && d.workflow_runs[0];
        if (!run) { el.textContent = ''; return; }
        var when = new Date(run.created_at).toLocaleString('zh-CN', {
          month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
        });
        if (run.status === 'completed') {
          el.textContent = (run.conclusion === 'success' ? '✓ ' : '✗ ') + when;
          el.className = 'ci-status ' + (run.conclusion === 'success' ? 'ok' : 'fail');
        } else {
          el.textContent = '⟳ 更新中';
          el.className = 'ci-status running';
        }
      })
      .catch(function () { el.textContent = ''; });
  }

  /* ---------------- 通用渲染 ---------------- */
  function table(headersHtml, rowsHtml, extraCls) {
    return '<div class="table-wrap"><table class="' + (extraCls || '') + '">' +
      '<thead><tr>' + headersHtml + '</tr></thead><tbody>' + rowsHtml +
      '</tbody></table></div>';
  }
  function card(title, inner, extraCls) {
    return '<div class="card ' + (extraCls || '') + '">' +
      (title ? '<div class="card-header">' + title + '</div>' : '') +
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
    circles += '<text x="80" y="86" text-anchor="middle" font-size="20" fill="var(--text-secondary)">' +
      centerLabel + '</text>';
    var legend = segments.map(function (s) {
      return '<div><span class="donut-dot" style="background:' + s.color + ';"></span>' +
        s.label + ' ' + Math.round(s.value * 100) + '%</div>';
    }).join('');
    /* 视图坐标仍为 160×160，实际显示尺寸压到 92px，避免环形图挤占整页 */
    return '<div class="donut-wrap"><svg width="92" height="92" viewBox="0 0 160 160">' + circles +
      '</svg><div class="donut-legend">' + legend + '</div></div>';
  }

  /* ---------------- 页面：总览 ---------------- */
  /* 紧凑布局：环形图缩到 92px，两个 Top5 榜单并排，避免大图把表格挤到下方 */
  function renderDashboard(data) {
    var st = data.signal_stats || {};
    var html = '';

    if (st.total > 0) {
      html += '<a href="signals.html?date=' + state.date + '" style="text-decoration:none; color:inherit;">' +
        card('今日信号摘要 <span style="font-size:12px;color:var(--text-secondary);">&rarr;</span>',
          '<div class="stat-strip">' +
          '<div><div class="stat-num" style="color:var(--green);">' + st.buy +
          '</div><div class="stat-label">关注买入</div></div>' +
          '<div><div class="stat-num" style="color:var(--yellow);">' + st.hold +
          '</div><div class="stat-label">继续关注</div></div>' +
          '<div><div class="stat-num" style="color:var(--red);">' + st.sell +
          '</div><div class="stat-label">关注卖出</div></div>' +
          '</div>', 'card-compact') + '</a>';
    } else {
      html += card('今日信号摘要',
        '<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-text">暂无信号数据</div>' +
        '<div class="empty-hint">数据由 GitHub Actions 每个交易日 22:00 自动更新</div></div>',
        'card-compact');
    }

    /* 周期 + 持仓配置：两张小图并排 */
    var grid = '';
    var ci = data.cycle_info;
    if (ci && ci.weights) {
      var w = ci.weights;
      grid += card('市场周期定位（Dalio 框架）',
        '<div class="stat-strip" style="margin-bottom:8px;">' +
        '<div><div class="stat-label">当前阶段</div>' +
        '<div style="font-size:15px;font-weight:700;color:var(--accent);">' + esc(ci.phase_label) + '</div></div>' +
        '<div><div class="stat-label">置信度</div>' +
        '<div style="font-size:15px;font-weight:700;">' + esc(ci.confidence) + '</div></div></div>' +
        donutSvg([
          { value: num(w.return) || 0, color: 'var(--green)', label: '长期回报' },
          { value: num(w.risk) || 0, color: 'var(--red)', label: '风险调整' },
          { value: num(w.stability) || 0, color: 'var(--accent)', label: '稳定性' },
          { value: num(w.quality) || 0, color: 'var(--yellow)', label: '质量' },
        ], '权重') +
        '<div style="margin-top:8px;font-size:12px;color:var(--text-secondary);line-height:1.5;">' +
        esc(ci.description) + '</div>', 'card-compact');
    }
    if (data.holdings && data.holdings.length) {
      var hrows = data.holdings.map(function (h) {
        return '<tr><td>' + codeLink(h['类型'], h['代码']) + '</td><td>' + esc(h['名称']) +
          '</td><td>' + num2(h['比例(%)']) + '</td></tr>';
      }).join('');
      grid += card('持仓配置', donutSvg([
        { value: (data.stock_sum || 0) / ((data.stock_sum || 0) + (data.fund_sum || 0) || 1), color: 'var(--accent)', label: '股票' },
        { value: (data.fund_sum || 0) / ((data.stock_sum || 0) + (data.fund_sum || 0) || 1), color: 'var(--green)', label: '基金' },
      ], '比例') +
        (hrows ? table('<th>代码</th><th>名称</th><th>比例(%)</th>', hrows, 'mini-table') : ''),
        'card-compact');
    }
    if (grid) html += '<div class="dashboard-grid">' + grid + '</div>';

    /* 股票排名 Top5 + 经理 Top5：并排放在下方 */
    var lower = '';
    var ts = data.top_stocks || [];
    if (ts.length) {
      var srows = ts.map(function (s) {
        return '<tr><td>' + esc(s['排名']) + '</td><td>' + codeLink('股票', s['股票代码']) + '</td>' +
          '<td>' + esc(s['股票名称']) + '</td><td>' + esc(s['入选经理数']) + '</td>' +
          '<td style="font-weight:600;color:var(--accent);">' + num2(s['综合得分']) + '</td></tr>';
      }).join('');
      lower += card('股票排名 Top5 <a class="card-link" href="stocks.html?date=' + state.date +
        '">查看全部 →</a>',
        '<p class="rank-mini-note">按综合得分 S<sub>s</sub>（共识度/覆盖/仓位/名次/经理质量）排序，共 ' +
        esc(data.stock_count || ts.length) + ' 只 · <a href="formulas.html">评分公式</a></p>' +
        table('<th>排名</th><th>代码</th><th>名称</th><th>入选经理</th><th>综合得分</th>', srows, 'mini-table'),
        'card-compact');
    }
    var tm = data.top_managers || [];
    if (tm.length) {
      var mrows = tm.map(function (m) {
        return '<tr><td>' + esc(m['排名']) + '</td><td>' + esc(m['姓名']) + '</td><td>' + esc(m['所属公司']) +
          '</td><td>' + num2(m['管理基金数']) +
          '</td><td style="' + pc(m['平均收益率']) + ';">' + num2(m['平均收益率']) +
          '</td><td style="' + pc(m['最佳收益率']) + ';">' + num2(m['最佳收益率']) + '</td></tr>';
      }).join('');
      lower += card('基金经理 Top5 <a class="card-link" href="managers.html?date=' + state.date +
        '">查看全部 →</a>',
        table('<th>排名</th><th>姓名</th><th>所属公司</th><th>管理基金数</th><th>平均收益率(%)</th><th>最佳收益率(%)</th>',
          mrows, 'mini-table'), 'card-compact');
    }
    if (lower) html += '<div class="dashboard-grid">' + lower + '</div>';
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
        '<td>' + codeLink(s['资产类型'], s['代码']) + '</td>' +
        '<td>' + esc(s['名称']) + '</td>' +
        '<td>' + esc(s['是否持有']) + '</td>' +
        '<td><span class="tag ' + tagCls + '">' + esc(tag) + '</span></td>' +
        '<td style="' + pc(s['净强度']) + ' font-weight:600;">' + num2(s['净强度']) + '</td>' +
        '<td>' + num2(s['买入强度']) + '</td>' +
        '<td>' + num2(s['卖出强度']) + '</td>' +
        managerCell(s['关联经理Top3(净强度)']) + '</tr>';
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
        '<td>' + codeLink(h['类型'], h['代码']) + '</td>' +
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
        '<td>' + managerLink(m['姓名']) + '</td>' +
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

  /* ---------------- 页面：基金经理个人页 ---------------- */
  /* 数据来自 manager_index.json：按姓名聚合排名 / 绩优基金 / 重仓股 / 调仓信号 */
  function renderManager(index) {
    var name = (state.name || '').trim();
    var crumb = '<p class="mgr-crumb">' +
      '<a href="signals.html?date=' + state.date + '">← 每日信号</a> · ' +
      '<a href="managers.html?date=' + state.date + '">经理排名</a> · ' +
      '<a href="stocks.html?date=' + state.date + '">股票排名</a> · ' +
      '<a href="elite.html?date=' + state.date + '">绩优标的</a></p>';
    if (!name) {
      root.innerHTML = crumb + emptyState('🔍', '未指定基金经理',
        '请从「关联经理」列点选经理姓名，或前往经理排名页');
      return;
    }
    var m = (index.managers || {})[name] || null;
    var rank = (m && m.ranks && m.ranks[0]) || {};
    var company = (m && m['所属公司']) || rank['所属公司'] || '';
    function stat(label, value, style) {
      return '<div class="mgr-stat"><div class="k">' + esc(label) + '</div>' +
        '<div class="v" style="' + (style || '') + '">' + value + '</div></div>';
    }
    var html = crumb +
      '<div class="mgr-hero"><h1>' + esc(name) + '</h1>' +
      (company ? '<span class="mgr-company">' + esc(company) + '</span>' : '') + '</div>' +
      '<p class="mgr-note">资料由本站流水线从公开的基金季度持仓、基金业绩与经理排名聚合而成，' +
      '仅作研究记录，不构成投资建议。</p>' +
      '<div class="mgr-ext">' +
      '<a class="btn btn-sm btn-outline" href="https://so.eastmoney.com/web/s?keyword=' +
      encodeURIComponent(name) + '" target="_blank" rel="noopener noreferrer">东方财富搜索该经理 ↗</a>' +
      '<a class="btn btn-sm btn-outline" href="https://www.baidu.com/s?wd=' +
      encodeURIComponent(name + ' 基金经理') + '" target="_blank" rel="noopener noreferrer">百度搜索 ↗</a>' +
      '<a class="btn btn-sm btn-outline" href="https://fund.eastmoney.com/manager/" ' +
      'target="_blank" rel="noopener noreferrer">天天基金经理大全 ↗</a></div>';

    if (rank && rank['排名']) {
      html += '<h2 class="mgr-section-title">业绩排名 <span style="font-size:12px;font-weight:400;' +
        'color:var(--text-secondary);">口径：' + esc(rank['排名指标'] || '') + '</span></h2>' +
        '<div class="mgr-stats">' +
        stat('排名', '#' + esc(rank['排名'])) +
        stat('平均收益率', num2(rank['平均收益率']) + '%', pc(rank['平均收益率'])) +
        stat('中位数收益率', num2(rank['中位数收益率']) + '%', pc(rank['中位数收益率'])) +
        stat('最佳收益率', num2(rank['最佳收益率']) + '%', 'color:var(--green);') +
        stat('最差收益率', num2(rank['最差收益率']) + '%', 'color:var(--red);') +
        stat('管理 / 有效基金', esc(rank['管理基金数']) + ' / ' + esc(rank['有效基金数'])) +
        '</div>';
    }

    var funds = (m && m.funds) || [], stocks = (m && m.stocks) || [], signals = (m && m.signals) || [];
    if (funds.length) {
      var frows = funds.map(function (f) {
        return '<tr><td>' + esc(f['基金Top']) + '</td><td>' + codeLink('基金', f['基金代码']) + '</td>' +
          '<td>' + esc(f['基金简称']) + '</td><td>' + esc(f['基金年化排名']) + '</td>' +
          '<td style="' + pc(f['成立来年化']) + ';">' + num2(f['成立来年化']) + '%</td>' +
          '<td style="' + pc(f['近1年']) + ';">' + num2(f['近1年']) + '%</td>' +
          '<td>' + esc(f['成立天数']) + '</td></tr>';
      }).join('');
      html += '<h2 class="mgr-section-title">绩优基金 Top3（' + funds.length + '）</h2>' +
        table('<th>名次</th><th>基金代码</th><th>基金简称</th><th>年化排名</th><th>成立来年化(%)</th><th>近1年(%)</th><th>成立天数</th>', frows);
    }
    if (stocks.length) {
      var krows = stocks.map(function (s) {
        return '<tr><td>' + esc(s['股票Top']) + '</td><td>' + codeLink('股票', s['股票代码']) + '</td>' +
          '<td>' + esc(s['股票名称']) + '</td><td>' + num2(s['汇总占净值比例']) + '%</td>' +
          '<td>' + esc(s['出现基金数']) + '</td><td>' + esc(s['最新季度']) + '</td>' +
          '<td class="mgr-cell">' + esc(s['Top3基金列表']) + '</td></tr>';
      }).join('');
      html += '<h2 class="mgr-section-title">重仓股票 Top10（' + stocks.length + '）</h2>' +
        table('<th>名次</th><th>股票代码</th><th>股票名称</th><th>汇总占净值比例(%)</th><th>出现基金数</th><th>最新季度</th><th>Top3 基金</th>', krows);
    }
    if (signals.length) {
      var grows = signals.map(function (g) {
        return '<tr><td>' + esc(g['资产类型']) + '</td><td>' + codeLink(g['资产类型'], g['代码']) + '</td>' +
          '<td>' + esc(g['名称']) + '</td><td>' + esc(g['建议标签(非投资建议)']) + '</td>' +
          '<td style="' + pc(g['净强度']) + ';">' + num2(g['净强度']) + '</td>' +
          managerCell(g['关联经理Top3(净强度)']) + '</tr>';
      }).join('');
      html += '<h2 class="mgr-section-title">相关每日信号（' + signals.length + '）</h2>' +
        table('<th>资产类型</th><th>代码</th><th>名称</th><th>建议标签</th><th>净强度</th><th>关联经理</th>', grows);
    }
    if (!funds.length && !stocks.length && !signals.length) {
      html += '<p class="mgr-note">该经理暂未出现在当前日期的绩优标的与调仓信号中，' +
        '可在 <a href="managers.html?date=' + state.date + '">经理排名</a> 查看其业绩指标。</p>';
    }
    root.innerHTML = html;
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
        '<td>' + codeLink('基金', f['基金代码']) + '</td>' +
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

  /* ---------------- 页面：股票排名 ---------------- */
  /* 数据由「每位绩优经理的股票 Top10」去重聚合，按形式化综合得分 S_s 排序 */
  function renderStocks(data) {
    var rows = data.rows || [];
    if (!rows.length) {
      root.innerHTML = emptyState('🏆', '暂无股票排名数据', '请先运行流水线生成绩优经理标的');
      return;
    }
    var levels = [1, 2, 3, 5];
    var labels = ['全部', '≥2 位经理', '≥3 位经理', '≥5 位经理'];
    var btns = levels.map(function (m, i) {
      return '<button class="btn btn-sm ' + (state.minMgr === m ? 'btn-primary' : 'btn-outline') +
        '" data-mgr="' + m + '">' + labels[i] + '</button>';
    }).join('');
    var filtered = rows.filter(function (r) { return num(r['入选经理数']) >= state.minMgr; });
    var body = pageSlice(filtered).map(function (r) {
      return '<tr>' +
        '<td style="font-weight:600;">' + esc(r['排名']) + '</td>' +
        '<td style="font-weight:600;color:var(--accent);">' + num2(r['综合得分']) + '</td>' +
        '<td>' + codeLink('股票', r['股票代码']) + '</td>' +
        '<td>' + esc(r['股票名称']) + '</td>' +
        '<td style="font-weight:600;">' + esc(r['入选经理数']) + '</td>' +
        '<td>' + esc(r['出现基金数']) + '</td>' +
        '<td>' + num2(r['平均占净值比例']) + '</td>' +
        '<td>' + esc(r['最高名次']) + '</td>' +
        managerCell(r['关联经理']) +
        '<td>' + esc(r['最新季度']) + '</td></tr>';
    }).join('');

    root.innerHTML = card('',
      '<p class="rank-note">由 ' + esc(data.manager_count) + ' 位绩优经理各自的股票 Top10（共 ' +
      esc(data.record_count) + ' 条）去重汇总，按形式化综合得分 S<sub>s</sub> 降序排列（共识度 / 覆盖基金数 / 平均占净值比例 / 最好名次 / 经理质量），' +
      '<a href="formulas.html">查看评分公式 →</a>。共 ' + esc(data.stock_count) + ' 只股票</p>' +
      '<div style="display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap; align-items:center;" id="stocks-filter">' +
      '<span style="font-size:13px; color:var(--text-secondary);">入选经理数 &ge;</span>' + btns +
      '<span style="font-size:13px; color:var(--text-secondary); margin-left:16px;">筛选出 ' + filtered.length + ' 只股票</span></div>' +
      (filtered.length
        ? table('<th>排名</th><th>综合得分</th><th>股票代码</th><th>股票名称</th><th>入选经理数</th><th>出现基金数</th><th>平均占净值比例(%)</th><th>最高名次</th><th>关联经理</th><th>最新季度</th>', body)
        : '<div class="empty-state"><div class="empty-icon">🏆</div><div class="empty-text">没有符合条件的股票</div></div>') +
      pager(filtered.length, { min_mgr: String(state.minMgr) }));

    document.getElementById('stocks-filter').addEventListener('click', function (e) {
      var m = e.target.getAttribute && e.target.getAttribute('data-mgr');
      if (!m) return;
      state.minMgr = parseInt(m, 10);
      state.page = 1;
      setParam('min_mgr', m);
      setParam('page', null);
      renderStocks(data);
    });
  }

  /* ---------------- 页面：绩优标的 ---------------- */
  /* 后端已按 S_f / S_s 综合所有经理算出唯一榜单：固定 3 只基金 / 10 只股票。
     完整候选池（按经理分组）仍可在「股票排名 / 基金排名」页查看。 */
  function renderElite(data) {
    var ef = data.funds || [], es = data.stocks || [];
    var fundHead = '<th>排名</th><th>综合得分</th><th>基金代码</th><th>基金简称</th><th>入选经理数</th>' +
      '<th>首选经理</th><th>成立来年化</th><th>近1年</th><th>成立天数</th>';
    var stockHead = '<th>排名</th><th>综合得分</th><th>股票代码</th><th>股票名称</th><th>入选经理数</th>' +
      '<th>出现基金数</th><th>平均占净值比例(%)</th><th>最高名次</th><th>关联经理</th><th>最新季度</th>';
    var fundRows = ef.map(function (f) {
      return '<tr>' +
        '<td style="font-weight:600;">' + esc(f['基金排名']) + '</td>' +
        '<td style="font-weight:600;color:var(--accent);">' + num2(f['综合得分']) + '</td>' +
        '<td>' + codeLink('基金', f['基金代码']) + '</td><td>' + esc(f['基金简称']) + '</td>' +
        '<td>' + esc(f['入选经理数']) + '</td>' +
        '<td>' + managerLink(f['姓名']) + ' <span style="font-size:11px;color:var(--text-secondary);">' +
        esc(f['经理排名']) + '</span></td>' +
        '<td style="' + pc(f['成立来年化']) + ';">' + num2(f['成立来年化']) + '</td>' +
        '<td style="' + pc(f['近1年']) + ';">' + num2(f['近1年']) + '</td>' +
        '<td>' + num2(f['成立天数']) + '</td></tr>';
    }).join('');
    var stockRows = es.map(function (s) {
      return '<tr>' +
        '<td style="font-weight:600;">' + esc(s['排名']) + '</td>' +
        '<td style="font-weight:600;color:var(--accent);">' + num2(s['综合得分']) + '</td>' +
        '<td>' + codeLink('股票', s['股票代码']) + '</td><td>' + esc(s['股票名称']) + '</td>' +
        '<td>' + esc(s['入选经理数']) + '</td><td>' + esc(s['出现基金数']) + '</td>' +
        '<td>' + num2(s['平均占净值比例']) + '</td><td>' + esc(s['最高名次']) + '</td>' +
        managerCell(s['关联经理']) +
        '<td>' + esc(s['最新季度']) + '</td></tr>';
    }).join('');

    var scope = '<p class="elite-scope">共 ' + esc(data.manager_count || 0) + ' 位绩优经理、' +
      esc(data.candidate_funds || ef.length) + ' 条基金候选 / ' +
      esc(data.candidate_stocks || es.length) + ' 条股票候选，' +
      '按形式化综合得分跨经理统一排序，<b>全站只选 ' + esc(data.top_funds || 3) +
      ' 只基金 / ' + esc(data.top_stocks || 10) + ' 只股票</b>（不是每位经理各 3 / 10 条）。' +
      '<a href="formulas.html">查看评分公式 →</a> · ' +
      '<a href="stocks.html?date=' + state.date + '">完整股票排名 →</a></p>';

    root.innerHTML = card('',
      scope +
      '<div class="tabs">' +
      '<button class="tab-btn active" id="tab-btn-funds">基金 Top3</button>' +
      '<button class="tab-btn" id="tab-btn-stocks">股票 Top10</button></div>' +
      '<div id="tab-funds" class="tab-panel active">' +
      (ef.length ? table(fundHead, fundRows, 'elite-table')
        : '<div class="empty-state"><div class="empty-icon">📊</div><div class="empty-text">暂无绩优基金数据</div></div>') +
      '</div>' +
      '<div id="tab-stocks" class="tab-panel">' +
      (es.length ? table(stockHead, stockRows, 'elite-table')
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

  /* ---------------- 回测：汇总在上、逐笔明细在下 ---------------- */
  /* 摘要 md 转成的 HTML 里汇总指标与「交易明细」混在一起，这里按 h2 拆开重排 */
  function splitBacktestSummary(html) {
    var intro = '', sections = [];
    var re = /<h2>([\s\S]*?)<\/h2>([\s\S]*?)(?=<h2>|$)/g;
    var m;
    while ((m = re.exec(html)) !== null) {
      if (!intro && !sections.length) intro = html.slice(0, m.index);
      sections.push({ title: m[1].replace(/<[^>]+>/g, '').trim(), body: m[0] });
    }
    if (!sections.length) intro = html;
    var summary = intro, trades = '', notes = '';
    sections.forEach(function (s) {
      if (/交易明细|逐笔|交易记录/.test(s.title)) trades += s.body;
      else if (/输出文件|局限|注意/.test(s.title)) notes += s.body;
      else summary += s.body;
    });
    return { summary: summary, trades: trades, notes: notes };
  }

  /* 明细表里的证券代码也加上行情外链 */
  function linkifyCodes(html, assetType) {
    return html.replace(/<td>(\d{6})<\/td>/g, function (_, code) {
      return '<td>' + codeLink(assetType, code) + '</td>';
    });
  }

  function tradeDetails(tradesHtml, current) {
    if (!tradesHtml) return '';
    var assetType = current.type === 'fund' ? '基金' : '股票';
    var m = tradesHtml.match(/<div class="table-wrap"><table>([\s\S]*?)<\/table><\/div>/);
    var count = (tradesHtml.match(/<p>[^<]*?(\d+)\s*笔交易[^<]*<\/p>/) || [])[1] || '';
    if (!m) {
      return card('交易明细', '<div class="md-content">' + linkifyCodes(tradesHtml, assetType) + '</div>');
    }
    var rows = m[1].match(/<tr>[\s\S]*?<\/tr>/g) || [];
    var head = rows.length ? rows.shift() : '';
    var headCells = (head.match(/<th>[\s\S]*?<\/th>/g) || []).join('');
    var bodyRows = rows.filter(function (r) { return /<td>/.test(r); })
      .map(function (r) { return linkifyCodes(r, assetType); });
    var title = '交易明细' + (count
      ? ' <span style="font-size:12px;font-weight:400;color:var(--text-secondary);">共 ' + count + ' 笔</span>' : '');
    return card(title,
      '<div class="md-content">' +
      table(headCells,
        bodyRows.length ? pageSlice(bodyRows).join('') : '<tr><td colspan="8">暂无交易记录</td></tr>',
        'trade-table') +
      pager(bodyRows.length, { view: current.id }) +
      '</div>');
  }

  /* ---------------- 页面：回测 ---------------- */
  function renderBacktest(data) {
    var results = data.results || [];
    var navActions = document.querySelector('#site-header .nav-actions');
    var oldSelect = document.getElementById('backtest-select');
    if (oldSelect) oldSelect.remove();

    if (!results.length) {
      root.innerHTML = emptyState('📈', '该日期暂无回测结果', '回测由本地或 CI 运行生成');
      return;
    }
    var current = results.filter(function (r) { return r.id === state.view; })[0] || results[0];
    state.view = current.id;

    /* 回测记录选择器：放在导航栏右侧 */
    if (navActions) {
      var sel = document.createElement('select');
      sel.id = 'backtest-select';
      sel.className = 'nav-date-select';
      sel.setAttribute('aria-label', '选择回测记录');
      sel.innerHTML = results.map(function (r) {
        var label = (r.id.indexOf('fund') === 0 ? '基金回测' : '股票回测');
        return '<option value="' + esc(r.id) + '"' + (r.id === current.id ? ' selected' : '') + '>' +
          label + '</option>';
      }).join('');
      sel.addEventListener('change', function () {
        state.view = sel.value;
        state.page = 1;
        setParam('view', sel.value);
        setParam('page', null);
        renderBacktest(data);
      });
      navActions.insertBefore(sel, navActions.firstChild);
    }

    var parts = splitBacktestSummary(current.summary_html || '');
    var assetType = current.type === 'fund' ? '基金' : '股票';
    var detail = '';

    /* 1) 交互图表在最上方：悬浮显示当日日期与各项数值；静态 PNG 作为兜底/高清原图 */
    var chartUrl = current.chart ? 'charts/' + encodeURIComponent(current.chart) : '';
    if (chartUrl || current.series) {
      var chartBody = '<div id="bt-chart" class="bt-chart"><div class="bt-empty">正在加载净值曲线…</div></div>';
      if (chartUrl) {
        chartBody += '<details class="bt-fallback"><summary>查看静态高清原图</summary>' +
          '<a href="' + chartUrl + '" target="_blank" rel="noopener noreferrer" title="点击查看原图">' +
          '<img src="' + chartUrl + '" class="backtest-chart" alt="回测图表" loading="lazy"></a></details>';
      }
      detail += card('回测图表 <span style="font-size:12px;font-weight:400;color:var(--text-secondary);">' +
        '交互式 · 悬浮查看当日数据</span>', chartBody);
    }

    /* 2) 汇总数据：参数 / 绩效指标 / 年度收益 / 标的交易汇总 */
    if (parts.summary.trim()) {
      /* 卡片标题已是「回测汇总」，去掉 md 自带的同义大标题与重复日期 */
      var summaryHtml = linkifyCodes(
        parts.summary.replace(/<h1>[\s\S]*?<\/h1>/, ''), assetType);
      if (parts.notes.trim()) {
        summaryHtml += '<details class="md-notes"><summary>说明与输出文件</summary>' +
          linkifyCodes(parts.notes, assetType) + '</details>';
      }
      detail += card('回测汇总', '<div class="md-content" id="summary-content">' + summaryHtml + '</div>');
    } else if (parts.notes.trim()) {
      detail += card('回测说明', '<div class="md-content">' + parts.notes + '</div>');
    }

    /* 3) 每笔交易记录细节放在最下方，分页展示 */
    detail += tradeDetails(parts.trades, current);

    if (!detail) detail = '<div class="card"><div class="empty-state"><div class="empty-text">该回测无摘要与图表</div></div></div>';

    root.innerHTML = detail;
    loadInteractiveChart(current, chartUrl);
  }

  /* 曲线 JSON 按需加载：成功则绘制交互图，失败（旧日期/无数据）回退静态 PNG */
  function loadInteractiveChart(current, chartUrl) {
    var box = document.getElementById('bt-chart');
    if (!box) return;
    var fallback = chartUrl
      ? '<a href="' + chartUrl + '" target="_blank" rel="noopener noreferrer">' +
        '<img src="' + chartUrl + '" class="backtest-chart" alt="回测图表"></a>' +
        '<p class="bt-foot">交互曲线暂不可用，已显示静态图表。</p>'
      : '<div class="bt-empty">暂无净值曲线数据。</div>';
    if (!window.BacktestChart || !(current.series || current.nav)) {
      box.innerHTML = fallback;
      return;
    }
    var name = current.series || ('series_' + current.id + '.json');
    getJSON('data/' + state.date + '/' + encodeURIComponent(name))
      .then(function (s) {
        var target = document.getElementById('bt-chart');
        if (!target || state.view !== current.id) return; /* 已切换到另一份回测 */
        if (!s || !s.dates || !s.dates.length) { target.innerHTML = fallback; return; }
        window.BacktestChart.render(target, s, { fallbackImage: chartUrl });
      })
      .catch(function () {
        var target = document.getElementById('bt-chart');
        if (target && state.view === current.id) target.innerHTML = fallback;
      });
  }

  /* ---------------- 启动 ---------------- */
  function run() {
    getJSON('data/manifest.json')
      .then(function (manifest) {
        /* 用数据生成时间做版本号：CI 更新数据后 URL 自动变化，旧缓存立即失效 */
        DATA_VERSION = manifest.generated_at || String(Date.now());
        buildHeader(manifest);
        if (PAGE === 'pipeline' || PAGE === 'formulas') return; /* 静态壳自带内容 */

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
          manager: function () {
            return getJSON('data/' + state.date + '/manager_index.json').then(renderManager);
          },
          funds: function () {
            return getJSON('data/' + state.date + '/funds.json').then(renderFunds);
          },
          stocks: function () {
            return getJSON('data/' + state.date + '/stocks.json').then(renderStocks);
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
        /* 公式页 / 流水线页是静态壳自带内容，file:// 下 manifest 取不到时
           也要保留正文，只让页眉降级，不要用错误卡片把整页覆盖掉。 */
        if (root && PAGE !== 'formulas' && PAGE !== 'pipeline') {
          root.innerHTML = errorCard(err.message || err);
        }
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();

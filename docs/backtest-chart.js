/* ============================================================
 * 回测交互式图表（纯 SVG，无第三方依赖）
 *
 * 用法：
 *   BacktestChart.render(container, series, { fallbackImage: 'charts/x.png' })
 *
 * series 由 src/backtest_series.py 从净值曲线 CSV 生成（列式数组）。
 * 提供：净值/基准/回撤曲线 + 年度收益柱状图、鼠标悬浮十字准星与
 * 当日数值气泡、时间范围切换、触摸支持、静态原图降级入口。
 * ============================================================ */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var BLUE = '#1f77b4';
  var ORANGE = '#e08a26';
  var RED = '#b0342c';

  /* viewBox 固定，容器宽度自适应；小屏保底 720px 横向滚动 */
  var W = 1200, H = 500;
  var L = 78, R = 1172;
  var NAV_T = 34, NAV_B = 286;
  var DD_T = 340, DD_B = 452;
  var PLOT_W = R - L;

  var WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

  function el(tag, attrs, text) {
    var node = document.createElementNS(NS, tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      node.setAttribute(k, String(attrs[k]));
    });
    if (text != null) node.textContent = String(text);
    return node;
  }
  function div(cls, html) {
    var d = document.createElement('div');
    if (cls) d.className = cls;
    if (html != null) d.innerHTML = html;
    return d;
  }
  function finite(v) { return v != null && isFinite(Number(v)) && Number(v) === Number(v); }
  function f(v, digits) {
    return finite(v) ? Number(v).toFixed(digits == null ? 2 : digits) : '—';
  }
  function pct(v) { return finite(v) ? (Number(v) > 0 ? '+' : '') + f(v, 2) + '%' : '—'; }
  function money(v) {
    if (!finite(v)) return '—';
    return '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function weekday(d) {
    var t = new Date(d + 'T00:00:00Z');
    return isNaN(t.getTime()) ? '' : WEEK[t.getUTCDay()];
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* ---------------- 主渲染 ---------------- */
  function render(container, series, options) {
    if (!container) return;
    var opts = options || {};
    var dates = (series && series.dates) || [];
    var n = dates.length;
    container.innerHTML = '';
    if (!n) {
      container.appendChild(div('bt-empty', '暂无净值曲线数据，无法显示交互图表。'));
      return;
    }

    var nav = series.nav || [];
    var bm = series.benchmark || [];
    var dd = series.drawdown || [];
    var cum = series.cum_return || [];
    var exc = series.excess || [];
    var asset = series.total_asset || [];
    var cash = series.cash || [];
    var pos = series.position || [];
    var holds = series.holdings || [];
    var hasBm = bm.some(finite);

    /* ---- 顶部工具条：图例 + 区间按钮 ---- */
    var toolbar = div('bt-toolbar');
    var legend = div('bt-legend');
    legend.innerHTML =
      '<span><i class="bt-swatch" style="background:' + BLUE + '"></i>策略净值</span>' +
      (hasBm ? '<span><i class="bt-swatch dashed" style="background:' + ORANGE + '"></i>基准净值</span>' : '') +
      '<span><i class="bt-swatch" style="background:' + RED + '"></i>回撤</span>' +
      '<span class="bt-hint-text">鼠标悬浮 / 触摸查看当日数值</span>';
    toolbar.appendChild(legend);

    var ranges = div('bt-ranges');
    var RANGE_LIST = [
      { key: '3M', label: '近3月', months: 3 },
      { key: '6M', label: '近6月', months: 6 },
      { key: '1Y', label: '近1年', months: 12 },
      { key: 'ALL', label: '全部', months: 0 }
    ];
    RANGE_LIST.forEach(function (item) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'bt-range-btn' + (item.key === 'ALL' ? ' active' : '');
      b.textContent = item.label;
      b.setAttribute('data-range', item.key);
      b.addEventListener('click', function () {
        Array.prototype.forEach.call(ranges.children, function (c) { c.classList.remove('active'); });
        b.classList.add('active');
        state.start = startFor(item.months);
        draw();
      });
      ranges.appendChild(b);
    });
    toolbar.appendChild(ranges);
    container.appendChild(toolbar);

    /* ---- 概览数字 ---- */
    var lastNav = nav[n - 1], lastCum = cum[n - 1];
    var minDd = 0;
    dd.forEach(function (v) { if (finite(v) && Number(v) < minDd) minDd = Number(v); });
    var stats = div('bt-stats');
    stats.innerHTML =
      '<span>区间 <b>' + escapeHtml(dates[0]) + ' ~ ' + escapeHtml(dates[n - 1]) + '</b></span>' +
      '<span>交易日 <b>' + n + '</b></span>' +
      '<span>最新净值 <b>' + f(lastNav, 4) + '</b></span>' +
      '<span>累计收益 <b>' + pct(lastCum) + '</b></span>' +
      '<span>最大回撤 <b>' + pct(minDd) + '</b></span>';
    container.appendChild(stats);

    /* ---- 主图（净值 + 回撤，共用十字准星） ---- */
    var plot = div('bt-plot');
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, class: 'bt-svg', role: 'img',
      'aria-label': '回测净值走势与回撤曲线交互图' });
    var tooltip = div('bt-tooltip');
    tooltip.style.display = 'none';
    plot.appendChild(svg);
    plot.appendChild(tooltip);
    container.appendChild(plot);

    var cross = el('line', { class: 'bt-cross', y1: NAV_T, y2: DD_B, x1: 0, x2: 0 });
    var dotNav = el('circle', { class: 'bt-dot', r: 5, fill: BLUE });
    var dotBm = el('circle', { class: 'bt-dot', r: 4.5, fill: ORANGE });
    var dotDd = el('circle', { class: 'bt-dot', r: 4.5, fill: RED });
    var crossLabelBg = el('rect', { class: 'bt-cross-label-bg', y: DD_B + 4, height: 22, rx: 2 });
    var crossLabel = el('text', { class: 'bt-cross-label', y: DD_B + 19, 'text-anchor': 'middle' });
    var hit = el('rect', { x: L, y: NAV_T, width: PLOT_W, height: DD_B - NAV_T,
      fill: 'transparent', class: 'bt-hit' });

    var state = { start: 0, end: n - 1, xOf: null, ddMap: null, yNav: null };

    function startFor(months) {
      if (!months) return 0;
      var d = new Date(dates[n - 1] + 'T00:00:00Z');
      d.setUTCMonth(d.getUTCMonth() - months);
      var cut = d.toISOString().slice(0, 10);
      var i = 0;
      while (i < n - 1 && dates[i] < cut) i++;
      return i;
    }

    function linePath(arr, yOf) {
      var d = '', open = false;
      for (var i = state.start; i <= state.end; i++) {
        var v = arr[i];
        if (!finite(v)) { open = false; continue; }
        d += (open ? ' L' : ' M') + xOf(i).toFixed(1) + ' ' + yOf(Number(v)).toFixed(1);
        open = true;
      }
      return d;
    }
    function xOf(i) {
      return state.end === state.start
        ? (L + R) / 2
        : L + (i - state.start) / (state.end - state.start) * PLOT_W;
    }

    function axisText(x, y, str, anchor) {
      svg.appendChild(el('text', { x: x, y: y, 'text-anchor': anchor || 'start' }, str));
    }

    function draw() {
      state.xOf = xOf;
      while (svg.firstChild) svg.removeChild(svg.firstChild);

      /* y 轴范围：净值 + 基准，含 1.0 参考线 */
      var vals = [];
      for (var i = state.start; i <= state.end; i++) {
        if (finite(nav[i])) vals.push(Number(nav[i]));
        if (finite(bm[i])) vals.push(Number(bm[i]));
      }
      vals.push(1);
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
      var pad = Math.max((hi - lo) * 0.08, 0.02);
      lo -= pad; hi += pad;
      function yNav(v) { return NAV_B - (v - lo) / (hi - lo) * (NAV_B - NAV_T); }
      state.yNav = yNav;

      /* 回撤：0 在顶部，最深回撤在底部（与 matplotlib 图一致） */
      var ddMin = 0;
      for (var j = state.start; j <= state.end; j++) {
        if (finite(dd[j])) ddMin = Math.min(ddMin, Number(dd[j]));
      }
      if (ddMin === 0) ddMin = -1;
      function yDd(v) { return DD_T + clamp(Number(v) / ddMin, 0, 1.05) * (DD_B - DD_T); }
      state.ddMap = yDd;

      /* 净值区网格 + y 刻度 */
      for (var k = 0; k <= 4; k++) {
        var v = lo + (hi - lo) * k / 4;
        var y = yNav(v);
        svg.appendChild(el('line', { x1: L, y1: y, x2: R, y2: y, class: 'bt-grid' }));
        axisText(L - 10, y + 4, f(v, 2), 'end');
      }
      svg.appendChild(el('line', { x1: L, y1: yNav(1), x2: R, y2: yNav(1), class: 'bt-base' }));

      /* 回撤区网格 + y 刻度 */
      for (var k2 = 0; k2 <= 2; k2++) {
        var dv = ddMin * k2 / 2;
        var dy = yDd(dv);
        svg.appendChild(el('line', { x1: L, y1: dy, x2: R, y2: dy, class: 'bt-grid' }));
        axisText(L - 10, dy + 4, f(dv, 1) + '%', 'end');
      }

      /* 分隔标题 */
      axisText(L, NAV_T - 12, '净值走势', 'start');
      axisText(L, DD_T - 12, '回撤 (%)', 'start');

      /* 曲线 */
      svg.appendChild(el('path', { d: linePath(nav, yNav), class: 'bt-line bt-line-nav', stroke: BLUE }));
      if (hasBm) {
        svg.appendChild(el('path', { d: linePath(bm, yNav), class: 'bt-line bt-line-bm', stroke: ORANGE }));
      }
      /* 回撤面积：缺失值按 0 处理，保证基线闭合 */
      var area = 'M ' + xOf(state.start).toFixed(1) + ' ' + yDd(0).toFixed(1);
      for (var a = state.start; a <= state.end; a++) {
        area += ' L ' + xOf(a).toFixed(1) + ' ' + yDd(finite(dd[a]) ? Number(dd[a]) : 0).toFixed(1);
      }
      area += ' L ' + xOf(state.end).toFixed(1) + ' ' + yDd(0).toFixed(1) + ' Z';
      svg.appendChild(el('path', { d: area, class: 'bt-dd-area', fill: RED }));
      svg.appendChild(el('path', { d: linePath(dd, yDd), class: 'bt-line bt-line-dd', stroke: RED }));

      /* x 轴日期刻度 */
      var ticks = Math.min(7, state.end - state.start + 1);
      for (var t = 0; t < ticks; t++) {
        var ti = state.start + Math.round((state.end - state.start) * t / Math.max(1, ticks - 1));
        var tx = xOf(ti);
        svg.appendChild(el('line', { x1: tx, y1: NAV_B, x2: tx, y2: NAV_B + 5, class: 'bt-tick' }));
        svg.appendChild(el('line', { x1: tx, y1: DD_B, x2: tx, y2: DD_B + 5, class: 'bt-tick' }));
        axisText(tx, DD_B + 22, dates[ti].slice(2).replace(/-/g, '/'), 'middle');
      }

      /* 十字准星（放在最上层，不拦截鼠标） */
      svg.appendChild(cross);
      svg.appendChild(dotNav);
      svg.appendChild(dotBm);
      svg.appendChild(dotDd);
      svg.appendChild(crossLabelBg);
      svg.appendChild(crossLabel);
      svg.appendChild(hit);
      hide();
    }

    /* ---------------- tooltip ---------------- */
    function positionTooltip(clientX, clientY, box) {
      var pr = plot.getBoundingClientRect();
      var x = clientX - pr.left + plot.scrollLeft + 18;
      var y = clientY - pr.top + 14;
      if (x + box.offsetWidth > plot.scrollLeft + pr.width - 8) {
        x = clientX - pr.left + plot.scrollLeft - box.offsetWidth - 18;
      }
      x = Math.max(plot.scrollLeft + 6, x);
      y = clamp(y, 6, Math.max(6, pr.height - box.offsetHeight - 6));
      box.style.left = x + 'px';
      box.style.top = y + 'px';
    }

    function row(label, value, extra, color) {
      return '<tr><td class="bt-tt-label">' + (color ? '<i class="bt-swatch" style="background:' + color + '"></i>' : '') +
        label + '</td><td class="bt-tt-val">' + value + '</td>' +
        (extra ? '<td class="bt-tt-extra">' + extra + '</td>' : '') + '</tr>';
    }

    function show(i, clientX, clientY) {
      var x = xOf(i);
      cross.setAttribute('x1', x); cross.setAttribute('x2', x);
      cross.style.opacity = '1';
      var d = dates[i];
      /* 时间轴浮动标签（覆盖刻度，效果同行情软件的十字光标日期） */
      var bw = 92;
      var lx = clamp(x, L + bw / 2, R - bw / 2);
      crossLabelBg.setAttribute('x', lx - bw / 2);
      crossLabelBg.setAttribute('width', bw);
      crossLabelBg.style.opacity = '1';
      crossLabel.setAttribute('x', lx);
      crossLabel.textContent = d;
      crossLabel.style.opacity = '1';
      var html = '<div class="bt-tt-date">' + escapeHtml(d) +
        ' <span>' + weekday(d) + '</span></div><table class="bt-tt-table">';
      html += row('策略净值', f(nav[i], 4), '', BLUE);
      html += row('累计收益', pct(cum[i]), '', null);
      if (hasBm) {
        html += row('基准净值', f(bm[i], 4), '', ORANGE);
        html += row('基准累计', pct(finite(bm[i]) ? (Number(bm[i]) - 1) * 100 : null), '', null);
        html += row('超额收益', pct(exc[i]), '', null);
      }
      html += row('当日回撤', pct(dd[i]), '', RED);
      html += '</table><div class="bt-tt-foot">' +
        '总资产 <b>' + money(asset[i]) + '</b>' +
        ' · 现金 ' + money(cash[i]) + ' · 持仓 ' + money(pos[i]) +
        '<br>' + escapeHtml(series.holdings_label || '持仓标的数') + ' ' +
        (finite(holds[i]) ? Number(holds[i]) : '—') +
        ' · 本金 ' + money(series.initial_cash) +
        '</div>';
      tooltip.innerHTML = html;
      tooltip.style.display = 'block';
      positionTooltip(clientX, clientY, tooltip);

      if (finite(nav[i])) {
        dotNav.setAttribute('cx', x); dotNav.setAttribute('cy', state.yNav(Number(nav[i])));
        dotNav.style.opacity = '1';
      } else dotNav.style.opacity = '0';
      if (hasBm && finite(bm[i])) {
        dotBm.setAttribute('cx', x); dotBm.setAttribute('cy', state.yNav(Number(bm[i])));
        dotBm.style.opacity = '1';
      } else dotBm.style.opacity = '0';
      if (finite(dd[i])) {
        dotDd.setAttribute('cx', x); dotDd.setAttribute('cy', state.ddMap(Number(dd[i])));
        dotDd.style.opacity = '1';
      } else dotDd.style.opacity = '0';
    }

    function hide() {
      cross.style.opacity = '0';
      [dotNav, dotBm, dotDd, crossLabelBg, crossLabel].forEach(function (d) { d.style.opacity = '0'; });
      tooltip.style.display = 'none';
    }

    function nearestIndex(clientX) {
      var rect = svg.getBoundingClientRect();
      var vx = (clientX - rect.left) / rect.width * W;
      var ratio = (vx - L) / PLOT_W;
      return clamp(state.start + Math.round(ratio * (state.end - state.start)), state.start, state.end);
    }

    hit.addEventListener('mousemove', function (e) { show(nearestIndex(e.clientX), e.clientX, e.clientY); });
    hit.addEventListener('mouseleave', hide);
    hit.addEventListener('touchstart', function (e) {
      if (e.touches[0]) show(nearestIndex(e.touches[0].clientX), e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: true });
    hit.addEventListener('touchmove', function (e) {
      if (e.touches[0]) show(nearestIndex(e.touches[0].clientX), e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: true });
    hit.addEventListener('touchend', hide);

    /* ---- 年度收益柱状图（全区间，独立于时间范围） ---- */
    var yearly = series.yearly || [];
    if (yearly.length) {
      var yCard = div('bt-yearly');
      yCard.appendChild(div('bt-yearly-title', '年度收益（全区间，悬浮查看数值）'));
      var yPlot = div('bt-plot bt-plot-yearly');
      var YH = 170, YT = 22, YB = 128, YL = 78, YR = 1172;
      var ysvg = el('svg', { viewBox: '0 0 ' + W + ' ' + YH, class: 'bt-svg bt-svg-yearly' });
      var ytt = div('bt-tooltip');
      ytt.style.display = 'none';
      yPlot.appendChild(ysvg);
      yPlot.appendChild(ytt);
      yCard.appendChild(yPlot);
      container.appendChild(yCard);

      var yVals = yearly.map(function (o) { return Number(o.ret) || 0; });
      var yLo = Math.min.apply(null, yVals.concat([0]));
      var yHi = Math.max.apply(null, yVals.concat([0]));
      var yPad = Math.max((yHi - yLo) * 0.15, 1);
      yLo -= yPad; yHi += yPad;
      function yPos(v) { return YB - (v - yLo) / (yHi - yLo) * (YB - YT); }
      var zero = yPos(0);
      ysvg.appendChild(el('line', { x1: YL, y1: zero, x2: YR, y2: zero, class: 'bt-base' }));
      var slot = (YR - YL) / yearly.length;
      var bw = Math.min(72, slot * 0.55);
      yearly.forEach(function (o, idx) {
        var cx = YL + slot * (idx + 0.5);
        var v = Number(o.ret) || 0;
        var top = yPos(v);
        var color = v >= 0 ? BLUE : RED;
        var bar = el('rect', { x: cx - bw / 2, y: Math.min(top, zero), width: bw,
          height: Math.max(1, Math.abs(zero - top)), fill: color, opacity: 0.85, class: 'bt-bar' });
        ysvg.appendChild(bar);
        var label = el('text', { x: cx, y: v >= 0 ? top - 8 : top + 18, 'text-anchor': 'middle',
          class: 'bt-bar-label' }, pct(v));
        ysvg.appendChild(label);
        ysvg.appendChild(el('text', { x: cx, y: YB + 22, 'text-anchor': 'middle' }, String(o.year)));
        var zone = el('rect', { x: cx - slot / 2, y: YT, width: slot, height: YB - YT,
          fill: 'transparent', class: 'bt-hit' });
        zone.addEventListener('mouseenter', function () {
          ytt.innerHTML = '<div class="bt-tt-date">' + escapeHtml(o.year) + ' 年</div>' +
            '<table class="bt-tt-table">' + row('年度收益', pct(v), '', color) + '</table>';
          ytt.style.display = 'block';
          var pr = yPlot.getBoundingClientRect();
          var boxX = yPlot.scrollLeft + (cx / W) * ysvg.getBoundingClientRect().width + 12;
          ytt.style.left = Math.min(boxX, yPlot.scrollLeft + pr.width - ytt.offsetWidth - 8) + 'px';
          ytt.style.top = '12px';
          bar.setAttribute('opacity', '1');
        });
        zone.addEventListener('mouseleave', function () {
          ytt.style.display = 'none';
          bar.setAttribute('opacity', '0.85');
        });
        ysvg.appendChild(zone);
      });
    }

    /* ---- 静态原图入口（数据缺失或想看高清大图时仍可用） ---- */
    if (opts.fallbackImage) {
      var foot = div('bt-foot');
      foot.innerHTML = '交互图表由净值曲线数据实时绘制 · <a href="' +
        escapeHtml(opts.fallbackImage) + '" target="_blank" rel="noopener noreferrer">查看静态高清原图 ↗</a>';
      container.appendChild(foot);
    }

    draw();
  }

  window.BacktestChart = { render: render };
})();

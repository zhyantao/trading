#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「选股与选基公式」页面内容生成器（静态站 / 动态站唯一内容源）。

公式用 MathML 排版，不依赖任何 CDN 或第三方 JS。
权重全部从 selection_formula / factor_scoring 读取，页面与实际计算
永远使用同一组参数。
"""

from __future__ import annotations

import html
from typing import Any

from selection_formula import formula_parameters


def _math(inner: str) -> str:
    return '<math display="block" xmlns="http://www.w3.org/1998/Math/MathML">' + inner + "</math>"


# ── 行内符号的迷你记法 → MathML ─────────────────────────────
# 记法示例：R_a（下标）、P̂_{t+1}（帽子 + 下标组）、Ṽ_f（波浪号 + 下标）、
# ln(1+C_f)、M^*（上标）、B⁺_{f,s}、j∈{近1周,近1月,近3月}（{…} 为分组）。
# 支持 ₀-₉ 下标数字、² ⁿ ⁺ ⁻ 上标、预组合字符 Ṽ 等；多字母标识符自动正体。

_SUBSCRIPTS = str.maketrans({
    ord("₀"): "_0", ord("₁"): "_1", ord("₂"): "_2", ord("₃"): "_3", ord("₄"): "_4",
    ord("₅"): "_5", ord("₆"): "_6", ord("₇"): "_7", ord("₈"): "_8", ord("₉"): "_9",
    ord("ⁿ"): "^n", ord("⁺"): "^+", ord("⁻"): "^−", ord("²"): "^2", ord("³"): "^3",
    ord("Ṽ"): "Ṽ", ord("ṽ"): "ṽ",
})
_MATH_OPS = set("+-−·=<>≤≥±∈∉∨∧≡∣|:;,()[]{}*′/")
_EXTRA_MI = set("Σ⋃")
_ACCENTS = {"̂": "^", "̃": "~"}


def _mi(text: str, normal: bool = False) -> str:
    attr = ' mathvariant="normal"' if normal else ""
    return f"<mi{attr}>{html.escape(text)}</mi>"


def _mo(ch: str) -> str:
    return f"<mo>{html.escape(ch)}</mo>"


def _parse_inline(src: str) -> str:
    s = src.translate(_SUBSCRIPTS)
    n = len(s)
    i = 0

    def parse_atom(attach: bool = True) -> str:
        nonlocal i
        if i >= n:
            raise ValueError(f"unexpected end in {src!r}")
        ch = s[i]
        if ch.isdigit():
            j = i
            while j < n and (s[j].isdigit() or s[j] == "."):
                j += 1
            tok = f"<mn>{s[i:j]}</mn>"
            i = j
        elif ch.isascii() and ch.isalpha():
            j = i
            while j < n and s[j].isascii() and s[j].isalpha():
                j += 1
            tok = _mi(s[i:j], normal=j - i > 1)
            i = j
        elif not ch.isascii() and ("一" <= ch <= "鿿"):
            j = i
            while j < n and "一" <= s[j] <= "鿿":
                j += 1
            tok = _mi(s[i:j], normal=True)
            i = j
        elif not ch.isascii() and (ch.isalpha() or ch in _EXTRA_MI):
            tok = _mi(ch, normal=ch in _EXTRA_MI)
            i += 1
        elif ch in _MATH_OPS:
            tok = _mo(ch)
            i += 1
        else:
            raise ValueError(f"unhandled char {ch!r} at {i} in {src!r}")
        sub = sup = None
        while attach and i < n:
            ch = s[i]
            if ch in "_^":
                i += 1
                if i < n and s[i] == "{":
                    i += 1
                    inner = "<mrow>" + parse_seq(stop="}") + "</mrow>"
                else:
                    inner = parse_atom(attach=False)
                if ch == "_":
                    sub = inner
                else:
                    sup = inner
            elif ch in _ACCENTS:
                i += 1
                tok = f"<mover>{tok}<mo>{_ACCENTS[ch]}</mo></mover>"
            else:
                break
        if sub is not None and sup is not None:
            return f"<msubsup>{tok}{sub}{sup}</msubsup>"
        if sub is not None:
            return f"<msub>{tok}{sub}</msub>"
        if sup is not None:
            return f"<msup>{tok}{sup}</msup>"
        return tok

    def parse_seq(stop: str | None = None) -> str:
        nonlocal i
        parts: list[str] = []
        while i < n:
            ch = s[i]
            if stop is not None and ch == stop:
                i += 1
                return "".join(parts)
            if ch == " ":
                i += 1
                continue
            if ch == "{":
                i += 1
                parts.append("<mrow>" + parse_seq(stop="}") + "</mrow>")
                continue
            parts.append(parse_atom())
        if stop is not None:
            raise ValueError(f"unclosed group in {src!r}")
        return "".join(parts)

    return parse_seq()


def _inline(notation: str) -> str:
    """行内数学符号：迷你记法 → inline MathML。"""
    return '<math display="inline" xmlns="http://www.w3.org/1998/Math/MathML">' + _parse_inline(notation) + "</math>"


def _block(tag: str, formula: str, where: str = "") -> str:
    return (
        '<div class="formula-block">'
        f'<div class="formula-tag">{tag}</div>'
        + _math(formula)
        + (f'<div class="formula-where">{where}</div>' if where else "")
        + "</div>"
    )


def _param_rows(params: dict[str, Any]) -> str:
    fund_labels = {
        "annualized": _inline("α") + " · 成立来年化 " + _inline("R_a"),
        "recent_1y": _inline("β") + " · 近 1 年收益 " + _inline("R_1"),
        "consensus": _inline("γ") + " · 跨经理共识 " + _inline("ln(1+C_f)"),
        "manager_quality": _inline("δ") + " · 经理质量 " + _inline("Q_f"),
        "longevity": _inline("ε") + " · 成立时长 " + _inline("ln(1+D_f)"),
        "valuation": _inline("ζ") + " · 估算价格因子 " + _inline("Ṽ_f"),
    }
    stock_labels = {
        "managers": _inline("a") + " · 入选经理数 " + _inline("ln(1+M_s)"),
        "funds": _inline("b") + " · 出现基金数 " + _inline("ln(1+F_s)"),
        "holding_ratio": _inline("c") + " · 平均占净值比例 " + _inline("ln(1+P_s)"),
        "best_rank": _inline("d") + " · 最好名次 " + _inline("1−T̃_s"),
        "manager_quality": _inline("e") + " · 经理质量 " + _inline("Q_s"),
        "valuation": _inline("f") + " · 估算价格因子 " + _inline("Ṽ_s"),
    }
    factor_labels = {
        "return": "长期回报（多周期加权 " + _inline("z") + "-score）",
        "risk": "风险调整（跨周期离散度 + 负周期占比）",
        "stability": "稳定性（正周期占比 + 一致性）",
        "quality": "质量（成立时长 + 费率）",
        "consistency": "一致性（最差收益 + 中位/最佳比）",
        "experience": "经验（从业年限 + 管理规模）",
    }

    rows: list[str] = []
    for key, value in params["fund_weights"].items():
        rows.append(f'<tr><td>选基 ' + _inline("S_f") + f'</td><td>{fund_labels[key]}</td><td class="f-num">{value:.2f}</td></tr>')
    rows.append(
        '<tr><td>选基 ' + _inline("S_f") + '</td><td>' + _inline("λ") + ' · 出现负收益周期的惩罚</td>'
        f'<td class="f-num">{params["fund_penalty"]:.2f}</td></tr>'
    )
    for key, value in params["stock_weights"].items():
        rows.append(f'<tr><td>选股 ' + _inline("S_s") + f'</td><td>{stock_labels[key]}</td><td class="f-num">{value:.2f}</td></tr>')
    for key, value in params["fund_factor_weights"].items():
        rows.append(f'<tr><td>基金多因子</td><td>{factor_labels.get(key, key)}</td><td class="f-num">{value:.2f}</td></tr>')
    for key, value in params["manager_factor_weights"].items():
        rows.append(f'<tr><td>经理多因子</td><td>{factor_labels.get(key, key)}</td><td class="f-num">{value:.2f}</td></tr>')
    pp = params["price_params"]
    rows.append(
        '<tr><td>估算价格</td><td>' + _inline("λ") + ' · ' + _inline("EWMA") + ' 衰减因子</td>'
        f'<td class="f-num">{pp["lambda"]:.2f}</td></tr>'
    )
    rows.append(
        '<tr><td>估算价格</td><td>' + _inline("K") + ' · 有效样本量收缩先验 / 最少序列长度</td>'
        f'<td class="f-num">{pp["shrinkage_k"]:.0f} / {pp["min_series"]}</td></tr>'
    )
    rows.append(
        '<tr><td>估算价格</td><td>' + _inline("σ₀") + ' · 日波动先验（基金 / 股票）</td>'
        f'<td class="f-num">{pp["fund_sigma_prior"]*100:.1f}% / {pp["stock_sigma_prior"]*100:.1f}%</td></tr>'
    )
    rows.append(
        '<tr><td>估算价格</td><td>股票行情序列新鲜度上限（退市/长停回退代理）</td>'
        f'<td class="f-num">{pp.get("stock_stale_days", 15)} 天</td></tr>'
    )
    rows.append(
        '<tr><td>估算价格</td><td>' + _inline("MAD") + ' 缩尾倍数 / 区间收益率折算权重（周:月:季）</td>'
        f'<td class="f-num">{pp["return_winsor_mad"]:.0f} / '
        f'{pp["period_windows"]["近1周"][1]:.1f}:{pp["period_windows"]["近1月"][1]:.1f}:'
        f'{pp["period_windows"]["近3月"][1]:.1f}</td></tr>'
    )
    rows.append(
        '<tr><td>选样数量</td><td>全站基金 / 股票</td>'
        f'<td class="f-num">{params["top_funds"]} / {params["top_stocks"]}</td></tr>'
    )
    return "".join(rows)


def render_formula_doc(static: bool = True) -> str:
    """返回公式页正文 HTML（可直接插入静态壳或 Jinja 模板）。

    static=True  → 站内链接用 elite.html / stocks.html / funds.html
    static=False → 站内链接用 /elite / stocks / funds（FastAPI 动态站）
    """
    p = formula_parameters()
    fw, sw = p["fund_weights"], p["stock_weights"]
    suffix = ".html" if static else ""
    prefix = "" if static else "/"

    parts: list[str] = []
    parts.append(
        '<div class="formula-doc">'
        '<p class="formula-lead">本页用形式化记号描述本站「选基 → 选股 → 组合权重 → 调仓信号」的'
        '完整计算口径（含估算价格与估值因子）。所有公式与 '
        '<span class="f-mono">src/selection_formula.py</span>、'
        '<span class="f-mono">src/price_estimate.py</span>、'
        '<span class="f-mono">src/factor_scoring.py</span> 中的实现一一对应，参数表由代码直接生成；'
        '页面展示的「综合得分」为 ' + _inline("100·S") + '（满分 100）。</p>'
    )

    # ── 1. 记号 ────────────────────────────────────────────
    parts.append(
        '<h2>1. 记号与数据域</h2>'
        '<div class="table-wrap"><table class="formula-nota"><thead><tr>'
        '<th>记号</th><th>含义</th><th>数据来源</th></tr></thead><tbody>'
        '<tr><td>' + _inline("m,r_m") + '</td><td>基金经理及其业绩排名（越小越优）</td><td>基金经理业绩排名 CSV</td></tr>'
        '<tr><td>' + _inline("F_m,G_m") + '</td><td>经理 ' + _inline("m") + ' 的 Top3 基金候选 / Top10 股票候选</td><td>绩优基金经理候选池 CSV</td></tr>'
        '<tr><td>' + _inline("F=⋃_m F_m") + '</td><td>全站基金候选池（按代码去重）</td><td>同上</td></tr>'
        '<tr><td>' + _inline("G=⋃_m G_m") + '</td><td>全站股票候选池（按代码去重）</td><td>同上</td></tr>'
        '<tr><td>' + _inline("R_a,R_1,R_Σ") + '</td><td>成立来年化、近 1 年、成立来累计收益（%）</td><td>全市场基金排行</td></tr>'
        '<tr><td>' + _inline("D(f)") + '</td><td>基金成立天数</td><td>基金-经理关联表</td></tr>'
        '<tr><td>' + _inline("C_f,Q_f") + '</td><td>推荐该基金的经理数、经理质量均值</td><td>由候选池聚合</td></tr>'
        '<tr><td>' + _inline("M_s,F_s") + '</td><td>重仓该股票的经理数、基金数</td><td>由候选池聚合</td></tr>'
        '<tr><td>' + _inline("P_s,T_s") + '</td><td>平均占净值比例（%）、所有经理中的最好名次</td><td>由候选池聚合</td></tr>'
        '<tr><td>' + _inline("P_t,P̂_{t+1}") + '</td><td>最新价（基金单位净值 / 股票前复权收盘价）与 ' + _inline("T+1") + ' 估算价</td><td>净值、行情缓存序列与全市场基金排行</td></tr>'
        '<tr><td>' + _inline("μ̃,σ̂,σ₀") + '</td><td>收缩后的日漂移、' + _inline("EWMA") + ' 日波动、资产类别日波动先验</td><td>见式 (10)–(11)</td></tr>'
        '<tr><td>' + _inline("V,Ṽ") + '</td><td>风险调整估值信号 ' + _inline("μ̃/σ₀") + ' 及其横截面归一化</td><td>见式 (11)–(12)</td></tr>'
        '<tr><td>' + _inline("z̃(x),x̃") + '</td><td>稳健标准化后归一化、缩尾后 min-max 归一化</td><td>见式 (5)</td></tr>'
        '</tbody></table></div>'
    )

    # ── 2. 经理筛选 ─────────────────────────────────────────
    parts.append('<h2>2. 绩优经理集合</h2>')
    parts.append(_block(
        "定义 1 · 候选经理（无历史负业绩）",
        '<msup><mi>M</mi><mo>*</mo></msup><mo>=</mo><mo>{</mo><mi>m</mi><mo>∣</mo>'
        '<msub><mi>r</mi><mi>m</mi></msub><mo>≤</mo><mn>20</mn><mo>,</mo>'
        '<mo>∀</mo><mi>f</mi><mo>∈</mo><msub><mi>F</mi><mi>m</mi></msub><mo>:</mo>'
        '<msub><mi>R</mi><mn>1</mn></msub><mo>(</mo><mi>f</mi><mo>)</mo><mo>≥</mo><mn>0</mn><mo>∧</mo>'
        '<msub><mi>R</mi><mo>Σ</mo></msub><mo>(</mo><mi>f</mi><mo>)</mo><mo>≥</mo><mn>0</mn><mo>∧</mo>'
        '<mi>D</mi><mo>(</mo><mi>f</mi><mo>)</mo><mo>≥</mo><mn>180</mn><mo>}</mo>',
        "按经理排名向下扫描补足 20 位；成立不足 180 天的新基金在关联表阶段已过滤。",
    ))
    parts.append(_block(
        "定义 2 · 经理质量（排名越靠前贡献越大）",
        '<msub><mi>Q</mi><mi>f</mi></msub><mo>=</mo><mfrac><mn>1</mn><msub><mi>C</mi><mi>f</mi></msub></mfrac>'
        '<munder><mo>∑</mo><mrow><mi>m</mi><mo>:</mo><mi>f</mi><mo>∈</mo><msub><mi>F</mi><mi>m</mi></msub></mrow></munder>'
        '<mfrac><mn>1</mn><msub><mi>r</mi><mi>m</mi></msub></mfrac>'
        '<mo>,</mo><mspace width="1em"/><msub><mi>Q</mi><mi>s</mi></msub><mo>=</mo>'
        '<mfrac><mn>1</mn><msub><mi>M</mi><mi>s</mi></msub></mfrac>'
        '<munder><mo>∑</mo><mrow><mi>m</mi><mo>:</mo><mi>s</mi><mo>∈</mo><msub><mi>G</mi><mi>m</mi></msub></mrow></munder>'
        '<mfrac><mn>1</mn><msub><mi>r</mi><mi>m</mi></msub></mfrac>',
        "后文的 " + _inline("Q̃") + " 表示对 " + _inline("Q") + " 做式 (5) 的归一化。",
    ))

    # ── 3. 归一化 ───────────────────────────────────────────
    parts.append('<h2>3. 归一化算子</h2>')
    parts.append(_block(
        "式 (5) · 缩尾、稳健标准化与 min-max",
        '<msub><mi>x</mi><mi>i</mi></msub><mo>′</mo><mo>=</mo>'
        '<mi>clip</mi><mo>(</mo><msub><mi>x</mi><mi>i</mi></msub><mo>,</mo>'
        '<msub><mi>q</mi><mn>0.01</mn></msub><mo>,</mo><msub><mi>q</mi><mn>0.99</mn></msub><mo>)</mo>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msub><mi>z</mi><mi>i</mi></msub><mo>=</mo><mi>clip</mi><mo>(</mo>'
        '<mfrac><mrow><msubsup><mi>x</mi><mi>i</mi><mo>′</mo></msubsup><mo>−</mo><mi>med</mi><mo>(</mo><mi>x</mi><mo>′</mo><mo>)</mo></mrow>'
        '<mrow><mi>IQR</mi><mo>(</mo><mi>x</mi><mo>′</mo><mo>)</mo></mrow></mfrac>'
        '<mo>,</mo><mo>−</mo><mn>3</mn><mo>,</mo><mn>3</mn><mo>)</mo>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msub><mover><mi>x</mi><mo>~</mo></mover><mi>i</mi></msub><mo>=</mo>'
        '<mfrac><mrow><msub><mi>x</mi><mi>i</mi></msub><mo>−</mo><munder><mo>min</mo><mi>j</mi></munder><msub><mi>x</mi><mi>j</mi></msub></mrow>'
        '<mrow><munder><mo>max</mo><mi>j</mi></munder><msub><mi>x</mi><mi>j</mi></msub><mo>−</mo>'
        '<munder><mo>min</mo><mi>j</mi></munder><msub><mi>x</mi><mi>j</mi></msub></mrow></mfrac>',
        "缺失值按中性处理（" + _inline("z") + " 记 " + _inline("0") + "、" + _inline("x̃") + " 记中位数），"
        "常量序列 " + _inline("x̃≡0.5") + "；"
        "这样接口偶发缺字段时不会把标的误判为低分。",
    ))

    # ── 4. 估算价格 ─────────────────────────────────────────
    parts.append('<h2>4. 估算价格与估值因子</h2>')
    parts.append(
        '<p class="formula-note">估算价格 ' + _inline("P̂") + ' 是「按公开历史价格序列外推的下一交易日参考价」，'
        '不是实时报价，也不是目标价。基金用日单位净值序列（无序列时用公开区间收益率折算），'
        '股票用前复权收盘价序列（无序列时用重仓它的基金净值漂移按季报权重代理，只给涨跌、'
        '不虚构绝对价格）。数据全部来自仓库内已有的缓存序列与全市场排行字段，不新增联网请求。</p>'
    )
    parts.append(_block(
        "式 (9) · 对数收益与稳健缩尾",
        '<msub><mi>r</mi><mi>t</mi></msub><mo>=</mo><mi>clip</mi><mo>(</mo><mi>ln</mi><mo>(</mo>'
        '<mfrac><msub><mi>P</mi><mi>t</mi></msub><msub><mi>P</mi><mrow><mi>t</mi><mo>−</mo><mn>1</mn></mrow></msub></mfrac>'
        '<mo>)</mo><mo>,</mo><mi>med</mi><mo>(</mo><mi>r</mi><mo>)</mo><mo>±</mo><mi>c</mi><mo>·</mo>'
        '<mn>1.4826</mn><mo>·</mo><mi>MAD</mi><mo>(</mo><mi>r</mi><mo>)</mo><mo>)</mo>',
        "分红、份额折算会造成单日 10%+ 的「假收益」；用最近 120 日的中位数绝对偏差缩尾（倍数 "
        + _inline("c=5") + "），避免污染 " + _inline("EWMA") + "。",
    ))
    parts.append(_block(
        "式 (10) · EWMA 漂移、波动与样本量收缩",
        '<msub><mover><mi>μ</mi><mo>^</mo></mover><mi>t</mi></msub><mo>=</mo><mi>λ</mi>'
        '<msub><mover><mi>μ</mi><mo>^</mo></mover><mrow><mi>t</mi><mo>−</mo><mn>1</mn></mrow></msub>'
        '<mo>+</mo><mo>(</mo><mn>1</mn><mo>−</mo><mi>λ</mi><mo>)</mo><msub><mi>r</mi><mi>t</mi></msub>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msub><mover><mi>σ</mi><mo>^</mo></mover><mi>t</mi></msub><mo>=</mo><mi>EWMA</mi><mo>(</mo><mi>r</mi><mo>,</mo><mi>λ</mi><mo>)</mo>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msub><mi>n</mi><mi>eff</mi></msub><mo>=</mo><mfrac><mrow><mn>1</mn><mo>−</mo><msup><mi>λ</mi><mi>n</mi></msup></mrow>'
        '<mrow><mn>1</mn><mo>−</mo><mi>λ</mi></mrow></mfrac><mo>,</mo><mspace width="1em"/>'
        '<mover><mi>μ</mi><mo>~</mo></mover><mo>=</mo><msub><mover><mi>μ</mi><mo>^</mo></mover><mi>n</mi></msub>'
        '<mo>·</mo><mfrac><msub><mi>n</mi><mi>eff</mi></msub><mrow><msub><mi>n</mi><mi>eff</mi></msub><mo>+</mo><mi>K</mi></mrow></mfrac>',
        _inline("λ=0.94") + "（RiskMetrics），" + _inline("K=20") + " 为先验样本量；短的净值序列不参与序列口径，"
        "改走式 (12) 的区间收益率折算。",
    ))
    parts.append(_block(
        "式 (11) · " + _inline("T+1") + " 估算价、参考区间与估值信号",
        '<msub><mover><mi>P</mi><mo>^</mo></mover><mrow><mi>t</mi><mo>+</mo><mn>1</mn></mrow></msub>'
        '<mo>=</mo><msub><mi>P</mi><mi>t</mi></msub><mo>·</mo><msup><mi>e</mi><mover><mi>μ</mi><mo>~</mo></mover></msup>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msub><mi>I</mi><mn>68</mn></msub><mo>=</mo><mo>[</mo><msub><mi>P</mi><mi>t</mi></msub>'
        '<msup><mi>e</mi><mrow><mover><mi>μ</mi><mo>~</mo></mover><mo>−</mo><mover><mi>σ</mi><mo>^</mo></mover></mrow></msup>'
        '<mo>,</mo><msub><mi>P</mi><mi>t</mi></msub>'
        '<msup><mi>e</mi><mrow><mover><mi>μ</mi><mo>~</mo></mover><mo>+</mo><mover><mi>σ</mi><mo>^</mo></mover></mrow></msup><mo>]</mo>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msub><mi>V</mi><mi>raw</mi></msub><mo>=</mo><mi>clip</mi><mo>(</mo>'
        '<mfrac><mover><mi>μ</mi><mo>~</mo></mover><msub><mi>σ</mi><mn>0</mn></msub></mfrac>'
        '<mo>,</mo><mo>−</mo><mn>3</mn><mo>,</mo><mn>3</mn><mo>)</mo>',
        _inline("μ̃") + " 先按 " + _inline("±3σ₀") + " 截断；" + _inline("σ̂") + " 是标的自身 "
        + _inline("EWMA") + " 日波动（用于 " + _inline("±1σ") + " 参考区间），"
        + _inline("σ₀") + " 是资产类别统一先验（基金 1.2%、股票 2.2%，用于把 " + _inline("V_raw") + " 拉回同一风险尺度）。"
        "估算涨跌 = " + _inline("P̂/P_t−1") + "。",
    ))
    parts.append(_block(
        "式 (12) · 降级口径与 " + _inline("Ṽ") + " 的横截面归一化",
        '<mover><mi>μ</mi><mo>~</mo></mover><mo>=</mo>'
        '<mfrac><mrow><munder><mo>∑</mo><mi>j</mi></munder><msub><mi>w</mi><mi>j</mi></msub><mo>·</mo>'
        '<mfrac><mrow><mi>ln</mi><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>R</mi><mi>j</mi></msub><mo>)</mo></mrow>'
        '<msub><mi>d</mi><mi>j</mi></msub></mfrac></mrow><mrow><munder><mo>∑</mo><mi>j</mi></munder><msub><mi>w</mi><mi>j</mi></msub></mrow></mfrac>'
        '<mo>·</mo><mfrac><msub><mi>n</mi><mi>eff</mi></msub><mrow><msub><mi>n</mi><mi>eff</mi></msub><mo>+</mo><mi>K</mi></mrow></mfrac>'
        '<mo>,</mo><mspace width="1em"/>'
        '<mover><mi>V</mi><mo>~</mo></mover><mo>=</mo><mover><mi>x</mi><mo>~</mo></mover><mo>(</mo><msub><mi>V</mi><mi>raw</mi></msub><mo>)</mo>'
        '<mo>,</mo><mspace width="1em"/>'
        '<mover><mi>V</mi><mo>~</mo></mover><mo>≡</mo><mn>0.5</mn><mo> </mo><mo>(</mo><mi>missing</mi><mo>)</mo>',
        _inline("j∈{近1周,近1月,近3月}") + "，" + _inline("d_j=5/21/63") + " 交易日，"
        + _inline("w=0.5/0.3/0.2") + "；"
        "无行情序列的股票按季报「汇总占净值比例」对重仓基金的 " + _inline("μ̃_f") + " 加权代理。"
        + _inline("Ṽ") + " 在候选池横截面上做式 (5) 的缩尾 + min-max；缺数据的标的取中性 "
        + _inline("0.5") + "，既不奖励也不惩罚。",
    ))

    # ── 5. 选基 ─────────────────────────────────────────────
    parts.append('<h2>5. 选基公式</h2>')
    parts.append(_block(
        "式 (1) · 基金多因子基准分（用于「基金排名」页与优化持仓 --composite）",
        '<msup><mi>S</mi><mi>fac</mi></msup><mo>(</mo><mi>f</mi><mo>)</mo><mo>=</mo>'
        '<mfrac><mn>1</mn><mrow><munder><mo>∑</mo><mi>k</mi></munder><msub><mi>w</mi><mi>k</mi></msub></mrow></mfrac>'
        '<munder><mo>∑</mo><mrow><mi>k</mi><mo>∈</mo><mo>{</mo><mi>ret</mi><mo>,</mo><mi>risk</mi><mo>,</mo>'
        '<mi>stab</mi><mo>,</mo><mi>qual</mi><mo>}</mo></mrow></munder>'
        '<msub><mi>w</mi><mi>k</mi></msub><msub><mi>φ</mi><mi>k</mi></msub><mo>(</mo><mi>f</mi><mo>)</mo>',
        "回报因子按 7 个周期收益的加权稳健 " + _inline("z") + "-score 合成，并按每行「实际可用周期的权重和」归一；"
        "风险与稳定性先把各周期逐列标准化，消除近 1 月与成立来年化的量纲差异。",
    ))
    parts.append(_block(
        "式 (2) · 全局基金综合得分",
        '<msub><mi>S</mi><mi>f</mi></msub><mo>=</mo>'
        f'<mn>{fw["annualized"]:.2f}</mn><mover><mi>z</mi><mo>~</mo></mover><mo>(</mo><msub><mi>R</mi><mi>a</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{fw["recent_1y"]:.2f}</mn><mover><mi>z</mi><mo>~</mo></mover><mo>(</mo><msub><mi>R</mi><mn>1</mn></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{fw["consensus"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>C</mi><mi>f</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{fw["manager_quality"]:.2f}</mn><msub><mover><mi>Q</mi><mo>~</mo></mover><mi>f</mi></msub><mo>+</mo>'
        f'<mn>{fw["longevity"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>D</mi><mi>f</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{fw["valuation"]:.2f}</mn><msub><mover><mi>V</mi><mo>~</mo></mover><mi>f</mi></msub>'
        '<mo>−</mo>'
        f'<mn>{p["fund_penalty"]:.2f}</mn><mo>·</mo>'
        '<mn>1</mn><mo>[</mo><msub><mi>R</mi><mn>1</mn></msub><mo>&lt;</mo><mn>0</mn><mo>∨</mo>'
        '<msub><mi>R</mi><mo>Σ</mo></msub><mo>&lt;</mo><mn>0</mn><mo>]</mo>',
        "与「每位经理各取 3 只」不同，" + _inline("C_f") + " 让被多位经理共同选中的基金获得共识加分；"
        + _inline("Ṽ_f") + " 为式 (9)–(12) 的估算价格因子，同一基金的不同份额（A/B/C）按基础名称去重。",
    ))
    parts.append(_block(
        "式 (3) · 全局选基（唯一榜单）",
        '<msup><mi>F</mi><mo>*</mo></msup><mo>=</mo>'
        '<munder><mo>Top</mo><mn>3</mn></munder><mo>{</mo><msub><mi>S</mi><mi>f</mi></msub><mo>∣</mo><mi>f</mi><mo>∈</mo><mi>F</mi><mo>}</mo>',
        "即「绩优标的」页的基金 Top3：<b>综合所有经理只选 3 条</b>，不是每位经理 3 条。",
    ))

    # ── 6. 选股 ─────────────────────────────────────────────
    parts.append('<h2>6. 选股公式</h2>')
    parts.append(_block(
        "式 (4) · 股票共识综合得分",
        '<msub><mi>S</mi><mi>s</mi></msub><mo>=</mo>'
        f'<mn>{sw["managers"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>M</mi><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["funds"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>F</mi><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["holding_ratio"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>P</mi><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["best_rank"]:.2f}</mn><mo>(</mo><mn>1</mn><mo>−</mo><msub><mover><mi>T</mi><mo>~</mo></mover><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["manager_quality"]:.2f}</mn><msub><mover><mi>Q</mi><mo>~</mo></mover><mi>s</mi></msub><mo>+</mo>'
        f'<mn>{sw["valuation"]:.2f}</mn><msub><mover><mi>V</mi><mo>~</mo></mover><mi>s</mi></msub>',
        "对数压缩防止单只基金的高仓位主导排名；" + _inline("M_s") + " 与 " + _inline("F_s") + " 分别按经理、"
        "按 <span class=\"f-mono\">Top3基金列表</span> 去重计数；" + _inline("Ṽ_s") + " 为估算价格因子，"
        "无行情序列时按重仓基金净值漂移代理。「股票排名」页与「优化持仓」的股票得分都使用 " + _inline("S_s") + "。",
    ))
    parts.append(_block(
        "式 (6) · 全局选股（唯一榜单）",
        '<msup><mi>G</mi><mo>*</mo></msup><mo>=</mo>'
        '<munder><mo>Top</mo><mn>10</mn></munder><mo>{</mo><msub><mi>S</mi><mi>s</mi></msub><mo>∣</mo><mi>s</mi><mo>∈</mo><mi>G</mi><mo>}</mo>',
        "即「绩优标的」页的股票 Top10：<b>综合所有经理只选 10 条</b>；"
        "完整的去重股票池（含综合得分）仍在「股票排名」页展示。",
    ))

    # ── 7. 组合权重 ─────────────────────────────────────────
    parts.append('<h2>7. 组合权重与信号</h2>')
    parts.append(_block(
        "式 (7) · 得分归一化的目标权重",
        '<msub><mi>w</mi><mi>i</mi></msub><mo>=</mo><mi>B</mi><mo>·</mo>'
        '<mfrac><msub><mi>S</mi><mi>i</mi></msub><mrow><munder><mo>∑</mo><mrow><mi>j</mi><mo>∈</mo><mi>P</mi></mrow></munder><msub><mi>S</mi><mi>j</mi></msub></mrow></mfrac>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msub><mi>w</mi><mi>i</mi></msub><mo>≤</mo><msub><mi>w</mi><mo>max</mo></msub>'
        '<mo>,</mo><mspace width="1em"/>'
        '<msubsup><mi>w</mi><mi>i</mi><mi>RP</mi></msubsup><mo>=</mo><mi>B</mi><mo>·</mo>'
        '<mfrac><mrow><msub><mi>S</mi><mi>i</mi></msub><mo>/</mo><msub><mi>σ</mi><mi>i</mi></msub></mrow>'
        '<mrow><munder><mo>∑</mo><mi>j</mi></munder><msub><mi>S</mi><mi>j</mi></msub><mo>/</mo><msub><mi>σ</mi><mi>j</mi></msub></mrow></mfrac>',
        _inline("B") + " 为股票/基金大类权重桶（默认 30% / 70%），" + _inline("w_max") + " 为单一持仓上限；"
        "启用风险平价时用覆盖经理数的倒数作为风险代理 " + _inline("σ") + "。",
    ))
    parts.append(_block(
        "式 (8) · 调仓信号净强度",
        '<msub><mi>N</mi><mi>s</mi></msub><mo>=</mo>'
        '<munder><mo>∑</mo><mrow><mi>m</mi><mo>∈</mo><msup><mi>M</mi><mo>*</mo></msup></mrow></munder>'
        '<munder><mo>∑</mo><mrow><mi>f</mi><mo>∈</mo><msub><mi>F</mi><mi>m</mi></msub></mrow></munder>'
        '<mo>(</mo><msubsup><mi>B</mi><mrow><mi>f</mi><mo>,</mo><mi>s</mi></mrow><mo>+</mo></msubsup>'
        '<mo>−</mo><msubsup><mi>B</mi><mrow><mi>f</mi><mo>,</mo><mi>s</mi></mrow><mo>−</mo></msubsup><mo>)</mo>',
        _inline("B⁺") + " / " + _inline("B⁻") + " 为基金季度「重大变动」中累计买入 / 卖出占期初净值比例；"
        "按 " + _inline("|N_s|") + " 与阈值 " + _inline("τ=1.0") + " 比较，输出关注买入 / 关注卖出 / 继续关注。",
    ))

    # ── 8. 参数表 ───────────────────────────────────────────
    parts.append(
        '<h2>8. 参数（由代码直接生成）</h2>'
        '<div class="table-wrap"><table class="formula-params"><thead><tr>'
        '<th>模块</th><th>因子</th><th>权重 / 取值</th></tr></thead><tbody>'
        + _param_rows(p)
        + '</tbody></table></div>'
        '<p class="formula-note">所有权重按组归一（' + _inline("Σ=1") + '）；' + _inline("S_f") + '、'
        + _inline("S_s") + ' 截断到 ' + _inline("[0,1]") + '，页面得分 = ' + _inline("100·S") + '。'
        '调整权重请修改 <span class="f-mono">selection_formula.py</span> 顶部的常量，'
        '估算价格参数请修改 <span class="f-mono">price_estimate.py</span> 的 '
        '<span class="f-mono">PRICE_PARAMS</span>，'
        '公式页、静态站与动态站会同步更新。</p>'
    )

    # ── 9. 实现映射与限制 ───────────────────────────────────
    parts.append(
        '<h2>9. 实现映射与口径边界</h2>'
        '<div class="table-wrap"><table class="formula-nota"><thead><tr>'
        '<th>公式</th><th>实现位置</th><th>消费方</th></tr></thead><tbody>'
        '<tr><td>定义 1</td><td class="f-mono">pick_elite_managers_targets.py</td><td>候选池 CSV</td></tr>'
        '<tr><td>式 (1)、式 (5)</td><td class="f-mono">factor_scoring.py</td><td>基金排名、经理排名、优化持仓</td></tr>'
        '<tr><td>式 (9)–(12)</td><td class="f-mono">price_estimate.py</td><td>估算价格册 <span class="f-mono">price_estimates.json</span>、估值因子 ' + _inline("Ṽ") + '</td></tr>'
        '<tr><td>式 (2)、式 (3)</td><td class="f-mono">selection_formula.py → select_global_funds</td><td>绩优标的 · 基金 Top3</td></tr>'
        '<tr><td>式 (4)、式 (6)</td><td class="f-mono">selection_formula.py → score_stock_candidates</td><td>绩优标的 · 股票 Top10、股票排名、优化持仓</td></tr>'
        '<tr><td>式 (7)</td><td class="f-mono">optimize_holdings.py</td><td>我的持仓</td></tr>'
        '<tr><td>式 (8)</td><td class="f-mono">daily_rebalance_signal.py</td><td>每日信号</td></tr>'
        '</tbody></table></div>'
        '<p class="formula-note">口径边界：基金/股票候选来自公开披露的季报前十大重仓股与'
        '「重大变动」数据，属于季度滞后信息；净值与收益率来自第三方排行接口，'
        '可能存在披露延迟或口径差异。估算价格是「用历史价格序列外推的 ' + _inline("T+1") + ' 参考价」，'
        '不含盘中实时行情、公告事件与分析师预期；没有行情序列的股票显示为「暂无」，'
        '其估值因子按重仓基金净值漂移代理或取中性 ' + _inline("0.5") + '，代理口径不代表个股真实涨跌。'
        '估算价格与估值因子仅用于数据研究，不构成投资建议。</p>'
        '<p class="formula-links"><a href="' + prefix + 'elite' + suffix + '">查看绩优标的 →</a> · '
        '<a href="' + prefix + 'stocks' + suffix + '">查看股票排名 →</a> · '
        '<a href="' + prefix + 'funds' + suffix + '">查看基金排名 →</a></p>'
        '</div>'
    )
    return "".join(parts)


if __name__ == "__main__":
    print(render_formula_doc())

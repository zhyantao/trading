#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「选股与选基公式」页面内容生成器（静态站 / 动态站唯一内容源）。

公式用 MathML 排版，不依赖任何 CDN 或第三方 JS；每个公式同时给出
一行纯文本形式，便于复制、检索与在不支持 MathML 的环境里阅读。
权重全部从 selection_formula / factor_scoring 读取，页面与实际计算
永远使用同一组参数。
"""

from __future__ import annotations

import html
from typing import Any

from selection_formula import formula_parameters


def _math(inner: str) -> str:
    return '<math display="block" xmlns="http://www.w3.org/1998/Math/MathML">' + inner + "</math>"


def _block(tag: str, formula: str, plain: str, where: str = "") -> str:
    return (
        '<div class="formula-block">'
        f'<div class="formula-tag">{tag}</div>'
        + _math(formula)
        + f'<div class="formula-plain"><code>{html.escape(plain)}</code></div>'
        + (f'<div class="formula-where">{where}</div>' if where else "")
        + "</div>"
    )


def _param_rows(params: dict[str, Any]) -> str:
    fund_labels = {
        "annualized": "α · 成立来年化 <span class=\"f-mono\">R_a</span>",
        "recent_1y": "β · 近 1 年收益 <span class=\"f-mono\">R_1</span>",
        "consensus": "γ · 跨经理共识 <span class=\"f-mono\">ln(1+C_f)</span>",
        "manager_quality": "δ · 经理质量 <span class=\"f-mono\">Q_f</span>",
        "longevity": "ε · 成立时长 <span class=\"f-mono\">ln(1+D_f)</span>",
    }
    stock_labels = {
        "managers": "a · 入选经理数 <span class=\"f-mono\">ln(1+M_s)</span>",
        "funds": "b · 出现基金数 <span class=\"f-mono\">ln(1+F_s)</span>",
        "holding_ratio": "c · 平均占净值比例 <span class=\"f-mono\">ln(1+P_s)</span>",
        "best_rank": "d · 最好名次 <span class=\"f-mono\">1−T̃_s</span>",
        "manager_quality": "e · 经理质量 <span class=\"f-mono\">Q_s</span>",
    }
    factor_labels = {
        "return": "长期回报（多周期加权 z-score）",
        "risk": "风险调整（跨周期离散度 + 负周期占比）",
        "stability": "稳定性（正周期占比 + 一致性）",
        "quality": "质量（成立时长 + 费率）",
        "consistency": "一致性（最差收益 + 中位/最佳比）",
        "experience": "经验（从业年限 + 管理规模）",
    }

    rows: list[str] = []
    for key, value in params["fund_weights"].items():
        rows.append(f'<tr><td>选基 S<sub>f</sub></td><td>{fund_labels[key]}</td><td class="f-num">{value:.2f}</td></tr>')
    rows.append(
        '<tr><td>选基 S<sub>f</sub></td><td>λ · 出现负收益周期的惩罚</td>'
        f'<td class="f-num">{params["fund_penalty"]:.2f}</td></tr>'
    )
    for key, value in params["stock_weights"].items():
        rows.append(f'<tr><td>选股 S<sub>s</sub></td><td>{stock_labels[key]}</td><td class="f-num">{value:.2f}</td></tr>')
    for key, value in params["fund_factor_weights"].items():
        rows.append(f'<tr><td>基金多因子</td><td>{factor_labels.get(key, key)}</td><td class="f-num">{value:.2f}</td></tr>')
    for key, value in params["manager_factor_weights"].items():
        rows.append(f'<tr><td>经理多因子</td><td>{factor_labels.get(key, key)}</td><td class="f-num">{value:.2f}</td></tr>')
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
        '完整计算口径。所有公式与 <span class="f-mono">src/selection_formula.py</span>、'
        '<span class="f-mono">src/factor_scoring.py</span> 中的实现一一对应，参数表由代码直接生成；'
        '页面展示的「综合得分」为 <span class="f-mono">100 · S</span>（满分 100）。</p>'
    )

    # ── 1. 记号 ────────────────────────────────────────────
    parts.append(
        '<h2>1. 记号与数据域</h2>'
        '<div class="table-wrap"><table class="formula-nota"><thead><tr>'
        '<th>记号</th><th>含义</th><th>数据来源</th></tr></thead><tbody>'
        '<tr><td class="f-mono">m, r<sub>m</sub></td><td>基金经理及其业绩排名（越小越优）</td><td>基金经理业绩排名 CSV</td></tr>'
        '<tr><td class="f-mono">F<sub>m</sub>, G<sub>m</sub></td><td>经理 m 的 Top3 基金候选 / Top10 股票候选</td><td>绩优基金经理候选池 CSV</td></tr>'
        '<tr><td class="f-mono">F = ⋃<sub>m</sub> F<sub>m</sub></td><td>全站基金候选池（按代码去重）</td><td>同上</td></tr>'
        '<tr><td class="f-mono">G = ⋃<sub>m</sub> G<sub>m</sub></td><td>全站股票候选池（按代码去重）</td><td>同上</td></tr>'
        '<tr><td class="f-mono">R<sub>a</sub>, R<sub>1</sub>, R<sub>Σ</sub></td><td>成立来年化、近 1 年、成立来累计收益（%）</td><td>全市场基金排行</td></tr>'
        '<tr><td class="f-mono">D(f)</td><td>基金成立天数</td><td>基金-经理关联表</td></tr>'
        '<tr><td class="f-mono">C<sub>f</sub>, Q<sub>f</sub></td><td>推荐该基金的经理数、经理质量均值</td><td>由候选池聚合</td></tr>'
        '<tr><td class="f-mono">M<sub>s</sub>, F<sub>s</sub></td><td>重仓该股票的经理数、基金数</td><td>由候选池聚合</td></tr>'
        '<tr><td class="f-mono">P<sub>s</sub>, T<sub>s</sub></td><td>平均占净值比例（%）、所有经理中的最好名次</td><td>由候选池聚合</td></tr>'
        '<tr><td class="f-mono">z̃(x), x̃</td><td>稳健标准化后归一化、缩尾后 min-max 归一化</td><td>见式 (5)</td></tr>'
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
        "M* = { m | r_m ≤ 20, ∀ f ∈ F_m : R_1(f) ≥ 0 ∧ R_Σ(f) ≥ 0 ∧ D(f) ≥ 180 }",
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
        "Q_f = (1/C_f) Σ_{m: f∈F_m} 1/r_m ;  Q_s = (1/M_s) Σ_{m: s∈G_m} 1/r_m",
        "后文的 <span class=\"f-mono\">Q̃</span> 表示对 Q 做式 (5) 的归一化。",
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
        "x' = clip(x, q0.01, q0.99);  z = clip((x' − med)/IQR, −3, 3);  x̃ = (x − min x)/(max x − min x)",
        "缺失值按中性处理（z 记 0、x̃ 记中位数），常量序列 x̃ ≡ 0.5；"
        "这样接口偶发缺字段时不会把标的误判为低分。",
    ))

    # ── 4. 选基 ─────────────────────────────────────────────
    parts.append('<h2>4. 选基公式</h2>')
    parts.append(_block(
        "式 (1) · 基金多因子基准分（用于「基金排名」页与优化持仓 --composite）",
        '<msup><mi>S</mi><mi>fac</mi></msup><mo>(</mo><mi>f</mi><mo>)</mo><mo>=</mo>'
        '<mfrac><mn>1</mn><mrow><munder><mo>∑</mo><mi>k</mi></munder><msub><mi>w</mi><mi>k</mi></msub></mrow></mfrac>'
        '<munder><mo>∑</mo><mrow><mi>k</mi><mo>∈</mo><mo>{</mo><mi>ret</mi><mo>,</mo><mi>risk</mi><mo>,</mo>'
        '<mi>stab</mi><mo>,</mo><mi>qual</mi><mo>}</mo></mrow></munder>'
        '<msub><mi>w</mi><mi>k</mi></msub><msub><mi>φ</mi><mi>k</mi></msub><mo>(</mo><mi>f</mi><mo>)</mo>',
        "S^fac(f) = (1/Σ_k w_k) · Σ_k w_k φ_k(f),  k ∈ {ret, risk, stab, qual}",
        "回报因子按 7 个周期收益的加权稳健 z-score 合成，并按每行「实际可用周期的权重和」归一；"
        "风险与稳定性先把各周期逐列标准化，消除近 1 月与成立来年化的量纲差异。",
    ))
    parts.append(_block(
        "式 (2) · 全局基金综合得分",
        '<msub><mi>S</mi><mi>f</mi></msub><mo>=</mo>'
        f'<mn>{fw["annualized"]:.2f}</mn><mover><mi>z</mi><mo>~</mo></mover><mo>(</mo><msub><mi>R</mi><mi>a</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{fw["recent_1y"]:.2f}</mn><mover><mi>z</mi><mo>~</mo></mover><mo>(</mo><msub><mi>R</mi><mn>1</mn></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{fw["consensus"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>C</mi><mi>f</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{fw["manager_quality"]:.2f}</mn><msub><mover><mi>Q</mi><mo>~</mo></mover><mi>f</mi></msub><mo>+</mo>'
        f'<mn>{fw["longevity"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>D</mi><mi>f</mi></msub><mo>)</mo>'
        '<mo>−</mo>'
        f'<mn>{p["fund_penalty"]:.2f}</mn><mo>·</mo>'
        '<mn>1</mn><mo>[</mo><msub><mi>R</mi><mn>1</mn></msub><mo>&lt;</mo><mn>0</mn><mo>∨</mo>'
        '<msub><mi>R</mi><mo>Σ</mo></msub><mo>&lt;</mo><mn>0</mn><mo>]</mo>',
        f'S_f = {fw["annualized"]:.2f}·z̃(R_a) + {fw["recent_1y"]:.2f}·z̃(R_1) + '
        f'{fw["consensus"]:.2f}·lñ(1+C_f) + {fw["manager_quality"]:.2f}·Q̃_f + '
        f'{fw["longevity"]:.2f}·lñ(1+D_f) − {p["fund_penalty"]:.2f}·1[R_1<0 ∨ R_Σ<0]',
        "与「每位经理各取 3 只」不同，C<sub>f</sub> 让被多位经理共同选中的基金获得共识加分；"
        "同一基金的不同份额（A/B/C）按基础名称去重，只保留得分最高的一只。",
    ))
    parts.append(_block(
        "式 (3) · 全局选基（唯一榜单）",
        '<msup><mi>F</mi><mo>*</mo></msup><mo>=</mo>'
        '<munder><mo>Top</mo><mn>3</mn></munder><mo>{</mo><msub><mi>S</mi><mi>f</mi></msub><mo>∣</mo><mi>f</mi><mo>∈</mo><mi>F</mi><mo>}</mo>',
        "F* = Top_3 { S_f | f ∈ F }   （同分依次比较 C_f、R_a、基金代码）",
        "即「绩优标的」页的基金 Top3：<b>综合所有经理只选 3 条</b>，不是每位经理 3 条。",
    ))

    # ── 5. 选股 ─────────────────────────────────────────────
    parts.append('<h2>5. 选股公式</h2>')
    parts.append(_block(
        "式 (4) · 股票共识综合得分",
        '<msub><mi>S</mi><mi>s</mi></msub><mo>=</mo>'
        f'<mn>{sw["managers"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>M</mi><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["funds"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>F</mi><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["holding_ratio"]:.2f}</mn><mover><mi>ln</mi><mo>~</mo></mover><mo>(</mo><mn>1</mn><mo>+</mo><msub><mi>P</mi><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["best_rank"]:.2f}</mn><mo>(</mo><mn>1</mn><mo>−</mo><msub><mover><mi>T</mi><mo>~</mo></mover><mi>s</mi></msub><mo>)</mo><mo>+</mo>'
        f'<mn>{sw["manager_quality"]:.2f}</mn><msub><mover><mi>Q</mi><mo>~</mo></mover><mi>s</mi></msub>',
        f'S_s = {sw["managers"]:.2f}·lñ(1+M_s) + {sw["funds"]:.2f}·lñ(1+F_s) + '
        f'{sw["holding_ratio"]:.2f}·lñ(1+P_s) + {sw["best_rank"]:.2f}·(1−T̃_s) + '
        f'{sw["manager_quality"]:.2f}·Q̃_s',
        "对数压缩防止单只基金的高仓位主导排名；M<sub>s</sub> 与 F<sub>s</sub> 分别按经理、"
        "按 <span class=\"f-mono\">Top3基金列表</span> 去重计数。「股票排名」页与"
        "「优化持仓」的股票得分都使用 S<sub>s</sub>。",
    ))
    parts.append(_block(
        "式 (6) · 全局选股（唯一榜单）",
        '<msup><mi>G</mi><mo>*</mo></msup><mo>=</mo>'
        '<munder><mo>Top</mo><mn>10</mn></munder><mo>{</mo><msub><mi>S</mi><mi>s</mi></msub><mo>∣</mo><mi>s</mi><mo>∈</mo><mi>G</mi><mo>}</mo>',
        "G* = Top_10 { S_s | s ∈ G }   （同分依次比较 M_s、F_s、P_s、T_s、代码）",
        "即「绩优标的」页的股票 Top10：<b>综合所有经理只选 10 条</b>；"
        "完整的去重股票池（含综合得分）仍在「股票排名」页展示。",
    ))

    # ── 6. 组合权重 ─────────────────────────────────────────
    parts.append('<h2>6. 组合权重与信号</h2>')
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
        "w_i = B · S_i / Σ_j S_j,  w_i ≤ w_max ;  w_i^RP = B · (S_i/σ_i) / Σ_j (S_j/σ_j)",
        "B 为股票/基金大类权重桶（默认 30% / 70%），w<sub>max</sub> 为单一持仓上限；"
        "启用风险平价时用覆盖经理数的倒数作为风险代理 σ。",
    ))
    parts.append(_block(
        "式 (8) · 调仓信号净强度",
        '<msub><mi>N</mi><mi>s</mi></msub><mo>=</mo>'
        '<munder><mo>∑</mo><mrow><mi>m</mi><mo>∈</mo><msup><mi>M</mi><mo>*</mo></msup></mrow></munder>'
        '<munder><mo>∑</mo><mrow><mi>f</mi><mo>∈</mo><msub><mi>F</mi><mi>m</mi></msub></mrow></munder>'
        '<mo>(</mo><msubsup><mi>B</mi><mrow><mi>f</mi><mo>,</mo><mi>s</mi></mrow><mo>+</mo></msubsup>'
        '<mo>−</mo><msubsup><mi>B</mi><mrow><mi>f</mi><mo>,</mo><mi>s</mi></mrow><mo>−</mo></msubsup><mo>)</mo>',
        "N_s = Σ_{m∈M*} Σ_{f∈F_m} ( B⁺_{f,s} − B⁻_{f,s} )",
        "B<sup>+</sup> / B<sup>−</sup> 为基金季度「重大变动」中累计买入 / 卖出占期初净值比例；"
        "按 |N<sub>s</sub>| 与阈值 τ=1.0 比较，输出关注买入 / 关注卖出 / 继续关注。",
    ))

    # ── 7. 参数表 ───────────────────────────────────────────
    parts.append(
        '<h2>7. 参数（由代码直接生成）</h2>'
        '<div class="table-wrap"><table class="formula-params"><thead><tr>'
        '<th>模块</th><th>因子</th><th>权重 / 取值</th></tr></thead><tbody>'
        + _param_rows(p)
        + '</tbody></table></div>'
        '<p class="formula-note">所有权重按组归一（Σ = 1）；S<sub>f</sub>、S<sub>s</sub> 截断到 [0, 1]，'
        '页面得分 = 100 · S。调整权重请修改 <span class="f-mono">selection_formula.py</span> 顶部的常量，'
        '公式页、静态站与动态站会同步更新。</p>'
    )

    # ── 8. 实现映射与限制 ───────────────────────────────────
    parts.append(
        '<h2>8. 实现映射与口径边界</h2>'
        '<div class="table-wrap"><table class="formula-nota"><thead><tr>'
        '<th>公式</th><th>实现位置</th><th>消费方</th></tr></thead><tbody>'
        '<tr><td>定义 1</td><td class="f-mono">pick_elite_managers_targets.py</td><td>候选池 CSV</td></tr>'
        '<tr><td>式 (1)、式 (5)</td><td class="f-mono">factor_scoring.py</td><td>基金排名、经理排名、优化持仓</td></tr>'
        '<tr><td>式 (2)、式 (3)</td><td class="f-mono">selection_formula.py → select_global_funds</td><td>绩优标的 · 基金 Top3</td></tr>'
        '<tr><td>式 (4)、式 (6)</td><td class="f-mono">selection_formula.py → score_stock_candidates</td><td>绩优标的 · 股票 Top10、股票排名、优化持仓</td></tr>'
        '<tr><td>式 (7)</td><td class="f-mono">optimize_holdings.py</td><td>我的持仓</td></tr>'
        '<tr><td>式 (8)</td><td class="f-mono">daily_rebalance_signal.py</td><td>每日信号</td></tr>'
        '</tbody></table></div>'
        '<p class="formula-note">口径边界：基金/股票候选来自公开披露的季报前十大重仓股与'
        '「重大变动」数据，属于季度滞后信息；净值与收益率来自第三方排行接口，'
        '可能存在披露延迟或口径差异。本页所有内容仅用于数据研究，不构成投资建议。</p>'
        '<p class="formula-links"><a href="' + prefix + 'elite' + suffix + '">查看绩优标的 →</a> · '
        '<a href="' + prefix + 'stocks' + suffix + '">查看股票排名 →</a> · '
        '<a href="' + prefix + 'funds' + suffix + '">查看基金排名 →</a></p>'
        '</div>'
    )
    return "".join(parts)


if __name__ == "__main__":
    print(render_formula_doc())

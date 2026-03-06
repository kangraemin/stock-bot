"""Grid search 결과 다관점 분석 HTML 리포트 생성"""

import json
import os
from collections import defaultdict
from html import escape

CACHE_DIR = os.path.join(os.path.dirname(__file__), "backtest", ".grid_cache")
OUTPUT = os.path.join(os.path.dirname(__file__), "analysis_report.html")

BASE_SYMS = ["SPY", "QQQ", "AAPL", "AMZN", "GOOGL", "MSFT", "NVDA", "TSLA"]
LEV_SYMS = ["TQQQ", "SOXL", "SPXL", "UPRO", "TECL"]


def load_all():
    all_data = {}
    for f in sorted(os.listdir(CACHE_DIR)):
        if not f.endswith(".json"):
            continue
        sym = f.replace(".json", "")
        with open(os.path.join(CACHE_DIR, f)) as fp:
            all_data[sym] = json.load(fp)
    return all_data


def flatten(all_data):
    flat = []
    for sym, data in all_data.items():
        for tf, tf_data in data.items():
            for period, period_data in tf_data.items():
                for fee, results in period_data.items():
                    for rank, r in enumerate(results):
                        flat.append({
                            "sym": sym, "tf": tf, "period": period,
                            "fee": fee, "rank": rank, **r,
                        })
    return flat


def fmt_pct(v):
    return f"{v * 100:.1f}%"


def fmt_f(v, d=2):
    return f"{v:.{d}f}"


def param_str(p):
    return (
        f"BB({p.get('bb_window')}/{p.get('bb_std')}), "
        f"RSI({p.get('rsi_window')}, {p.get('rsi_buy_threshold')}/{p.get('rsi_sell_threshold')}), "
        f"EMA({p.get('ema_window')})"
    )


def filter_str(p):
    f = []
    if p.get("ema_filter"): f.append("EMA")
    if p.get("macd_filter"): f.append("MACD")
    if p.get("volume_filter"): f.append("VOL")
    if p.get("adx_filter"): f.append("ADX")
    return "+".join(f) if f else "none"


def css():
    return """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0d1117; color: #c9d1d9; padding: 20px; }
        h1 { color: #58a6ff; font-size: 28px; margin: 30px 0 10px; border-bottom: 2px solid #30363d; padding-bottom: 10px; }
        h2 { color: #79c0ff; font-size: 20px; margin: 25px 0 10px; }
        h3 { color: #d2a8ff; font-size: 16px; margin: 15px 0 8px; }
        .summary { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin: 15px 0; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 15px; margin: 15px 0; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; }
        .card-title { color: #58a6ff; font-weight: bold; font-size: 16px; margin-bottom: 10px; }
        .highlight { background: #1f6feb22; border-color: #1f6feb; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }
        th { background: #21262d; color: #58a6ff; padding: 8px 10px; text-align: left;
             border-bottom: 2px solid #30363d; position: sticky; top: 0; }
        td { padding: 6px 10px; border-bottom: 1px solid #21262d; }
        tr:hover { background: #161b2266; }
        .pos { color: #3fb950; } .neg { color: #f85149; } .neutral { color: #8b949e; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin: 1px; }
        .badge-green { background: #238636; color: #fff; }
        .badge-blue { background: #1f6feb; color: #fff; }
        .badge-purple { background: #8957e5; color: #fff; }
        .badge-gray { background: #30363d; color: #8b949e; }
        .badge-red { background: #da3633; color: #fff; }
        .medal { font-size: 18px; }
        .insight { background: #1c2128; border-left: 3px solid #58a6ff; padding: 12px 15px; margin: 10px 0; font-size: 14px; }
        .warning { border-left-color: #d29922; }
        .danger { border-left-color: #f85149; }
        .nav { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; margin: 15px 0;
               position: sticky; top: 0; z-index: 100; }
        .nav a { color: #58a6ff; text-decoration: none; margin: 0 10px; font-size: 14px; }
        .nav a:hover { text-decoration: underline; }
        .bar { height: 8px; border-radius: 4px; display: inline-block; }
        .bar-container { background: #21262d; border-radius: 4px; width: 100%; height: 8px; display: inline-block; }
    </style>
    """


def build_report():
    all_data = load_all()
    flat = flatten(all_data)
    symbols = sorted(all_data.keys())

    # ── Analysis ──
    # 1. Best per symbol
    best_per_sym = {}
    for sym in symbols:
        recs = [r for r in flat if r["sym"] == sym]
        best_per_sym[sym] = max(recs, key=lambda x: x.get("sharpe_ratio", 0))

    # 2. Timeframe comparison
    tf_stats = defaultdict(list)
    for r in flat:
        if r["rank"] == 0:
            tf_stats[r["tf"]].append(r)

    # 3. Period comparison
    period_stats = defaultdict(list)
    for r in flat:
        if r["rank"] == 0:
            period_stats[r["period"]].append(r)

    # 4. Fee comparison
    fee_stats = defaultdict(list)
    for r in flat:
        if r["rank"] == 0:
            fee_stats[r["fee"]].append(r)

    # 5. Filter effectiveness
    filter_counts = defaultdict(lambda: {"wins": 0, "total_sharpe": 0, "count": 0})
    for r in flat:
        if r["rank"] == 0:
            p = r.get("params", {})
            for filt in ["ema_filter", "macd_filter", "volume_filter", "adx_filter"]:
                key = filt.replace("_filter", "").upper()
                if p.get(filt):
                    filter_counts[key]["count"] += 1
                    filter_counts[key]["total_sharpe"] += r.get("sharpe_ratio", 0)

    # 6. Base vs Leverage
    base_best = [best_per_sym[s] for s in BASE_SYMS if s in best_per_sym]
    lev_best = [best_per_sym[s] for s in LEV_SYMS if s in best_per_sym]

    # 7. Parameter frequency in top results
    param_freq = defaultdict(lambda: defaultdict(int))
    top1_records = [r for r in flat if r["rank"] == 0]
    for r in top1_records:
        p = r.get("params", {})
        for k, v in p.items():
            param_freq[k][str(v)] += 1

    # 8. Risk-adjusted ranking (Calmar)
    calmar_rank = sorted(
        [best_per_sym[s] for s in symbols],
        key=lambda x: x.get("calmar_ratio", 0), reverse=True
    )

    # 9. vs Buy&Hold analysis
    bh_winners = [r for r in best_per_sym.values() if r.get("vs_buyhold_excess", 0) > 0]
    bh_losers = [r for r in best_per_sym.values() if r.get("vs_buyhold_excess", 0) <= 0]

    # ── HTML ──
    parts = []
    parts.append(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Grid Search Analysis Report</title>{css()}</head><body>")

    # Navigation
    parts.append("""
    <div class='nav'>
        <a href='#overview'>Overview</a>
        <a href='#ranking'>Ranking</a>
        <a href='#symbols'>Symbol Detail</a>
        <a href='#base-vs-lev'>Base vs 3x</a>
        <a href='#timeframe'>Timeframe</a>
        <a href='#period'>Period</a>
        <a href='#fee'>Fee</a>
        <a href='#filters'>Filters</a>
        <a href='#params'>Param Patterns</a>
        <a href='#bh'>vs Buy&Hold</a>
        <a href='#risk'>Risk</a>
        <a href='#recommendation'>Recommendation</a>
    </div>
    """)

    # ═══ 1. Overview ═══
    parts.append("<h1 id='overview'>Overview</h1>")
    avg_sharpe = sum(r.get("sharpe_ratio", 0) for r in best_per_sym.values()) / len(best_per_sym)
    avg_return = sum(r.get("total_return", 0) for r in best_per_sym.values()) / len(best_per_sym)
    avg_mdd = sum(r.get("max_drawdown", 0) for r in best_per_sym.values()) / len(best_per_sym)
    bh_win_rate = len(bh_winners) / len(best_per_sym) * 100

    parts.append(f"""
    <div class='grid'>
        <div class='card'><div class='card-title'>Symbols Analyzed</div>
            <span style='font-size:36px;color:#58a6ff'>{len(symbols)}</span>
            <br><span class='neutral'>Base: {len([s for s in symbols if s in BASE_SYMS])} | 3x Lev: {len([s for s in symbols if s in LEV_SYMS])}</span></div>
        <div class='card'><div class='card-title'>Total Configs Tested</div>
            <span style='font-size:36px;color:#58a6ff'>{len(flat)}</span>
            <br><span class='neutral'>per symbol: {len(flat)//len(symbols)} (top5 x tf x period x fee)</span></div>
        <div class='card'><div class='card-title'>Avg Best Sharpe</div>
            <span style='font-size:36px;color:#3fb950'>{avg_sharpe:.2f}</span></div>
        <div class='card'><div class='card-title'>Avg Best Return</div>
            <span style='font-size:36px;color:#3fb950'>{fmt_pct(avg_return)}</span></div>
        <div class='card'><div class='card-title'>Avg Best MDD</div>
            <span style='font-size:36px;color:#f85149'>{fmt_pct(avg_mdd)}</span></div>
        <div class='card'><div class='card-title'>Beat Buy&Hold Rate</div>
            <span style='font-size:36px;color:{"#3fb950" if bh_win_rate > 50 else "#f85149"}'>{bh_win_rate:.0f}%</span>
            <br><span class='neutral'>{len(bh_winners)}/{len(best_per_sym)} symbols</span></div>
    </div>
    """)

    # ═══ 2. Overall Ranking ═══
    parts.append("<h1 id='ranking'>Overall Ranking</h1>")

    # By Sharpe
    parts.append("<h2>By Sharpe Ratio (Risk-Adjusted)</h2>")
    sharpe_rank = sorted(best_per_sym.values(), key=lambda x: x.get("sharpe_ratio", 0), reverse=True)
    parts.append("<table><tr><th>#</th><th>Symbol</th><th>Sharpe</th><th>Return</th><th>MDD</th><th>Calmar</th><th>Trades</th><th>vs B&H</th><th>Config</th><th>Params</th><th>Filters</th></tr>")
    medals = ["&#129351;", "&#129352;", "&#129353;"]
    for i, r in enumerate(sharpe_rank):
        p = r.get("params", {})
        medal = medals[i] if i < 3 else str(i + 1)
        vbh = r.get("vs_buyhold_excess", 0)
        vbh_cls = "pos" if vbh > 0 else "neg"
        sym_badge = "badge-purple" if r["sym"] in LEV_SYMS else "badge-blue"
        parts.append(f"""<tr>
            <td class='medal'>{medal}</td>
            <td><span class='badge {sym_badge}'>{r['sym']}</span></td>
            <td class='pos'><b>{fmt_f(r.get('sharpe_ratio',0))}</b></td>
            <td class='pos'>{fmt_pct(r.get('total_return',0))}</td>
            <td class='neg'>{fmt_pct(r.get('max_drawdown',0))}</td>
            <td>{fmt_f(r.get('calmar_ratio',0))}</td>
            <td>{r.get('total_trades',0)}</td>
            <td class='{vbh_cls}'>{fmt_pct(vbh)}</td>
            <td><span class='badge badge-gray'>{r['tf']}</span> <span class='badge badge-gray'>{r['period']}</span> <span class='badge badge-gray'>{r['fee']}</span></td>
            <td>{escape(param_str(p))}</td>
            <td><span class='badge badge-green'>{filter_str(p)}</span></td>
        </tr>""")
    parts.append("</table>")

    # By Return
    parts.append("<h2>By Total Return</h2>")
    ret_rank = sorted(best_per_sym.values(), key=lambda x: x.get("total_return", 0), reverse=True)
    parts.append("<table><tr><th>#</th><th>Symbol</th><th>Return</th><th>Sharpe</th><th>MDD</th><th>vs B&H</th><th>Config</th></tr>")
    for i, r in enumerate(ret_rank):
        vbh = r.get("vs_buyhold_excess", 0)
        parts.append(f"""<tr><td>{i+1}</td><td>{r['sym']}</td>
            <td class='pos'><b>{fmt_pct(r.get('total_return',0))}</b></td>
            <td>{fmt_f(r.get('sharpe_ratio',0))}</td>
            <td class='neg'>{fmt_pct(r.get('max_drawdown',0))}</td>
            <td class='{"pos" if vbh>0 else "neg"}'>{fmt_pct(vbh)}</td>
            <td>{r['tf']}/{r['period']}/{r['fee']}</td></tr>""")
    parts.append("</table>")

    # ═══ 3. Symbol Detail Cards ═══
    parts.append("<h1 id='symbols'>Symbol Detail</h1>")
    parts.append("<div class='grid'>")
    for sym in symbols:
        r = best_per_sym[sym]
        p = r.get("params", {})
        vbh = r.get("vs_buyhold_excess", 0)
        is_lev = sym in LEV_SYMS
        card_cls = "card highlight" if r.get("sharpe_ratio", 0) >= 3 else "card"
        parts.append(f"""
        <div class='{card_cls}'>
            <div class='card-title'>{sym} <span class='badge {"badge-purple" if is_lev else "badge-blue"}'>{"3x LEV" if is_lev else "BASE"}</span></div>
            <table>
                <tr><td>Return</td><td class='pos'><b>{fmt_pct(r.get('total_return',0))}</b></td></tr>
                <tr><td>Sharpe</td><td>{fmt_f(r.get('sharpe_ratio',0))}</td></tr>
                <tr><td>MDD</td><td class='neg'>{fmt_pct(r.get('max_drawdown',0))}</td></tr>
                <tr><td>Calmar</td><td>{fmt_f(r.get('calmar_ratio',0))}</td></tr>
                <tr><td>Trades</td><td>{r.get('total_trades',0)}</td></tr>
                <tr><td>vs B&H</td><td class='{"pos" if vbh>0 else "neg"}'>{fmt_pct(vbh)}</td></tr>
                <tr><td>Config</td><td>{r['tf']} / {r['period']} / {r['fee']}</td></tr>
                <tr><td>Params</td><td style='font-size:12px'>{escape(param_str(p))}</td></tr>
                <tr><td>Filters</td><td><span class='badge badge-green'>{filter_str(p)}</span></td></tr>
            </table>
        </div>""")
    parts.append("</div>")

    # ═══ 4. Base vs Leverage ═══
    parts.append("<h1 id='base-vs-lev'>Base vs 3x Leveraged</h1>")
    if base_best and lev_best:
        avg_b_sharpe = sum(r.get("sharpe_ratio",0) for r in base_best) / len(base_best)
        avg_l_sharpe = sum(r.get("sharpe_ratio",0) for r in lev_best) / len(lev_best)
        avg_b_ret = sum(r.get("total_return",0) for r in base_best) / len(base_best)
        avg_l_ret = sum(r.get("total_return",0) for r in lev_best) / len(lev_best)
        avg_b_mdd = sum(r.get("max_drawdown",0) for r in base_best) / len(base_best)
        avg_l_mdd = sum(r.get("max_drawdown",0) for r in lev_best) / len(lev_best)
        avg_b_bh = sum(r.get("vs_buyhold_excess",0) for r in base_best) / len(base_best)
        avg_l_bh = sum(r.get("vs_buyhold_excess",0) for r in lev_best) / len(lev_best)

        parts.append(f"""
        <table>
            <tr><th>Metric</th><th>Base ({len(base_best)})</th><th>3x Leveraged ({len(lev_best)})</th><th>Winner</th></tr>
            <tr><td>Avg Sharpe</td><td>{fmt_f(avg_b_sharpe)}</td><td>{fmt_f(avg_l_sharpe)}</td>
                <td class='pos'>{'3x LEV' if avg_l_sharpe > avg_b_sharpe else 'BASE'}</td></tr>
            <tr><td>Avg Return</td><td>{fmt_pct(avg_b_ret)}</td><td>{fmt_pct(avg_l_ret)}</td>
                <td class='pos'>{'3x LEV' if avg_l_ret > avg_b_ret else 'BASE'}</td></tr>
            <tr><td>Avg MDD</td><td class='neg'>{fmt_pct(avg_b_mdd)}</td><td class='neg'>{fmt_pct(avg_l_mdd)}</td>
                <td class='pos'>{'BASE' if avg_b_mdd > avg_l_mdd else '3x LEV'}</td></tr>
            <tr><td>Avg vs B&H</td><td class='{"pos" if avg_b_bh>0 else "neg"}'>{fmt_pct(avg_b_bh)}</td>
                <td class='{"pos" if avg_l_bh>0 else "neg"}'>{fmt_pct(avg_l_bh)}</td>
                <td class='pos'>{'3x LEV' if avg_l_bh > avg_b_bh else 'BASE'}</td></tr>
        </table>""")

        if avg_l_sharpe > avg_b_sharpe and avg_l_bh > avg_b_bh:
            parts.append("<div class='insight'>3x 레버리지 종목이 Sharpe, vs B&H 모두 우위. 전략 적용 시 레버리지 종목이 더 효과적.</div>")
        elif avg_b_mdd > avg_l_mdd:
            parts.append("<div class='insight warning'>3x 레버리지가 수익은 높지만 MDD도 큼. 리스크 허용 범위 확인 필요.</div>")

    # ═══ 5. Timeframe ═══
    parts.append("<h1 id='timeframe'>Timeframe Analysis (Daily vs Weekly)</h1>")
    parts.append("<table><tr><th>Timeframe</th><th>Avg Sharpe</th><th>Avg Return</th><th>Avg MDD</th><th>Configs</th></tr>")
    for tf in ["daily", "weekly"]:
        recs = tf_stats.get(tf, [])
        if not recs:
            continue
        avg_s = sum(r.get("sharpe_ratio",0) for r in recs) / len(recs)
        avg_r = sum(r.get("total_return",0) for r in recs) / len(recs)
        avg_m = sum(r.get("max_drawdown",0) for r in recs) / len(recs)
        parts.append(f"<tr><td><b>{tf}</b></td><td>{fmt_f(avg_s)}</td><td>{fmt_pct(avg_r)}</td><td class='neg'>{fmt_pct(avg_m)}</td><td>{len(recs)}</td></tr>")
    parts.append("</table>")

    # Which TF wins per symbol?
    parts.append("<h3>Best Timeframe per Symbol</h3>")
    parts.append("<table><tr><th>Symbol</th><th>Best TF</th><th>Sharpe</th></tr>")
    for sym in symbols:
        recs = [r for r in flat if r["sym"] == sym and r["rank"] == 0]
        daily_best = max([r for r in recs if r["tf"] == "daily"], key=lambda x: x.get("sharpe_ratio",0), default=None)
        weekly_best = max([r for r in recs if r["tf"] == "weekly"], key=lambda x: x.get("sharpe_ratio",0), default=None)
        if daily_best and weekly_best:
            winner = "weekly" if weekly_best.get("sharpe_ratio",0) > daily_best.get("sharpe_ratio",0) else "daily"
            s = max(daily_best.get("sharpe_ratio",0), weekly_best.get("sharpe_ratio",0))
            parts.append(f"<tr><td>{sym}</td><td><span class='badge badge-blue'>{winner}</span></td><td>{fmt_f(s)}</td></tr>")
    parts.append("</table>")

    # ═══ 6. Period ═══
    parts.append("<h1 id='period'>Period Analysis</h1>")
    parts.append("<table><tr><th>Period</th><th>Avg Sharpe</th><th>Avg Return</th><th>Avg MDD</th><th>Configs</th></tr>")
    for period in ["1y", "3y", "5y"]:
        recs = period_stats.get(period, [])
        if not recs:
            continue
        avg_s = sum(r.get("sharpe_ratio",0) for r in recs) / len(recs)
        avg_r = sum(r.get("total_return",0) for r in recs) / len(recs)
        avg_m = sum(r.get("max_drawdown",0) for r in recs) / len(recs)
        parts.append(f"<tr><td><b>{period}</b></td><td>{fmt_f(avg_s)}</td><td>{fmt_pct(avg_r)}</td><td class='neg'>{fmt_pct(avg_m)}</td><td>{len(recs)}</td></tr>")
    parts.append("</table>")

    # ═══ 7. Fee ═══
    parts.append("<h1 id='fee'>Fee Model Comparison</h1>")
    parts.append("<table><tr><th>Fee</th><th>Avg Sharpe</th><th>Avg Return</th><th>Avg MDD</th></tr>")
    for fee in ["standard", "event"]:
        recs = fee_stats.get(fee, [])
        if not recs:
            continue
        avg_s = sum(r.get("sharpe_ratio",0) for r in recs) / len(recs)
        avg_r = sum(r.get("total_return",0) for r in recs) / len(recs)
        avg_m = sum(r.get("max_drawdown",0) for r in recs) / len(recs)
        parts.append(f"<tr><td><b>{fee}</b></td><td>{fmt_f(avg_s)}</td><td>{fmt_pct(avg_r)}</td><td class='neg'>{fmt_pct(avg_m)}</td></tr>")
    parts.append("</table>")

    # ═══ 8. Filter Effectiveness ═══
    parts.append("<h1 id='filters'>Filter Effectiveness</h1>")
    parts.append("<p>Top-1 결과에서 각 필터가 켜져 있을 때의 평균 Sharpe</p>")
    parts.append("<table><tr><th>Filter</th><th>Used Count</th><th>Avg Sharpe</th></tr>")
    for filt in ["EMA", "MACD", "VOL", "ADX"]:
        fc = filter_counts[filt]
        avg_s = fc["total_sharpe"] / fc["count"] if fc["count"] > 0 else 0
        parts.append(f"<tr><td><span class='badge badge-green'>{filt}</span></td><td>{fc['count']}</td><td>{fmt_f(avg_s)}</td></tr>")
    parts.append("</table>")

    # Filter combos in best results
    parts.append("<h3>Best Results Filter Combos</h3>")
    combo_stats = defaultdict(lambda: {"count": 0, "sharpe_sum": 0})
    for r in best_per_sym.values():
        fs = filter_str(r.get("params", {}))
        combo_stats[fs]["count"] += 1
        combo_stats[fs]["sharpe_sum"] += r.get("sharpe_ratio", 0)
    parts.append("<table><tr><th>Filter Combo</th><th>Count</th><th>Avg Sharpe</th></tr>")
    for combo, stats in sorted(combo_stats.items(), key=lambda x: x[1]["sharpe_sum"]/max(x[1]["count"],1), reverse=True):
        avg = stats["sharpe_sum"] / stats["count"]
        parts.append(f"<tr><td><span class='badge badge-green'>{combo}</span></td><td>{stats['count']}</td><td>{fmt_f(avg)}</td></tr>")
    parts.append("</table>")

    # ═══ 9. Parameter Patterns ═══
    parts.append("<h1 id='params'>Optimal Parameter Patterns</h1>")
    parts.append("<p>Top-1 결과에서 각 파라미터 값의 빈도 (가장 자주 최적으로 선택된 값)</p>")
    display_params = ["bb_window", "bb_std", "rsi_window", "ema_window", "rsi_buy_threshold", "rsi_sell_threshold"]
    for param in display_params:
        parts.append(f"<h3>{param}</h3>")
        freq = param_freq[param]
        total_c = sum(freq.values())
        parts.append("<table><tr><th>Value</th><th>Count</th><th>Ratio</th><th>Bar</th></tr>")
        for val, cnt in sorted(freq.items(), key=lambda x: x[1], reverse=True):
            pct = cnt / total_c * 100
            bar_w = int(pct * 3)
            parts.append(f"<tr><td><b>{val}</b></td><td>{cnt}</td><td>{pct:.0f}%</td>"
                         f"<td><div class='bar-container'><div class='bar' style='width:{bar_w}px;background:#58a6ff'></div></div></td></tr>")
        parts.append("</table>")

    # ═══ 10. vs Buy & Hold ═══
    parts.append("<h1 id='bh'>vs Buy & Hold Analysis</h1>")
    parts.append(f"<div class='insight'>전략이 Buy&Hold를 이긴 종목: <b>{len(bh_winners)}/{len(best_per_sym)}</b></div>")

    parts.append("<h3>Beat Buy&Hold</h3>")
    parts.append("<table><tr><th>Symbol</th><th>Strategy Return</th><th>Excess vs B&H</th><th>Sharpe</th></tr>")
    for r in sorted(bh_winners, key=lambda x: x.get("vs_buyhold_excess",0), reverse=True):
        parts.append(f"<tr><td>{r['sym']}</td><td class='pos'>{fmt_pct(r.get('total_return',0))}</td>"
                     f"<td class='pos'><b>+{fmt_pct(r.get('vs_buyhold_excess',0))}</b></td>"
                     f"<td>{fmt_f(r.get('sharpe_ratio',0))}</td></tr>")
    parts.append("</table>")

    if bh_losers:
        parts.append("<h3>Lost to Buy&Hold</h3>")
        parts.append("<div class='insight danger'>아래 종목은 그냥 존버가 나음. 전략이 B&H를 못 이김.</div>")
        parts.append("<table><tr><th>Symbol</th><th>Strategy Return</th><th>vs B&H</th></tr>")
        for r in sorted(bh_losers, key=lambda x: x.get("vs_buyhold_excess",0)):
            parts.append(f"<tr><td>{r['sym']}</td><td>{fmt_pct(r.get('total_return',0))}</td>"
                         f"<td class='neg'><b>{fmt_pct(r.get('vs_buyhold_excess',0))}</b></td></tr>")
        parts.append("</table>")

    # ═══ 11. Risk Analysis ═══
    parts.append("<h1 id='risk'>Risk Analysis</h1>")
    parts.append("<h2>By Calmar Ratio (Return / MDD)</h2>")
    parts.append("<table><tr><th>#</th><th>Symbol</th><th>Calmar</th><th>Return</th><th>MDD</th><th>Sharpe</th></tr>")
    for i, r in enumerate(calmar_rank):
        parts.append(f"<tr><td>{i+1}</td><td>{r['sym']}</td><td><b>{fmt_f(r.get('calmar_ratio',0))}</b></td>"
                     f"<td class='pos'>{fmt_pct(r.get('total_return',0))}</td>"
                     f"<td class='neg'>{fmt_pct(r.get('max_drawdown',0))}</td>"
                     f"<td>{fmt_f(r.get('sharpe_ratio',0))}</td></tr>")
    parts.append("</table>")

    # MDD danger zone
    danger = [r for r in best_per_sym.values() if r.get("max_drawdown", 0) < -0.25]
    if danger:
        parts.append("<div class='insight danger'>MDD -25% 초과 종목: " +
                     ", ".join(f"<b>{r['sym']}</b>({fmt_pct(r.get('max_drawdown',0))})" for r in danger) +
                     " — 레버리지 리스크 주의</div>")

    # ═══ 12. Final Recommendation ═══
    parts.append("<h1 id='recommendation'>Final Recommendation</h1>")

    # Score: sharpe * 0.4 + calmar * 0.3 + (1 if vs_bh > 0 else 0) * 0.3
    scored = []
    max_sharpe = max(r.get("sharpe_ratio",0.01) for r in best_per_sym.values())
    max_calmar = max(r.get("calmar_ratio",0.01) for r in best_per_sym.values())
    for sym, r in best_per_sym.items():
        s_norm = r.get("sharpe_ratio", 0) / max_sharpe if max_sharpe else 0
        c_norm = r.get("calmar_ratio", 0) / max_calmar if max_calmar else 0
        bh_bonus = 1 if r.get("vs_buyhold_excess", 0) > 0 else 0
        score = s_norm * 0.4 + c_norm * 0.3 + bh_bonus * 0.3
        scored.append({"sym": sym, "score": score, **r})
    scored.sort(key=lambda x: x["score"], reverse=True)

    parts.append("<div class='summary'>")
    parts.append("<h2>Bot Trading Recommendation Score</h2>")
    parts.append("<p>Score = Sharpe(40%) + Calmar(30%) + Beat B&H Bonus(30%)</p>")
    parts.append("<table><tr><th>#</th><th>Symbol</th><th>Score</th><th>Sharpe</th><th>Calmar</th><th>Return</th><th>MDD</th><th>vs B&H</th><th>Best Config</th><th>Filters</th></tr>")
    for i, r in enumerate(scored):
        p = r.get("params", {})
        vbh = r.get("vs_buyhold_excess", 0)
        star = " &#11088;" if i < 3 else ""
        parts.append(f"""<tr style='{"background:#1f6feb11" if i < 3 else ""}'>
            <td><b>{i+1}</b>{star}</td>
            <td><b>{r['sym']}</b></td>
            <td><b>{r['score']:.2f}</b></td>
            <td>{fmt_f(r.get('sharpe_ratio',0))}</td>
            <td>{fmt_f(r.get('calmar_ratio',0))}</td>
            <td class='pos'>{fmt_pct(r.get('total_return',0))}</td>
            <td class='neg'>{fmt_pct(r.get('max_drawdown',0))}</td>
            <td class='{"pos" if vbh>0 else "neg"}'>{fmt_pct(vbh)}</td>
            <td>{r['tf']}/{r['period']}/{r['fee']}</td>
            <td><span class='badge badge-green'>{filter_str(p)}</span></td>
        </tr>""")
    parts.append("</table></div>")

    # Top 3 summary
    top3 = scored[:3]
    parts.append("<div class='grid'>")
    for i, r in enumerate(top3):
        p = r.get("params", {})
        parts.append(f"""
        <div class='card highlight'>
            <div class='card-title'>{'&#129351;' if i==0 else '&#129352;' if i==1 else '&#129353;'} {r['sym']} (Score: {r['score']:.2f})</div>
            <div class='insight'>
                <b>Config:</b> {r['tf']} / {r['period']} / {r['fee']}<br>
                <b>Params:</b> {escape(param_str(p))}<br>
                <b>Filters:</b> {filter_str(p)}<br>
                <b>Return:</b> {fmt_pct(r.get('total_return',0))} | <b>Sharpe:</b> {fmt_f(r.get('sharpe_ratio',0))} | <b>MDD:</b> {fmt_pct(r.get('max_drawdown',0))} | <b>vs B&H:</b> {fmt_pct(r.get('vs_buyhold_excess',0))}
            </div>
        </div>""")
    parts.append("</div>")

    parts.append("<div style='text-align:center;color:#484f58;margin:40px 0;font-size:12px'>Generated by stock-bot grid search analyzer</div>")
    parts.append("</body></html>")

    html = "\n".join(parts)
    with open(OUTPUT, "w") as f:
        f.write(html)
    print(f"Report generated: {OUTPUT} ({len(html)//1024}KB)")


if __name__ == "__main__":
    build_report()

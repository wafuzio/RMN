#!/usr/bin/env python3
"""
report_server.py — Interactive scraper run report web app.

Serves a dark-themed dashboard with:
  - Period selector: Day / Week / Month + date picker
  - Retailer filter: All / Amazon / Walmart / Target / Instacart / Kroger
  - Overview cards (total, successful, failed)
  - Bar chart: runs per day coloured by retailer
  - By-retailer table with ad-type breakdown
  - Schedule detail table (collapsible per retailer)

Usage:
    python3 tools/report_server.py            # http://localhost:5050
    python3 tools/report_server.py --port 5051
"""

import argparse
import json
import sys
import os
from datetime import date, timedelta
from pathlib import Path

# Ensure tools/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, jsonify, render_template_string, request
from daily_report import (
    RETAILERS, build_report, build_report_range, available_date_range
)

app = Flask(__name__)

# ── HTML template ──────────────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Scraper Report</title>
<style>
:root {
  --bg:#0f1117; --surface:#1a1d27; --surface2:#21253a; --border:#2d2f3e;
  --text:#e2e4ef; --muted:#8b8fa8; --accent:#5b8cff; --accent2:#7c6fff;
  --ok:#3ecf8e; --warn:#f59e0b; --fail:#f87171; --miss:#6b7280;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font:14px/1.6 'Inter',system-ui,sans-serif;min-height:100vh;}
a{color:var(--accent);text-decoration:none;}

/* ── Top bar ── */
.topbar{background:var(--surface);border-bottom:1px solid var(--border);
        padding:12px 28px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;}
.topbar h1{font-size:16px;font-weight:700;color:var(--accent);white-space:nowrap;}
.topbar .spacer{flex:1;}

/* ── Controls ── */
.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.seg{display:flex;border:1px solid var(--border);border-radius:6px;overflow:hidden;}
.seg button{background:transparent;border:none;color:var(--muted);padding:6px 14px;
            cursor:pointer;font-size:13px;transition:background .15s,color .15s;}
.seg button.active{background:var(--accent);color:#fff;}
.seg button:hover:not(.active){background:var(--surface2);}

select,input[type=date]{background:var(--surface2);border:1px solid var(--border);
  color:var(--text);border-radius:6px;padding:5px 10px;font-size:13px;outline:none;}
select:focus,input[type=date]:focus{border-color:var(--accent);}

/* ── Main layout ── */
.main{padding:24px 28px;display:flex;flex-direction:column;gap:24px;}

/* ── Cards ── */
.cards{display:flex;gap:14px;flex-wrap:wrap;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
      padding:18px 22px;min-width:130px;flex:1;max-width:200px;}
.card .val{font-size:30px;font-weight:700;line-height:1.1;}
.card .lbl{font-size:12px;color:var(--muted);margin-top:3px;}
.card.ok .val{color:var(--ok);}
.card.fail .val{color:var(--fail);}
.card.pct .val{color:var(--accent);}

/* ── Chart ── */
.chart-wrap{background:var(--surface);border:1px solid var(--border);border-radius:10px;
            padding:18px 20px;}
.chart-wrap h2{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;
               letter-spacing:.07em;margin-bottom:14px;}
#chart{width:100%;height:180px;}

/* ── Tables ── */
.section{background:var(--surface);border:1px solid var(--border);border-radius:10px;
         padding:0;overflow:hidden;}
.section-hdr{padding:14px 18px;border-bottom:1px solid var(--border);
             font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;
             letter-spacing:.07em;display:flex;align-items:center;gap:8px;}
table{width:100%;border-collapse:collapse;font-size:13px;}
th{text-align:left;padding:9px 14px;color:var(--muted);font-weight:500;
   background:var(--surface2);border-bottom:1px solid var(--border);white-space:nowrap;}
td{padding:8px 14px;border-bottom:1px solid var(--border);vertical-align:top;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:rgba(255,255,255,.02);}
.rname{font-weight:600;text-transform:capitalize;}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
.num.ok{color:var(--ok);}
.num.fail{color:var(--fail);}
.num.warn{color:var(--warn);}
.time{font-variant-numeric:tabular-nums;font-family:monospace;font-size:12px;}
.tag{display:inline-block;background:#2a2d3e;border:1px solid var(--border);
     border-radius:4px;padding:1px 6px;font-size:11px;margin:1px 1px 1px 0;}
.tag b{color:var(--accent);}
.badge{display:inline-block;border-radius:4px;padding:2px 8px;font-size:11px;
       font-weight:600;white-space:nowrap;}
.badge.ok  {background:#0d2e1e;color:var(--ok);}
.badge.warn{background:#2e1f08;color:var(--warn);}
.badge.fail{background:#2e0f0f;color:var(--fail);}
.badge.miss{background:#1e2030;color:var(--miss);}
.none{color:var(--miss);}

/* ── Detail section ── */
.retailer-block{}
.retailer-hdr{padding:10px 18px;background:var(--surface2);border-bottom:1px solid var(--border);
              font-size:12px;font-weight:700;text-transform:uppercase;color:var(--accent2);
              letter-spacing:.08em;cursor:pointer;display:flex;align-items:center;gap:8px;}
.retailer-hdr .arrow{transition:transform .2s;font-size:10px;}
.retailer-hdr.collapsed .arrow{transform:rotate(-90deg);}
.retailer-body{overflow:hidden;transition:max-height .25s ease;}
.retailer-body.collapsed{max-height:0 !important;}

/* ── Loading overlay ── */
#loading{position:fixed;inset:0;background:rgba(15,17,23,.85);display:flex;
         align-items:center;justify-content:center;z-index:100;font-size:15px;
         color:var(--muted);gap:12px;}
#loading.hidden{display:none;}
.spinner{width:22px;height:22px;border:3px solid var(--border);
         border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<div id="loading"><div class="spinner"></div> Loading…</div>

<div class="topbar">
  <h1>Scraper Report</h1>
  <div class="controls">
    <div class="seg" id="periodSeg">
      <button data-p="day"   class="active">Day</button>
      <button data-p="week"  >Week</button>
      <button data-p="month" >Month</button>
    </div>
    <input type="date" id="datePick">
    <select id="retailerPick">
      <option value="">All Retailers</option>
      <option value="amazon">Amazon</option>
      <option value="walmart">Walmart</option>
      <option value="target">Target</option>
      <option value="instacart">Instacart</option>
      <option value="kroger">Kroger</option>
    </select>
  </div>
  <div class="spacer"></div>
  <span id="periodLabel" style="color:var(--muted);font-size:13px;"></span>
</div>

<div class="main">
  <!-- Overview cards -->
  <div class="cards" id="cards"></div>

  <!-- Daily bar chart -->
  <div class="chart-wrap">
    <h2>Runs per Day</h2>
    <canvas id="chart"></canvas>
  </div>

  <!-- By retailer -->
  <div class="section">
    <div class="section-hdr">By Retailer</div>
    <table id="retailerTable">
      <thead><tr>
        <th>Retailer</th><th class="num">Total</th>
        <th class="num">OK</th><th class="num">Empty/Failed</th>
        <th>Ad Types Captured</th>
      </tr></thead>
      <tbody id="retailerBody"></tbody>
    </table>
  </div>

  <!-- Schedule detail -->
  <div class="section">
    <div class="section-hdr">Schedule Detail</div>
    <div id="scheduleDetail"></div>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let period   = 'day';
let retailer = '';
let dateVal  = new Date().toISOString().slice(0,10);
// Default to yesterday
const yest = new Date(); yest.setDate(yest.getDate()-1);
dateVal = yest.toISOString().slice(0,10);

// ── Controls init ──────────────────────────────────────────────────────────
document.getElementById('datePick').value = dateVal;
document.getElementById('datePick').max   = new Date().toISOString().slice(0,10);

document.querySelectorAll('#periodSeg button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#periodSeg button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    period = btn.dataset.p;
    load();
  });
});
document.getElementById('datePick').addEventListener('change', e => {
  dateVal = e.target.value;
  load();
});
document.getElementById('retailerPick').addEventListener('change', e => {
  retailer = e.target.value;
  load();
});

// ── Fetch & render ─────────────────────────────────────────────────────────
function load() {
  document.getElementById('loading').classList.remove('hidden');
  const params = new URLSearchParams({period, date: dateVal, retailer});
  fetch('/api/report?' + params)
    .then(r => r.json())
    .then(data => { render(data); document.getElementById('loading').classList.add('hidden'); })
    .catch(() => document.getElementById('loading').classList.add('hidden'));
}

function render(d) {
  document.getElementById('periodLabel').textContent = d.day_name;

  // ── Cards ──
  const pct = d.total ? Math.round(d.successful*100/d.total) : 0;
  document.getElementById('cards').innerHTML = `
    <div class="card"><div class="val">${d.total}</div><div class="lbl">Total Runs</div></div>
    <div class="card ok"><div class="val">${d.successful}</div><div class="lbl">Successful</div></div>
    <div class="card fail"><div class="val">${d.failed}</div><div class="lbl">Failed / Empty</div></div>
    <div class="card pct"><div class="val">${pct}%</div><div class="lbl">Success Rate</div></div>
  `;

  // ── Chart ──
  renderChart(d.daily_series);

  // ── Retailer table ──
  const RETAILERS = ['amazon','walmart','target','instacart','kroger'];
  let rows = '';
  for (const r of RETAILERS) {
    const rv = d.by_retailer[r];
    if (!rv) continue;
    const tot = rv.success + rv.failed;
    const at  = rv.ad_types || {};
    const atHtml = Object.entries(at).sort().map(([k,v]) =>
      `<span class="tag">${k} <b>${v}</b></span>`).join('') || '<span class="none">—</span>';
    rows += `<tr>
      <td class="rname">${r}</td>
      <td class="num">${tot}</td>
      <td class="num ok">${rv.success}</td>
      <td class="num fail">${rv.failed}</td>
      <td>${atHtml}</td>
    </tr>`;
  }
  document.getElementById('retailerBody').innerHTML = rows || '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:20px">No data</td></tr>';

  // ── Schedule detail ──
  renderDetail(d);
}

// ── Chart (pure canvas, no lib dep) ───────────────────────────────────────
const RETAILER_COLORS = {
  amazon:'#5b8cff', walmart:'#3ecf8e', target:'#f87171',
  instacart:'#f59e0b', kroger:'#a78bfa', unknown:'#6b7280'
};

let chartState = null;
function renderChart(series) {
  const canvas = document.getElementById('chart');
  const ctx    = canvas.getContext('2d');
  const dates  = Object.keys(series).sort();
  if (!dates.length) { ctx.clearRect(0,0,canvas.width,canvas.height); return; }

  // Collect retailers present
  const retailersPresent = new Set();
  for (const d of Object.values(series))
    for (const r of Object.keys(d.by_retailer||{})) retailersPresent.add(r);
  const rets = [...retailersPresent].sort();

  // Size canvas
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.parentElement.clientWidth - 40;
  const H = 180;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width  = W + 'px';
  canvas.style.height = H + 'px';
  ctx.scale(dpr, dpr);
  ctx.clearRect(0,0,W,H);

  const PAD = {l:36, r:12, t:10, b:36};
  const chartW = W - PAD.l - PAD.r;
  const chartH = H - PAD.t - PAD.b;

  // Max value
  let maxVal = 1;
  for (const d of Object.values(series)) if (d.total > maxVal) maxVal = d.total;
  maxVal = Math.ceil(maxVal * 1.1) || 1;

  const barW  = Math.max(4, Math.floor(chartW / dates.length) - 2);
  const gap   = Math.max(1, Math.floor((chartW - barW * dates.length) / (dates.length + 1)));

  // Y grid
  ctx.strokeStyle = '#2d2f3e'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = PAD.t + chartH - (i/4) * chartH;
    ctx.beginPath(); ctx.moveTo(PAD.l, y); ctx.lineTo(PAD.l + chartW, y); ctx.stroke();
    ctx.fillStyle = '#8b8fa8'; ctx.font = '10px sans-serif'; ctx.textAlign = 'right';
    ctx.fillText(Math.round(maxVal * i / 4), PAD.l - 4, y + 3);
  }

  // Bars (stacked by retailer)
  dates.forEach((dt, i) => {
    const d   = series[dt];
    const x   = PAD.l + gap + i * (barW + gap);
    let   yOff = 0;

    for (const ret of rets) {
      const rv  = (d.by_retailer||{})[ret];
      if (!rv) continue;
      const tot = rv.success + rv.failed;
      if (!tot) continue;
      const bh  = Math.max(2, (tot / maxVal) * chartH);
      const y   = PAD.t + chartH - yOff - bh;
      ctx.fillStyle = RETAILER_COLORS[ret] || '#6b7280';
      ctx.fillRect(x, y, barW, bh);
      yOff += bh;
    }

    // X label (show every Nth)
    const nth = dates.length > 14 ? 7 : dates.length > 7 ? 2 : 1;
    if (i % nth === 0) {
      ctx.fillStyle = '#8b8fa8'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
      const label = dt.slice(5); // MM-DD
      ctx.fillText(label, x + barW/2, PAD.t + chartH + 16);
    }
  });

  // Legend
  let lx = PAD.l;
  for (const ret of rets) {
    ctx.fillStyle = RETAILER_COLORS[ret] || '#6b7280';
    ctx.fillRect(lx, H - 8, 10, 8);
    ctx.fillStyle = '#8b8fa8'; ctx.font = '10px sans-serif'; ctx.textAlign = 'left';
    ctx.fillText(ret, lx + 13, H - 1);
    lx += ctx.measureText(ret).width + 28;
  }
}

// ── Schedule detail ────────────────────────────────────────────────────────
function renderDetail(d) {
  const container = document.getElementById('scheduleDetail');
  const rows = d.schedule_rows || [];
  if (!rows.length) {
    container.innerHTML = '<div style="padding:20px;color:var(--muted);text-align:center">No scheduled runs for this period</div>';
    return;
  }

  // Group by retailer
  const byRet = {};
  for (const row of rows) {
    (byRet[row.retailer] = byRet[row.retailer]||[]).push(row);
  }

  const isRange = d.date !== d.date_end;

  let html = '';
  for (const [ret, retRows] of Object.entries(byRet).sort()) {
    html += `<div class="retailer-block">
      <div class="retailer-hdr" onclick="toggleBlock(this)">
        <span class="arrow">▼</span> ${ret.toUpperCase()}
        <span style="color:var(--muted);font-weight:400;font-size:11px;margin-left:4px">(${retRows.length} schedules)</span>
      </div>
      <div class="retailer-body">`;

    if (isRange) {
      html += `<table><thead><tr>
        <th>Client</th><th>Keyword</th><th>Times/Day</th>
        <th class="num">Expected</th><th class="num ok">OK</th>
        <th class="num warn">Empty</th><th class="num fail">Missing</th>
        <th>Ad Types</th>
      </tr></thead><tbody>`;
      for (const row of retRows) {
        const atHtml = Object.entries(row.ad_types||{}).sort().map(([k,v]) =>
          `<span class="tag">${k} <b>${v}</b></span>`).join('') || '<span class="none">—</span>';
        const missClass = row.missing > 0 ? 'fail' : 'ok';
        html += `<tr>
          <td>${row.client}</td>
          <td>${row.keyword || '<em>all</em>'}</td>
          <td class="time">${row.times.join(', ')}</td>
          <td class="num">${row.expected}</td>
          <td class="num ok">${row.ok}</td>
          <td class="num warn">${row.empty}</td>
          <td class="num ${missClass}">${row.missing}</td>
          <td>${atHtml}</td>
        </tr>`;
      }
      html += '</tbody></table>';
    } else {
      html += `<table><thead><tr>
        <th>Client</th><th>Keyword</th>
        <th>Scheduled</th><th>Actual</th>
        <th>Status</th><th>Ad Types</th>
      </tr></thead><tbody>`;
      for (const row of retRows) {
        for (const sl of row.slots) {
          const badge = statusBadge(sl.status);
          const atHtml = Object.entries(sl.ad_types||{}).sort().map(([k,v]) =>
            `<span class="tag">${k} <b>${v}</b></span>`).join('') || '';
          html += `<tr class="row-${sl.status}">
            <td>${row.client}</td>
            <td>${row.keyword||'<em>all</em>'}</td>
            <td class="time">${sl.scheduled||'—'}</td>
            <td class="time">${sl.actual||'—'}</td>
            <td>${badge}</td>
            <td>${atHtml}</td>
          </tr>`;
        }
      }
      html += '</tbody></table>';
    }
    html += '</div></div>';
  }
  container.innerHTML = html;

  // Auto-set max-height on expanded blocks
  container.querySelectorAll('.retailer-body').forEach(b => {
    b.style.maxHeight = b.scrollHeight + 'px';
  });
}

function statusBadge(s) {
  const map = {
    ok:                '<span class="badge ok">✅ ok</span>',
    empty:             '<span class="badge warn">⚠ empty</span>',
    failed:            '<span class="badge fail">✗ failed</span>',
    missing:           '<span class="badge miss">— missing</span>',
    unscheduled_ok:    '<span class="badge ok">✅ extra</span>',
    unscheduled_empty: '<span class="badge warn">⚠ extra</span>',
  };
  return map[s] || s;
}

function toggleBlock(hdr) {
  hdr.classList.toggle('collapsed');
  const body = hdr.nextElementSibling;
  body.classList.toggle('collapsed');
  if (!body.classList.contains('collapsed'))
    body.style.maxHeight = body.scrollHeight + 'px';
}

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('resize', () => {
  // re-render chart on resize
  if (window._lastData) renderChart(window._lastData.daily_series);
});
const _origRender = render;
window.render = function(d) { window._lastData = d; _origRender(d); };

load();
</script>
</body>
</html>"""


# ── API endpoint ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(TEMPLATE)


@app.route("/api/report")
def api_report():
    period_param   = request.args.get("period", "day")
    date_param     = request.args.get("date", "")
    retailer_param = request.args.get("retailer", "").strip().lower()

    try:
        base = date.fromisoformat(date_param) if date_param else date.today() - timedelta(days=1)
    except ValueError:
        base = date.today() - timedelta(days=1)

    if period_param == "week":
        # Mon–Sun of the week containing base
        start = base - timedelta(days=base.weekday())
        end   = start + timedelta(days=6)
    elif period_param == "month":
        start = base.replace(day=1)
        # last day of month
        if start.month == 12:
            end = start.replace(day=31)
        else:
            end = (start.replace(month=start.month+1) - timedelta(days=1))
    else:
        start = end = base

    if start == end:
        report = build_report(start)
        if retailer_param:
            report["by_retailer"] = {k: v for k, v in report["by_retailer"].items()
                                     if k == retailer_param}
            report["schedule_rows"] = [r for r in report["schedule_rows"]
                                       if r["retailer"] == retailer_param]
            filtered = [r for r in (report.get("log_failures") or [])
                        if r["retailer"] == retailer_param]
            report["log_failures"] = filtered
    else:
        report = build_report_range(start, end, retailer_filter=retailer_param)

    # Make Counter objects JSON-serialisable
    def fix(obj):
        if hasattr(obj, "items"):
            return {k: fix(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fix(i) for i in obj]
        return obj

    return jsonify(fix(report))


@app.route("/api/dates")
def api_dates():
    earliest, latest = available_date_range()
    return jsonify({"earliest": earliest.isoformat(), "latest": latest.isoformat()})


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper report web server")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"Report server → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)

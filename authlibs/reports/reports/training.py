#!/usr/bin/python3
"""
training.py - Resource Training Trends Report (Year-over-Year)

Queries event_type 4000 (Resource access granted) from log.db joined with resources from makeit.db.
Produces year-over-year bar charts with numbers for each resource, summary KPI metrics,
search/sorting tools, and an optional tabular cross-tab view.
"""

import os
import sys
import sqlite3
import math
from datetime import datetime
from html import escape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DB = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../log.db"))
MAKEIT_DB = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../makeit.db"))
EVENT_ACCESS_GRANTED = 4000


def get_scale_ceiling(max_val):
    """Calculates a clean upper limit for the Y-axis so bars have room for labels."""
    if max_val <= 0:
        return 5
    elif max_val <= 5:
        return 5
    elif max_val <= 10:
        return 10
    elif max_val <= 25:
        return 25
    elif max_val <= 50:
        return 50
    elif max_val <= 100:
        return 100
    elif max_val <= 200:
        return 200
    else:
        return int(math.ceil(max_val * 1.15 / 50.0) * 50)


def generate_resource_bar_chart(res_id, res_name, years, year_counts, current_year_str):
    """Generates a responsive SVG bar chart for a single resource across all years."""
    max_val = max(year_counts.values()) if year_counts else 0
    scale_ceiling = get_scale_ceiling(max_val)

    svg_w = 480
    svg_h = 205
    pad_top = 26
    pad_bottom = 30
    pad_left = 38
    pad_right = 14

    chart_w = svg_w - pad_left - pad_right
    chart_h = svg_h - pad_top - pad_bottom
    baseline_y = pad_top + chart_h

    num_years = len(years) if years else 1
    col_w = chart_w / float(num_years)
    bar_w = min(30.0, max(14.0, col_w * 0.60))

    svg = []
    svg.append(f'<svg viewBox="0 0 {svg_w} {svg_h}" width="100%" height="{svg_h}" style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; display: block; overflow: visible;">')

    grad_id = f"grad_{res_id}"
    svg.append(f'''<defs>
      <linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#3b82f6"/>
        <stop offset="100%" stop-color="#1d4ed8"/>
      </linearGradient>
      <linearGradient id="{grad_id}_current" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#06b6d4"/>
        <stop offset="100%" stop-color="#0284c7"/>
      </linearGradient>
    </defs>''')

    mid_val = scale_ceiling / 2.0
    mid_y = baseline_y - chart_h / 2.0

    # Top dashed line and label
    svg.append(f'<line x1="{pad_left}" y1="{pad_top}" x2="{svg_w - pad_right}" y2="{pad_top}" stroke="#e2e8f0" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{pad_left - 6}" y="{pad_top + 4}" font-size="10px" fill="#94a3b8" text-anchor="end">{scale_ceiling}</text>')

    # Mid dashed line and label
    svg.append(f'<line x1="{pad_left}" y1="{mid_y}" x2="{svg_w - pad_right}" y2="{mid_y}" stroke="#e2e8f0" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{pad_left - 6}" y="{mid_y + 4}" font-size="10px" fill="#94a3b8" text-anchor="end">{int(mid_val)}</text>')

    # Baseline solid line and zero label
    svg.append(f'<line x1="{pad_left}" y1="{baseline_y}" x2="{svg_w - pad_right}" y2="{baseline_y}" stroke="#cbd5e1" stroke-width="1.5"/>')
    svg.append(f'<text x="{pad_left - 6}" y="{baseline_y + 3}" font-size="10px" fill="#94a3b8" text-anchor="end">0</text>')

    # Bars and data numbers for each year
    for i, yr in enumerate(years):
        cnt = year_counts.get(yr, 0)
        center_x = pad_left + i * col_w + col_w / 2.0
        bar_x = center_x - bar_w / 2.0

        is_current = (yr == current_year_str)
        fill_attr = f'url(#{grad_id}_current)' if is_current else f'url(#{grad_id})'

        if cnt > 0:
            bar_h = (cnt / float(scale_ceiling)) * chart_h
            bar_y = baseline_y - bar_h
            svg.append(f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="3" ry="3" fill="{fill_attr}" style="transition: opacity 0.15s;" onmouseover="this.style.opacity=\'0.85\'" onmouseout="this.style.opacity=\'1.0\'">')
            svg.append(f'<title>{escape(res_name)} - {yr}: {cnt} members trained</title>')
            svg.append('</rect>')
            # Exact number label above bar
            svg.append(f'<text x="{center_x:.1f}" y="{bar_y - 6:.1f}" font-size="11.5px" font-weight="600" fill="#1e293b" text-anchor="middle">{cnt}</text>')
        else:
            # Subtle baseline indicator for 0
            svg.append(f'<rect x="{bar_x:.1f}" y="{baseline_y - 2}" width="{bar_w:.1f}" height="2" fill="#e2e8f0"/>')
            svg.append(f'<text x="{center_x:.1f}" y="{baseline_y - 6}" font-size="10px" fill="#94a3b8" text-anchor="middle">0</text>')

        # Year label below baseline
        yr_label = yr
        if is_current:
            yr_label += "*"
        svg.append(f'<text x="{center_x:.1f}" y="{baseline_y + 17}" font-size="11px" font-weight="500" fill="#475569" text-anchor="middle">{yr_label}</text>')

    svg.append('</svg>')
    return "".join(svg)


def render_report_html(data):
    """Renders the complete training report HTML."""
    current_year_str = str(datetime.now().year)

    # Determine year range across all resources
    all_years_set = set()
    for res_id, info in data.items():
        all_years_set.update(info['years'].keys())

    if not all_years_set:
        all_years = [current_year_str]
    else:
        min_yr = int(min(all_years_set))
        max_yr = int(max(all_years_set))
        all_years = [str(y) for y in range(min_yr, max_yr + 1)]

    # Compute KPI totals
    total_trainings_all = 0
    year_totals = {yr: 0 for yr in all_years}
    top_resource_name = "None"
    top_resource_total = 0

    for res_id, info in data.items():
        res_total = sum(info['years'].values())
        total_trainings_all += res_total
        if res_total > top_resource_total:
            top_resource_total = res_total
            top_resource_name = info['name']
        for yr in all_years:
            year_totals[yr] += info['years'].get(yr, 0)

    busiest_year = max(year_totals.items(), key=lambda x: x[1]) if year_totals else ("-", 0)

    html = []
    html.append("HTML:\n</pre>")
    html.append("<div style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif; padding: 24px; background-color: #f8fafc; border-radius: 10px; color: #1e293b;'>")

    # Header
    html.append("<div style='display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 15px; margin-bottom: 24px;'>")
    html.append("<div>")
    html.append("<h2 style='color: #0f172a; margin: 0 0 6px 0; font-size: 24px; font-weight: 700;'>Resource Training Trends (Year-over-Year)</h2>")
    html.append(f"<p style='color: #64748b; margin: 0; font-size: 14px;'>Annual authorization & training completions (Event 4000) across {len(all_years)} years ({all_years[0]} - {all_years[-1]})</p>")
    if current_year_str in all_years:
        html.append(f"<p style='color: #0369a1; margin: 4px 0 0 0; font-size: 12px; font-weight: 500;'>* Note: {current_year_str} reflects Year-to-Date (YTD) numbers.</p>")
    html.append("</div>")
    html.append("</div>")

    # KPI Metric Cards
    html.append("<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px;'>")
    kpis = [
        ("Total Trainings Granted", f"{total_trainings_all:,}", "#3b82f6"),
        ("Resources Tracked", f"{len(data)}", "#8b5cf6"),
        ("Busiest Training Year", f"{busiest_year[0]} ({busiest_year[1]:,} trained)", "#10b981"),
        ("Top Resource", f"{escape(top_resource_name)} ({top_resource_total:,})", "#f59e0b"),
    ]
    for label, val, accent in kpis:
        html.append(f"""
        <div style='background-color: white; border: 1px solid #e2e8f0; border-left: 4px solid {accent}; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
          <div style='font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;'>{label}</div>
          <div style='font-size: 19px; color: #0f172a; font-weight: 700; margin-top: 4px;'>{val}</div>
        </div>
        """)
    html.append("</div>")

    # Filter / Sort / View Controls
    html.append("""
    <div style='background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
      <div style='display: flex; align-items: center; gap: 12px; flex-wrap: wrap; flex: 1;'>
        <input type='text' id='trainingSearchInput' placeholder='🔍 Search resources (e.g. Laser, Mill, Wood)...' 
               oninput='let q=this.value.toLowerCase(); document.querySelectorAll(".training-res-card").forEach(c => { c.style.display = c.getAttribute("data-name").toLowerCase().includes(q) ? "" : "none"; });' 
               style='padding: 7px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13.5px; width: 280px; outline: none;'>
        
        <select onchange='let v=this.value; let container=document.getElementById("trainingCardsGrid"); let cards=Array.from(container.querySelectorAll(".training-res-card")); cards.sort((a,b) => { if(v==="name") return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name")); if(v==="total-desc") return parseInt(b.getAttribute("data-total")) - parseInt(a.getAttribute("data-total")); if(v==="recent-desc") return parseInt(b.getAttribute("data-recent")) - parseInt(a.getAttribute("data-recent")); return 0; }); cards.forEach(c => container.appendChild(c));' 
                style='padding: 7px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13.5px; background-color: white; color: #334155; cursor: pointer;'>
          <option value='name'>Sort by Name (A-Z)</option>
          <option value='total-desc'>Sort by Total Trained (Highest First)</option>
          <option value='recent-desc'>Sort by Recent Year (Highest First)</option>
        </select>
      </div>
      
      <div>
        <button type='button' onclick='let g=document.getElementById("trainingCardsGrid"); let t=document.getElementById("trainingTableContainer"); if(t.style.display==="none"){ t.style.display="block"; g.style.display="none"; this.innerHTML="📊 Show Graphs"; } else { t.style.display="none"; g.style.display="grid"; this.innerHTML="📋 Show Data Table"; }' 
                class='btn btn-outline-secondary btn-sm' style='font-weight: 500; font-size: 13px; padding: 6px 12px;'>📋 Show Data Table</button>
      </div>
    </div>
    """)

    # Cards Grid
    html.append("<div id='trainingCardsGrid' style='display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 20px;'>")

    sorted_resources = sorted(data.items(), key=lambda x: x[1]['name'].lower())

    for res_id, info in sorted_resources:
        name = info['name']
        year_counts = info['years']
        total_cnt = sum(year_counts.values())
        recent_cnt = year_counts.get(all_years[-1], 0)

        # YoY Trend badge compared to prior year
        prev_cnt = year_counts.get(all_years[-2], 0) if len(all_years) >= 2 else 0
        diff = recent_cnt - prev_cnt
        if prev_cnt > 0:
            pct = (diff / float(prev_cnt)) * 100
            if diff > 0:
                trend_badge = f"<span style='background-color: #dcfce7; color: #166534; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>▲ +{diff} (+{pct:.0f}%) vs {all_years[-2]}</span>"
            elif diff < 0:
                trend_badge = f"<span style='background-color: #fee2e2; color: #991b1b; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>▼ {diff} ({pct:.0f}%) vs {all_years[-2]}</span>"
            else:
                trend_badge = f"<span style='background-color: #f1f5f9; color: #475569; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>▶ 0% vs {all_years[-2]}</span>"
        elif recent_cnt > 0:
            trend_badge = f"<span style='background-color: #dcfce7; color: #166534; font-weight: 600; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>▲ +{recent_cnt} (new)</span>"
        else:
            trend_badge = f"<span style='background-color: #f1f5f9; color: #94a3b8; font-weight: 500; padding: 3px 8px; border-radius: 12px; font-size: 11px;'>No activity</span>"

        peak_cnt = 0
        peak_yr = "-"
        for yr in all_years:
            c = year_counts.get(yr, 0)
            if c > peak_cnt:
                peak_cnt = c
                peak_yr = yr
        avg_cnt = total_cnt / float(len(all_years)) if all_years else 0

        chart_svg = generate_resource_bar_chart(res_id, name, all_years, year_counts, current_year_str)

        html.append(f"""
        <div class='training-res-card' data-name='{escape(name)}' data-total='{total_cnt}' data-recent='{recent_cnt}' 
             style='background-color: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); display: flex; flex-direction: column; justify-content: space-between;'>
          
          <div>
            <div style='display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 4px;'>
              <div>
                <h4 style='margin: 0; font-size: 16px; font-weight: 700; color: #0f172a;'>{escape(name)}</h4>
                <span style='font-size: 11px; color: #94a3b8;'>Resource #{res_id}</span>
              </div>
              <div style='display: flex; align-items: center; gap: 6px;'>
                {trend_badge}
                <span style='background-color: #0d6efd; color: white; font-weight: 700; padding: 3px 9px; border-radius: 12px; font-size: 11.5px;'>{total_cnt:,} total</span>
              </div>
            </div>
            
            <div style='margin-top: 10px;'>
              {chart_svg}
            </div>
          </div>
          
          <div style='display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #f1f5f9; padding-top: 10px; margin-top: 8px; font-size: 11.5px; color: #64748b;'>
            <span><strong>Peak:</strong> {peak_cnt} ({peak_yr})</span>
            <span><strong>Annual Avg:</strong> {avg_cnt:.1f}/yr</span>
            <span><strong>{all_years[-1]}:</strong> {recent_cnt}</span>
          </div>
        </div>
        """)

    html.append("</div>")  # End cards grid

    # Cross-tab Summary Table
    html.append("<div id='trainingTableContainer' style='display: none; background-color: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); overflow-x: auto;'>")
    html.append("<h4 style='margin: 0 0 14px 0; font-size: 16px; color: #0f172a; font-weight: 700;'>Year-by-Year Training Summary Table</h4>")
    html.append("<table class='table table-bordered table-striped table-hover table-sm' style='font-size: 13px; margin: 0;'>")
    html.append("<thead class='thead-dark'><tr>")
    html.append("<th style='padding: 8px 10px;'>Resource Name</th>")
    html.append("<th style='padding: 8px 10px; text-align: center;'>ID</th>")
    for yr in all_years:
        col_title = yr if yr != current_year_str else f"{yr}*"
        html.append(f"<th style='padding: 8px 10px; text-align: right;'>{col_title}</th>")
    html.append("<th style='padding: 8px 10px; text-align: right; background-color: #334155; color: white;'>Total</th>")
    html.append("</tr></thead><tbody>")

    for res_id, info in sorted_resources:
        name = info['name']
        year_counts = info['years']
        res_total = sum(year_counts.values())
        html.append("<tr>")
        html.append(f"<td style='font-weight: 600;'>{escape(name)}</td>")
        html.append(f"<td style='text-align: center; color: #64748b;'>{res_id}</td>")
        for yr in all_years:
            c = year_counts.get(yr, 0)
            c_str = f"{c:,}" if c > 0 else "<span style='color: #cbd5e1;'>0</span>"
            html.append(f"<td style='text-align: right;'>{c_str}</td>")
        html.append(f"<td style='text-align: right; font-weight: 700; background-color: #f8fafc;'>{res_total:,}</td>")
        html.append("</tr>")

    # Table Totals Row
    html.append("<tr style='font-weight: 700; background-color: #e2e8f0; border-top: 2px solid #0f172a;'>")
    html.append("<td colspan='2' style='padding: 8px 10px;'>TOTAL</td>")
    for yr in all_years:
        html.append(f"<td style='padding: 8px 10px; text-align: right;'>{year_totals[yr]:,}</td>")
    html.append(f"<td style='padding: 8px 10px; text-align: right; background-color: #cbd5e1;'>{total_trainings_all:,}</td>")
    html.append("</tr>")

    html.append("</tbody></table>")
    html.append("</div>")  # End table container

    html.append("</div>")  # End outer div
    html.append("\n<pre>")
    return "".join(html)


def main():
    # Allow testing with demo data if requested or in environment
    if os.environ.get('TRAINING_REPORT_DEMO'):
        demo_data = {
            1: {'name': 'Epilog Laser', 'years': {'2018': 35, '2019': 58, '2020': 42, '2021': 75, '2022': 90, '2023': 112, '2024': 98, '2025': 105, '2026': 82}},
            2: {'name': 'Bridgeport Mill', 'years': {'2018': 12, '2019': 20, '2020': 15, '2021': 25, '2022': 30, '2023': 28, '2024': 35, '2025': 40, '2026': 29}},
            3: {'name': '3D Printers', 'years': {'2019': 45, '2020': 50, '2021': 85, '2022': 110, '2023': 130, '2024': 125, '2025': 140, '2026': 95}},
            4: {'name': 'Wood Lathe', 'years': {'2018': 18, '2019': 22, '2020': 14, '2021': 30, '2022': 35, '2023': 44, '2024': 41, '2025': 48, '2026': 36}},
            5: {'name': 'TIG Welder', 'years': {'2018': 8, '2019': 15, '2020': 11, '2021': 19, '2022': 24, '2023': 29, '2024': 26, '2025': 31, '2026': 20}},
            6: {'name': 'CNC Router', 'years': {'2020': 16, '2021': 38, '2022': 52, '2023': 65, '2024': 60, '2025': 72, '2026': 55}},
        }
        print(render_report_html(demo_data))
        sys.exit(0)

    try:
        conn = sqlite3.connect(LOG_DB)
        conn.execute(f'ATTACH DATABASE "{MAKEIT_DB}" AS makeit')
        cursor = conn.cursor()

        query = """
            SELECT 
                r.id AS resource_id,
                r.name AS resource_name,
                strftime('%Y', l.time_logged) AS year,
                COUNT(*) AS event_count
            FROM main.log AS l
            JOIN makeit.resources AS r ON l.resource_id = r.id
            WHERE l.event_type = ?
              AND l.time_logged IS NOT NULL
        """
        params = [EVENT_ACCESS_GRANTED]

        since_date = os.environ.get('REPORT_SINCE', '')
        if since_date:
            query += " AND l.time_logged >= ?"
            params.append(since_date)

        query += " GROUP BY r.id, r.name, strftime('%Y', l.time_logged) ORDER BY r.name, year;"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

    except Exception as e:
        print("HTML:\n</pre>")
        print(f"<div style='padding: 20px; font-family: sans-serif; background-color: white; border-radius: 8px; border: 1px solid #fee2e2;'>")
        print(f"<h3 style='color: #dc2626; margin-top: 0;'>Database Notice</h3>")
        print(f"<p style='color: #4b5563;'>Could not query training logs: {escape(str(e))}</p>")
        print("</div>\n<pre>")
        sys.exit(0)

    if not rows:
        print("HTML:\n</pre>")
        print("<div style='padding: 20px; font-family: sans-serif; background-color: white; border-radius: 8px;'>")
        print("<h3 style='color: #334155; margin-top: 0;'>Resource Training Trends</h3>")
        print("<p style='color: #64748b;'>No training records (event_type 4000) found in log database.</p>")
        print("</div>\n<pre>")
        sys.exit(0)

    # Structure data: {resource_id: {'name': str, 'years': {year: count}}}
    data = {}
    for res_id, res_name, yr, count in rows:
        if not yr:
            continue
        if res_id not in data:
            data[res_id] = {
                'name': res_name if res_name else f"Resource #{res_id}",
                'years': {}
            }
        data[res_id]['years'][yr] = count

    print(render_report_html(data))
    sys.exit(0)


if __name__ == '__main__':
    main()

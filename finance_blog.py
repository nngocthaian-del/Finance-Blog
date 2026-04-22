import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import json
import os

# --- Google Sheets CMS Integration ---
@st.cache_data(ttl=60)
def load_google_sheet_data():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        # Authenticate using the local Service Account JSON key
        # For deployment to Streamlit Cloud, you can migrate this to use st.secrets!
        creds_file = r"c:\Users\nngoc\Downloads\groovy-axis-494104-h0-6b8ede66fff7.json"
        
        if os.path.exists(creds_file):
            creds = Credentials.from_service_account_file(
                creds_file,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
            )
        else:
            # Fallback for Streamlit Cloud deployment using Secrets
            service_account_info = st.secrets["gcp_service_account"]
            creds = Credentials.from_service_account_info(
                service_account_info,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
            )

        client = gspread.authorize(creds)
        sheet_url = "https://docs.google.com/spreadsheets/d/1qZWYbXGTFsDMCp9LPOip1PlJEsS_jnOJStxcKkUAS78"
        doc = client.open_by_url(sheet_url)
        
        data = {"news": [], "sectors": {}, "outlook": ""}
        
        # 1. Daily Notes
        try:
            ws_news = doc.worksheet("Daily Notes")
            for r in ws_news.get_all_records():
                if str(r.get("Date", "")).strip():
                    data["news"].append({
                        "date": str(r.get("Date", "")),
                        "headline": str(r.get("Headline", "")),
                        "note": str(r.get("Note", ""))
                    })
        except Exception: pass
        
        # 2. Sector Notes
        try:
            ws_sectors = doc.worksheet("Sector Notes")
            for r in ws_sectors.get_all_records():
                s_name = str(r.get("Sector", "")).strip()
                if s_name:
                    if s_name not in data["sectors"]:
                        data["sectors"][s_name] = []
                    data["sectors"][s_name].append({
                        "date": str(r.get("Date", "")),
                        "headline": str(r.get("Headline", "")),
                        "note": str(r.get("Note", ""))
                    })
        except Exception: pass
        
        # 3. Outlook
        try:
            ws_outlook = doc.worksheet("Outlook")
            val = ws_outlook.acell("A2").value
            data["outlook"] = val if val else ""
        except Exception: pass
        
        # Sort notes descending (latest first)
        data["news"] = sorted(data["news"], key=lambda x: x.get("date", ""), reverse=True)
        for s in data["sectors"]:
            data["sectors"][s] = sorted(data["sectors"][s], key=lambda x: x.get("date", ""), reverse=True)
            
        return data
    except Exception as e:
        st.error(f"Error loading from Google Sheets. Ensure you shared the sheet with your service account email! Details: {e}")
        return {"news": [], "sectors": {}, "outlook": ""}

app_data = load_google_sheet_data()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Market Journal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
 
# ── Minimal clean styling ─────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@300;400&display=swap');
 
html, body, [class*="css"] {
    font-family: 'DM Mono', monospace;
    background-color: #fafaf8;
    color: #1a1a1a;
}
h1, h2, h3 {
    font-family: 'DM Serif Display', serif;
    font-weight: 400;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'DM Mono', monospace;
    font-size: 13px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #888;
}
.stTabs [aria-selected="true"] {
    color: #1a1a1a !important;
    border-bottom: 2px solid #1a1a1a !important;
}
.block-container { padding-top: 2rem; padding-bottom: 2rem; }
hr { border: none; border-top: 1px solid #e5e5e5; margin: 1.5rem 0; }
.news-table { font-size: 13px; }
</style>
""", unsafe_allow_html=True)
 
# ── Helper: fetch price history ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch(ticker, period="6mo", interval="1d"):
    try:
        fetch_period = "5d" if period == "1d" else period
        df = yf.download(ticker, period=fetch_period, interval=interval, progress=False)
        df = df[["Close"]].copy()
        df.columns = [ticker]
        df.index = pd.to_datetime(df.index)
        
        if period == "1d" and not df.empty:
            import numpy as np
            dates = df.index.date
            unique_dates = pd.Series(dates).unique()
            if len(unique_dates) >= 2:
                today = unique_dates[-1]
                prior_mask = dates < today
                if prior_mask.any():
                    last_prior_idx = np.where(prior_mask)[0][-1]
                    df = df.iloc[last_prior_idx:].copy()
                    
                    # Artificially shift the prior close timestamp to 5 minutes before today's open
                    # This prevents a massive empty gap from stretching across the chart.
                    if len(df) >= 2:
                        new_idx = df.index.tolist()
                        new_idx[0] = new_idx[1] - pd.Timedelta(minutes=5)
                        df.index = pd.Index(new_idx)
                        
        # Convert to US Eastern Time so the chart hours make sense visually
        if df.index.tz is not None:
            df.index = df.index.tz_convert('America/New_York')
        else:
            df.index = df.index.tz_localize('UTC').tz_convert('America/New_York')
            
        return df
    except Exception:
        return pd.DataFrame()
 
# ── Helper: multi-line chart ──────────────────────────────────────────────────
def make_chart(title, tickers, labels, colors, percent=True, period="6mo"):
    fig = go.Figure()
    interval = "5m" if period == "1d" else "1d"
    for ticker, label, color in zip(tickers, labels, colors):
        df = fetch(ticker, period=period, interval=interval)
        if df.empty:
            continue
        y = (df[ticker] / df[ticker].iloc[0] - 1) * 100 if percent else df[ticker]
        customdata = df[ticker]
        
        # Format the x-axis hover tooltip based on timeframe
        x_hover = "%{x|%I:%M %p}" if period == "1d" else "%{x|%b %d}"
        
        fig.add_trace(go.Scatter(
            x=df.index, y=y,
            customdata=customdata,
            mode="lines",
            name=label,
            line=dict(color=color, width=1.5),
            hovertemplate=f"<b>{label}</b><br>{x_hover}<br>{'%{y:.2f}%' if percent else '%{y:,.2f}'}<br>%{{customdata:,.2f}} pts<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text=title, font=dict(family="DM Serif Display", size=18), x=0),
        paper_bgcolor="#fafaf8",
        plot_bgcolor="#fafaf8",
        legend=dict(orientation="h", y=-0.15, font=dict(size=11)),
        margin=dict(l=0, r=0, t=40, b=40),
        hovermode="x unified",
        xaxis=dict(showgrid=False, tickfont=dict(size=10), zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#ebebeb", tickfont=dict(size=10),
                   zeroline=True, zerolinecolor="#ccc", zerolinewidth=1,
                   ticksuffix="%" if percent else ""),
        height=300,
    )
    return fig
 
# ── Helper: daily market returns for table ────────────────────────────────────
@st.cache_data(ttl=3600)
def get_daily_market_data():
    tickers = {"SP 500": "^GSPC", "Dow": "^DJI", "Gold": "GC=F", "Oil": "CL=F", "Yield": "^TNX"}
    df_list = []
    for name, ticker in tickers.items():
        try:
            d = yf.download(ticker, period="1y", interval="1d", progress=False)["Close"]
            if isinstance(d, pd.DataFrame):
                d = d.squeeze()
            d.name = name
            df_list.append(d)
        except Exception:
            pass
    if not df_list:
        return pd.DataFrame()
    
    df = pd.concat(df_list, axis=1)
    pct_df = df.pct_change() * 100
    if "Yield" in df.columns:
        pct_df["Yield"] = df["Yield"].diff() * 100  # convert % yield diff to basis points
        
    pct_df.index = pd.to_datetime(pct_df.index)
    df.index = pd.to_datetime(df.index)
    
    full_idx = pd.date_range(pct_df.index.min(), datetime.now())
    
    pct_df = pct_df.reindex(full_idx).ffill()
    pct_df.index = pct_df.index.strftime('%Y-%m-%d')
    
    df = df.reindex(full_idx).ffill()
    df.index = df.index.strftime('%Y-%m-%d')
    
    return {"pct": pct_df, "pts": df}
 
# News loaded dynamically via app_data["news"]
 
# ─────────────────────────────────────────────────────────────────────────────
# TAB LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("# Market Journal")
st.markdown("<p style='color:#888; font-size:13px; margin-top:-12px;'>Updated daily · Personal research notes</p>", unsafe_allow_html=True)
st.markdown("---")
 
tab1, tab2, tab3 = st.tabs(["Markets", "Equity Research", "Quarterly Outlook"])
 
# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — MARKETS
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
 
    period_label = st.radio(
        "Timeframe:",
        ["1 Day", "1 Month", "6 Months", "1 Year", "5 Years"],
        horizontal=True,
        index=2
    )
    period_map = {"1 Day": "1d", "1 Month": "1mo", "6 Months": "6mo", "1 Year": "1y", "5 Years": "5y"}
    period_val = period_map[period_label]

    # US Indices
    st.plotly_chart(make_chart(
        f"US Indices — {period_label}",
        ["^GSPC", "^IXIC", "^DJI"],
        ["S&P 500", "Nasdaq", "Dow Jones"],
        ["#1a1a1a", "#c0392b", "#2980b9"],
        percent=True,
        period=period_val
    ), use_container_width=True)
 
    # Asian Indices
    st.plotly_chart(make_chart(
        f"Asian Indices — {period_label}",
        ["^N225", "^HSI", "^KS11"],
        ["Nikkei", "Hang Seng", "KOSPI"],
        ["#e74c3c", "#e67e22", "#27ae60"],
        percent=True,
        period=period_val
    ), use_container_width=True)
 
    col1, col2 = st.columns(2)
 
    with col1:
        # Commodities: Gold & Silver
        st.plotly_chart(make_chart(
            f"Gold & Silver — {period_label}",
            ["GC=F", "SI=F"],
            ["Gold", "Silver"],
            ["#b8860b", "#95a5a6"],
            period=period_val
        ), use_container_width=True)
 
    with col2:
        # Oil
        st.plotly_chart(make_chart(
            f"Crude Oil (WTI) — {period_label}",
            ["CL=F"],
            ["WTI Crude"],
            ["#34495e"],
            percent=False,
            period=period_val
        ), use_container_width=True)
 
    # Yield Curve
    st.markdown("### Yield Curve")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Compare US Treasury yields across multiple days</p>", unsafe_allow_html=True)
 
    @st.cache_data(ttl=3600)
    def get_yields_history():
        maturities = {
            "1M": "DGS1MO", "2M": "DGS2MO", "3M": "DGS3MO", "6M": "DGS6MO",
            "1Y": "DGS1", "2Y": "DGS2", "3Y": "DGS3", "5Y": "DGS5",
            "7Y": "DGS7", "10Y": "DGS10", "20Y": "DGS20", "30Y": "DGS30"
        }
        # Fetch 5 years of historical yield data so the user can select older dates
        start_date = (datetime.now() - timedelta(days=5*365)).strftime("%Y-%m-%d")
        df_list = []
        for label, series_id in maturities.items():
            try:
                url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start_date}"
                s = pd.read_csv(url, index_col=0, na_values=".")
                s.columns = [label]
                df_list.append(s)
            except Exception as e:
                pass
                
        if not df_list:
            return pd.DataFrame()
            
        df = pd.concat(df_list, axis=1)
        df = df.dropna(how='all').ffill().dropna()
        df.index = pd.to_datetime(df.index).strftime('%Y-%m-%d')
        cols = [k for k in maturities.keys() if k in df.columns]
        return df[cols]
 
    yield_df = get_yields_history()
 
    if not yield_df.empty:
        available_dates = yield_df.index.tolist()[::-1]
        today_str = datetime.now().strftime("%Y-%m-%d")
        if today_str not in available_dates:
            available_dates.insert(0, today_str)
            
        default_dates = [available_dates[0]]
        if len(available_dates) > 5:
            default_dates.append(available_dates[5])
            
        selected_dates = st.multiselect(
            "Compare Dates:",
            options=available_dates,
            default=default_dates,
            label_visibility="collapsed"
        )
        
        if selected_dates:
            fig_yield = go.Figure()
            colors = ["#1a1a1a", "#c0392b", "#2980b9", "#27ae60", "#e67e22"]
            for i, date in enumerate(selected_dates):
                if date in yield_df.index:
                    y_data = yield_df.loc[date]
                    name_str = date
                else:
                    y_data = yield_df.iloc[-1]
                    name_str = f"{date} (Latest: {yield_df.index[-1]})"
                    st.info(f"**Note:** Official Treasury yield data for `{date}` is not published until tomorrow. Showing latest available.")
                    
                color = colors[i % len(colors)]
                fig_yield.add_trace(go.Scatter(
                    x=yield_df.columns,
                    y=y_data,
                    mode="lines+markers",
                    name=name_str,
                    line=dict(color=color, width=2),
                    marker=dict(size=7, color=color),
                    hovertemplate="<b>%{x}</b>: %{y:.3f}%<extra></extra>",
                ))
            fig_yield.update_layout(
                paper_bgcolor="#fafaf8", plot_bgcolor="#fafaf8",
                margin=dict(l=0, r=0, t=20, b=20),
                height=260,
                legend=dict(orientation="h", y=-0.25, font=dict(size=11)),
                xaxis=dict(showgrid=False, tickfont=dict(size=11)),
                yaxis=dict(showgrid=True, gridcolor="#ebebeb", ticksuffix="%", tickfont=dict(size=11)),
            )
            st.plotly_chart(fig_yield, use_container_width=True)
 
    # ── Daily News Table ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Daily Notes")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Click a row date to highlight</p>", unsafe_allow_html=True)
 
    # Data loads from Google Sheets automatically
    market_data = get_daily_market_data()
    
    html = "<style>\n"
    html += ".market-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }\n"
    html += ".market-table th { border-bottom: 2px solid #ccc; padding: 10px; color: #888; font-weight: normal; }\n"
    html += ".market-table td { border-bottom: 1px solid #ebebeb; padding: 12px 10px; vertical-align: top; }\n"
    html += ".pos { color: #27ae60; font-weight: 500; }\n"
    html += ".neg { color: #c0392b; font-weight: 500; }\n"
    html += ".neu { color: #888; }\n"
    html += "</style>\n"
    html += "<table class='market-table'>\n"
    html += "<tr>\n"
    html += "<th style='width: 12%;'>Date</th>\n"
    html += "<th style='width: 35%;'>Events</th>\n"
    html += "<th>SP 500</th>\n"
    html += "<th>Dow</th>\n"
    html += "<th>Gold</th>\n"
    html += "<th>Yield</th>\n"
    html += "<th>Oil</th>\n"
    html += "</tr>\n"
    
    for item in app_data["news"]:
        date_str = item["date"]
        display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d/%Y")
        
        lines = item['note'].strip().split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('-') and not line.startswith('*'):
                line = "- " + line
            formatted_lines.append(line)
        note_formatted = '<br/>'.join(formatted_lines)
        
        events_html = f"<div style='margin-bottom:4px;'><b>* {item['headline']}</b></div><span style='color:#666; font-size:12px;'>{note_formatted}</span>"
        
        sp_val, dow_val, gold_val, yield_val, oil_val = "-", "-", "-", "-", "-"
        if market_data and date_str in market_data["pct"].index:
            pct_row = market_data["pct"].loc[date_str]
            pts_row = market_data["pts"].loc[date_str]
            
            def fmt(pct_val, pts_val, is_bps=False, is_yield=False):
                if pd.isna(pct_val) or pd.isna(pts_val): return "-"
                cls = "pos" if pct_val > 0 else "neg" if pct_val < 0 else "neu"
                sign = "+" if pct_val > 0 else ""
                unit = " bps" if is_bps else "%"
                
                if is_yield:
                    pts_str = f"{pts_val:.3f}%"
                elif pts_val > 1000:
                    pts_str = f"{pts_val:,.0f}"
                else:
                    pts_str = f"{pts_val:.2f}"
                    
                return f"<div style='font-weight:500;'>{pts_str}</div><div class='{cls}' style='font-size:11px; margin-top:2px;'>{sign}{pct_val:.2f}{unit}</div>"
                
            sp_val = fmt(pct_row.get("SP 500"), pts_row.get("SP 500"))
            dow_val = fmt(pct_row.get("Dow"), pts_row.get("Dow"))
            gold_val = fmt(pct_row.get("Gold"), pts_row.get("Gold"))
            yield_val = fmt(pct_row.get("Yield"), pts_row.get("Yield"), is_bps=True, is_yield=True)
            oil_val = fmt(pct_row.get("Oil"), pts_row.get("Oil"))
            
        html += f"<tr><td>{display_date}</td><td>{events_html}</td><td>{sp_val}</td><td>{dow_val}</td><td>{gold_val}</td><td>{yield_val}</td><td>{oil_val}</td></tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — EQUITY RESEARCH
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Equity Research")
 
    sp500_sectors = {
        "S&P 500 Energy Sector": "^GSPE",
        "S&P 500 Information Technology Sector": "^SP500-45",
        "S&P 500 Consumer Staples Sector": "^SP500-30",
        "S&P 500 Consumer Discretionary Sector": "^SP500-25",
        "S&P 500 Financials Sector": "^SP500-40",
        "S&P 500": "^GSPC",
        "S&P 500 Health Care Sector": "^SP500-35",
        "S&P 500 Materials Sector": "^SP500-15",
        "S&P 500 Communication Services Sector": "^SP500-50",
        "S&P 500 Industrials Sector": "^SP500-20",
        "S&P 500 Utilities Sector": "^SP500-55",
        "S&P 500 Real Estate Sector": "^SP500-60"
    }

    selected_sectors = st.multiselect(
        "Compare Sectors:",
        options=list(sp500_sectors.keys()),
        default=["S&P 500", "S&P 500 Information Technology Sector", "S&P 500 Energy Sector"]
    )

    # Timeframe selector for the equity tab
    eq_period_label = st.radio(
        "Equity Timeframe:",
        ["1 Day", "1 Month", "6 Months", "1 Year", "5 Years"],
        horizontal=True,
        index=2,
        key="eq_timeframe"
    )
    eq_period_map = {"1 Day": "1d", "1 Month": "1mo", "6 Months": "6mo", "1 Year": "1y", "5 Years": "5y"}
    eq_period_val = eq_period_map[eq_period_label]
    
    if selected_sectors:
        tickers = [sp500_sectors[s] for s in selected_sectors]
        labels = selected_sectors
        
        # Generate colors, ensuring S&P 500 is always black
        colors = []
        palette = ["#2980b9", "#c0392b", "#27ae60", "#e67e22", "#8e44ad", "#f39c12", "#d35400", "#34495e", "#16a085", "#2c3e50", "#bdc3c7"]
        c_idx = 0
        for label in labels:
            if label == "S&P 500":
                colors.append("#1a1a1a")
            else:
                colors.append(palette[c_idx % len(palette)])
                c_idx += 1
                
        st.plotly_chart(make_chart(
            "Sector Relative Performance",
            tickers,
            labels,
            colors,
            percent=True,
            period=eq_period_val
        ), use_container_width=True)

    st.markdown("---")
    st.markdown("### Sector Notes & Updates")
    sector_name = st.selectbox(
        "Select a sector to view or update notes:",
        list(sp500_sectors.keys()),
    )
    
    # Read-only display of notes from Google Sheets
                        
    # Aggregate sector notes based on selection
    display_notes = []
    if sector_name == "S&P 500":
        for s_name, notes_list in app_data.get("sectors", {}).items():
            if isinstance(notes_list, list):
                for n in notes_list:
                    n_copy = n.copy()
                    s_clean = s_name
                    if s_clean != "S&P 500":
                        s_clean = s_clean.replace("S&P 500 ", "").replace(" Sector", "")
                    n_copy["sector"] = s_clean
                    display_notes.append(n_copy)
    else:
        sector_list = app_data.get("sectors", {}).get(sector_name, [])
        if sector_list:
            for n in sector_list:
                n_copy = n.copy()
                n_copy["sector"] = sector_name.replace("S&P 500 ", "").replace(" Sector", "")
                display_notes.append(n_copy)
                
    # Sort descending
    display_notes = sorted(display_notes, key=lambda x: x.get("date", ""), reverse=True)

    html = "<style>\n"
    html += ".sector-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }\n"
    html += ".sector-table th { border-bottom: 2px solid #ccc; padding: 10px; color: #888; font-weight: normal; }\n"
    html += ".sector-table td { border-bottom: 1px solid #ebebeb; padding: 12px 10px; vertical-align: top; }\n"
    html += "</style>\n"
    html += "<table class='sector-table'>\n"
    html += "<tr>\n"
    html += "<th style='width: 12%;'>Date</th>\n"
    html += "<th style='width: 25%;'>Sector</th>\n"
    html += "<th>Events</th>\n"
    html += "</tr>\n"
    
    for item in display_notes:
        date_str = item.get("date", "")
        display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d/%Y") if date_str else ""
        sector_disp = item.get("sector", "")
        
        lines = item.get('note', '').strip().split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('-') and not line.startswith('*'):
                line = "- " + line
            formatted_lines.append(line)
        note_formatted = '<br/>'.join(formatted_lines)
        
        events_html = f"<div style='margin-bottom:4px;'><b>* {item.get('headline', '')}</b></div><span style='color:#666; font-size:12px;'>{note_formatted}</span>"
        
        html += f"<tr><td>{display_date}</td><td><b style='color:#555;'>{sector_disp}</b></td><td>{events_html}</td></tr>\n"
    html += "</table>\n"
    st.markdown(html, unsafe_allow_html=True)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — QUARTERLY OUTLOOK
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Investment Outlook")
    st.markdown("---")
    
    current_outlook = app_data.get("outlook", "")
    current_outlook = app_data.get("outlook", "")
    if current_outlook:
        st.markdown(current_outlook)
    else:
        st.info("Your Investment Outlook will appear here once you add it to the Google Sheet!")
        

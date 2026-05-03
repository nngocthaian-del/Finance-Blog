import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import uuid
import re

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Market Journal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@300;400&display=swap');
html, body, [class*="css"] {
    font-family: 'DM Mono', monospace;
    background-color: #fafaf8;
    color: #1a1a1a;
}
h1, h2, h3 { font-family: 'DM Serif Display', serif; font-weight: 400; }
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

/* Quill editor styles */
.ql-toolbar { border-radius: 8px 8px 0 0 !important; border-color: #e5e5e5 !important; background: #fff; }
.ql-container { border-radius: 0 0 8px 8px !important; border-color: #e5e5e5 !important; font-family: 'DM Mono', monospace !important; font-size: 14px !important; min-height: 400px; }
.ql-editor { min-height: 380px; line-height: 1.8; }
</style>
""", unsafe_allow_html=True)

# ── Google Sheets connection ──────────────────────────────────────────────────
SPREADSHEET_ID = "1qZWYbXGTFsDMCp9LPOip1PlJEsS_jnOJStxcKkUAS78"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_gsheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_macro_news():
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SPREADSHEET_ID)
        ws = sheet.worksheet("Finance Blog Macro")
        values = ws.get_all_values()
        headers = values[0]
        rows = values[1:]
        df = pd.DataFrame(rows, columns=headers)
        df = df[df["date"].astype(str).str.strip() != ""]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Could not load news: {e}")
        return pd.DataFrame(columns=["date", "headline", "note"])

@st.cache_data(ttl=300)
def load_sector_notes():
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SPREADSHEET_ID)
        ws = sheet.worksheet("Finance Blog Sectors")
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        df = df[df["date"].astype(str).str.strip() != ""]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Could not load sector notes: {e}")
        return pd.DataFrame(columns=["date", "sector", "headline", "note"])

# ── Posts helpers ─────────────────────────────────────────────────────────────
def get_posts_worksheet():
    client = get_gsheet_client()
    sheet = client.open_by_key(SPREADSHEET_ID)
    try:
        ws = sheet.worksheet("Finance Blog Posts")
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title="Finance Blog Posts", rows=1000, cols=6)
        ws.append_row(["id", "date", "title", "content", "status", "updated_at"])
    return ws

@st.cache_data(ttl=300)
def load_posts(status_filter=None):
    try:
        ws = get_posts_worksheet()
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(columns=["id", "date", "title", "content", "status", "updated_at"])
        df = df[df["id"].astype(str).str.strip() != ""]
        if status_filter:
            df = df[df["status"] == status_filter]
        df = df.sort_values("updated_at", ascending=False).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Could not load posts: {e}")
        return pd.DataFrame(columns=["id", "date", "title", "content", "status", "updated_at"])

def save_post(post_id, title, content, status):
    ws = get_posts_worksheet()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    records = ws.get_all_records()
    for i, row in enumerate(records):
        if str(row.get("id", "")) == str(post_id):
            ws.update(f"A{i+2}:F{i+2}", [[post_id, row.get("date", today), title, content, status, now]])
            return "updated"

    ws.append_row([post_id, today, title, content, status, now])
    return "created"

def delete_post(post_id):
    ws = get_posts_worksheet()
    records = ws.get_all_records()
    for i, row in enumerate(records):
        if str(row.get("id", "")) == str(post_id):
            ws.delete_rows(i + 2)
            return True
    return False

# ── Helper: fetch price history ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch(ticker, period="6mo", interval="1d"):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        df = df[["Close"]].copy()
        df.columns = [ticker]
        df.index = pd.to_datetime(df.index)
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
        fig.add_trace(go.Scatter(
            x=df.index, y=y,
            mode="lines",
            name=label,
            line=dict(color=color, width=1.5),
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %d}}<br>{'%{y:.2f}%' if percent else '%{y:,.2f}'}<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text=title, font=dict(family="DM Serif Display", size=18), x=0.05, xanchor="left"),
        paper_bgcolor="#fafaf8", plot_bgcolor="#fafaf8",
        legend=dict(orientation="h", y=-0.18, x=0.05, xanchor="left", font=dict(size=11)),
        margin=dict(l=50, r=20, t=80, b=60),
        hovermode="closest",
        xaxis=dict(showgrid=False, tickfont=dict(size=10), zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#ebebeb", tickfont=dict(size=10),
                   zeroline=True, zerolinecolor="#ccc", zerolinewidth=1,
                   ticksuffix="%" if percent else ""),
        height=380,
    )
    return fig

# ── Session state defaults ────────────────────────────────────────────────────
if "editor_authenticated" not in st.session_state:
    st.session_state.editor_authenticated = False
if "editing_post_id" not in st.session_state:
    st.session_state.editing_post_id = None
if "editor_title" not in st.session_state:
    st.session_state.editor_title = ""
if "editor_content" not in st.session_state:
    st.session_state.editor_content = ""
if "editor_status" not in st.session_state:
    st.session_state.editor_status = "draft"
if "posts_cache_bust" not in st.session_state:
    st.session_state.posts_cache_bust = 0
if "view_post_id" not in st.session_state:
    st.session_state.view_post_id = None

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("# Market Journal")
st.markdown("<p style='color:#888; font-size:13px; margin-top:-12px;'>Updated daily · Personal research notes</p>", unsafe_allow_html=True)
st.markdown("---")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Markets", "Equity Research", "Strategy & Recommendations", "Notes", "✏️ Write"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — MARKETS
# ─────────────────────────────────────────────────────────────────────────────
with tab1:

    custom_range = st.date_input(
        "Timeframe:",
        value=(datetime.now().date() - timedelta(days=180), datetime.now().date()),
        max_value=datetime.now().date(),
        label_visibility="visible"
    )
    if isinstance(custom_range, tuple) and len(custom_range) == 2:
        delta = (custom_range[1] - custom_range[0]).days
        if delta <= 30: period_val = "1mo"
        elif delta <= 90: period_val = "3mo"
        elif delta <= 180: period_val = "6mo"
        elif delta <= 365: period_val = "1y"
        elif delta <= 730: period_val = "2y"
        else: period_val = "5y"
        period_label = f"{custom_range[0].strftime('%b %d')} – {custom_range[1].strftime('%b %d, %Y')}"
    else:
        period_val = "6mo"
        period_label = "6 Months"

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(make_chart(
            f"US Indices — {period_label}",
            ["^GSPC", "^IXIC", "^DJI"],
            ["S&P 500", "Nasdaq", "Dow Jones"],
            ["#1a1a1a", "#c0392b", "#2980b9"],
            period=period_val
        ), use_container_width=True)
    with col2:
        st.plotly_chart(make_chart(
            f"Asian Indices — {period_label}",
            ["^N225", "^HSI", "^KS11"],
            ["Nikkei", "Hang Seng", "KOSPI"],
            ["#e74c3c", "#e67e22", "#27ae60"],
            period=period_val
        ), use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        df_gold = fetch("GC=F", period=period_val)
        df_silver = fetch("SI=F", period=period_val)
        fig_gs = go.Figure()
        if not df_gold.empty:
            fig_gs.add_trace(go.Scatter(
                x=df_gold.index, y=df_gold["GC=F"],
                name="Gold", line=dict(color="#b8860b", width=1.5),
                hovertemplate="<b>Gold</b><br>%{x|%b %d}<br>$%{y:,.2f}<extra></extra>",
                yaxis="y1"
            ))
        if not df_silver.empty:
            fig_gs.add_trace(go.Scatter(
                x=df_silver.index, y=df_silver["SI=F"],
                name="Silver", line=dict(color="#95a5a6", width=1.5),
                hovertemplate="<b>Silver</b><br>%{x|%b %d}<br>$%{y:,.2f}<extra></extra>",
                yaxis="y2"
            ))
        fig_gs.update_layout(
            title=dict(text=f"Gold & Silver — {period_label}", font=dict(family="DM Serif Display", size=18), x=0.05, xanchor="left"),
            paper_bgcolor="#fafaf8", plot_bgcolor="#fafaf8",
            legend=dict(orientation="h", y=-0.18, x=0.05, xanchor="left", font=dict(size=11)),
            margin=dict(l=50, r=50, t=80, b=60),
            hovermode="closest",
            height=380,
            yaxis=dict(title="Gold (USD)", showgrid=True, gridcolor="#ebebeb", tickfont=dict(size=10), tickprefix="$"),
            yaxis2=dict(title="Silver (USD)", overlaying="y", side="right", tickfont=dict(size=10), tickprefix="$", showgrid=False),
            xaxis=dict(showgrid=False, tickfont=dict(size=10)),
        )
        st.plotly_chart(fig_gs, use_container_width=True)
    with col4:
        st.plotly_chart(make_chart(
            f"Crude Oil (WTI) — {period_label}",
            ["CL=F"],
            ["WTI Crude"],
            ["#34495e"],
            percent=False,
            period=period_val
        ), use_container_width=True)

    st.markdown("### Yield Curve")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>US Treasury yields — official source</p>", unsafe_allow_html=True)

    @st.cache_data(ttl=3600)
    def get_yields_history():
        col_map = {
            "1 Mo": "1M", "2 Mo": "2M", "3 Mo": "3M", "4 Mo": "4M",
            "6 Mo": "6M", "1 Yr": "1Y", "2 Yr": "2Y", "3 Yr": "3Y",
            "5 Yr": "5Y", "7 Yr": "7Y", "10 Yr": "10Y", "20 Yr": "20Y", "30 Yr": "30Y"
        }
        years = [datetime.now().year - 1, datetime.now().year]
        dfs = []
        for year in years:
            try:
                url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}"
                df = pd.read_csv(url)
                df = df.rename(columns={"Date": "date"})
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                df = df.set_index("date")
                rename = {k: v for k, v in col_map.items() if k in df.columns}
                df = df.rename(columns=rename)
                keep = [v for v in col_map.values() if v in df.columns]
                dfs.append(df[keep])
            except Exception:
                pass
        if not dfs:
            return pd.DataFrame()
        result = pd.concat(dfs)
        result = result[~result.index.duplicated(keep="last")]
        result = result.sort_index()
        result = result.dropna(how="all").ffill()
        return result

    yield_df = get_yields_history()
    if not yield_df.empty:
        available_dates = yield_df.index.tolist()[::-1]
        default_dates = [available_dates[0]]
        if len(available_dates) > 5:
            default_dates.append(available_dates[5])
        selected_dates = st.multiselect(
            "Compare dates:", options=available_dates, default=default_dates,
            label_visibility="collapsed"
        )
        if selected_dates:
            fig_yield = go.Figure()
            colors = ["#1a1a1a", "#c0392b", "#2980b9", "#27ae60", "#e67e22"]
            ordered_cols = ["1M","2M","3M","4M","6M","1Y","2Y","3Y","5Y","7Y","10Y","20Y","30Y"]
            plot_cols = [c for c in ordered_cols if c in yield_df.columns]
            for i, date in enumerate(selected_dates):
                if date in yield_df.index:
                    fig_yield.add_trace(go.Scatter(
                        x=plot_cols, y=yield_df.loc[date, plot_cols],
                        mode="lines+markers", name=date,
                        line=dict(color=colors[i % len(colors)], width=2),
                        marker=dict(size=7),
                        hovertemplate="<b>%{x}</b>: %{y:.3f}%<extra></extra>",
                    ))
            fig_yield.update_layout(
                paper_bgcolor="#fafaf8", plot_bgcolor="#fafaf8",
                margin=dict(l=50, r=20, t=30, b=60), height=540,
                legend=dict(orientation="h", y=-0.15, font=dict(size=11)),
                xaxis=dict(showgrid=False, tickfont=dict(size=11)),
                yaxis=dict(showgrid=True, gridcolor="#ebebeb", ticksuffix="%", tickfont=dict(size=11)),
            )
            st.plotly_chart(fig_yield, use_container_width=True)

    st.markdown("---")
    st.markdown("### Daily Notes")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Updated daily at 4pm · Edit via Google Sheets</p>", unsafe_allow_html=True)

    news_df = load_macro_news()

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
            return None
        df = pd.concat(df_list, axis=1)
        pct_df = df.pct_change() * 100
        if "Yield" in df.columns:
            pct_df["Yield"] = df["Yield"].diff() * 100
        pct_df.index = pd.to_datetime(pct_df.index)
        df.index = pd.to_datetime(df.index)
        full_idx = pd.date_range(pct_df.index.min(), datetime.now())
        pct_df = pct_df.reindex(full_idx).ffill()
        pct_df.index = pct_df.index.strftime('%Y-%m-%d')
        df = df.reindex(full_idx).ffill()
        df.index = df.index.strftime('%Y-%m-%d')
        return {"pct": pct_df, "pts": df}

    market_data = get_daily_market_data()

    if not news_df.empty:
        date_range = st.date_input(
            "Select date range:",
            value=(datetime.now().date() - timedelta(days=30), datetime.now().date()),
            max_value=datetime.now().date(),
            label_visibility="collapsed"
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = date_range
            news_df = news_df[
                (news_df["date"] >= start.strftime("%Y-%m-%d")) &
                (news_df["date"] <= end.strftime("%Y-%m-%d"))
            ]

    if not news_df.empty and market_data:
        export_rows = []
        for _, row in news_df.iterrows():
            date_str = row["date"]
            r = {"Date": date_str, "Headline": row.get("headline",""), "Note": row.get("note","")}
            if date_str in market_data["pts"].index:
                pts = market_data["pts"].loc[date_str]
                pct = market_data["pct"].loc[date_str]
                r["SP500"] = round(pts.get("SP 500", 0), 2)
                r["SP500 %"] = round(pct.get("SP 500", 0), 2)
                r["Dow"] = round(pts.get("Dow", 0), 2)
                r["Dow %"] = round(pct.get("Dow", 0), 2)
                r["Gold"] = round(pts.get("Gold", 0), 2)
                r["Gold %"] = round(pct.get("Gold", 0), 2)
                r["Yield"] = round(pts.get("Yield", 0), 3)
                r["Yield chg bps"] = round(pct.get("Yield", 0), 2)
                r["Oil"] = round(pts.get("Oil", 0), 2)
                r["Oil %"] = round(pct.get("Oil", 0), 2)
            export_rows.append(r)
        export_df = pd.DataFrame(export_rows)
        import io
        buf = io.BytesIO()
        export_df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        st.download_button(
            label="📥 Export to Excel",
            data=buf,
            file_name=f"market_journal_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    if not news_df.empty:
        html = "<style>\n"
        html += ".market-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }\n"
        html += ".market-table th { background-color: #1a1a1a; color: #fafaf8; padding: 12px 10px; font-weight: 500; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }\n"
        html += ".market-table td { border-bottom: 1px solid #ebebeb; padding: 12px 10px; vertical-align: top; }\n"
        html += ".pos { color: #27ae60; font-weight: 500; }\n"
        html += ".neg { color: #c0392b; font-weight: 500; }\n"
        html += ".neu { color: #888; }\n"
        html += "</style>\n"
        html += "<table class='market-table'>\n"
        html += "<tr>\n"
        html += "<th style='width: 10%;'>Date</th>\n"
        html += "<th style='width: 40%;'>Events</th>\n"
        html += "<th>SP 500</th>\n"
        html += "<th>Dow</th>\n"
        html += "<th>Gold</th>\n"
        html += "<th>Yield</th>\n"
        html += "<th>Oil</th>\n"
        html += "</tr>\n"

        for _, row in news_df.iterrows():
            date_str = row["date"]
            display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d/%Y")
            headline = str(row.get("headline", "Daily Market Update"))
            note = str(row.get("note", ""))
            events_html = f"<div style='margin-bottom:6px;'><b>{headline}</b></div><div style='color:#666; font-size:12px; line-height:1.8;'>{note}</div>"

            sp_val = dow_val = gold_val = yield_val = oil_val = "-"
            if market_data and date_str in market_data["pct"].index:
                pct_row = market_data["pct"].loc[date_str]
                pts_row = market_data["pts"].loc[date_str]

                def fmt(pct_val, pts_val, is_yield=False):
                    try:
                        if pd.isna(pct_val) or pd.isna(pts_val): return "-"
                        cls = "pos" if pct_val > 0 else "neg" if pct_val < 0 else "neu"
                        sign = "+" if pct_val > 0 else ""
                        if is_yield:
                            pts_str = f"{pts_val:.3f}%"
                            return f"<div style='font-weight:500;'>{pts_str}</div><div class='{cls}' style='font-size:11px; margin-top:2px;'>{sign}{pct_val:.2f} bps</div>"
                        elif pts_val > 1000:
                            pts_str = f"{pts_val:,.0f}"
                        else:
                            pts_str = f"{pts_val:.2f}"
                        return f"<div style='font-weight:500;'>{pts_str}</div><div class='{cls}' style='font-size:11px; margin-top:2px;'>{sign}{pct_val:.2f}%</div>"
                    except:
                        return "-"

                sp_val = fmt(pct_row.get("SP 500"), pts_row.get("SP 500"))
                dow_val = fmt(pct_row.get("Dow"), pts_row.get("Dow"))
                gold_val = fmt(pct_row.get("Gold"), pts_row.get("Gold"))
                yield_val = fmt(pct_row.get("Yield"), pts_row.get("Yield"), is_yield=True)
                oil_val = fmt(pct_row.get("Oil"), pts_row.get("Oil"))

            html += f"<tr><td>{display_date}</td><td>{events_html}</td><td>{sp_val}</td><td>{dow_val}</td><td>{gold_val}</td><td>{yield_val}</td><td>{oil_val}</td></tr>\n"

        html += "</table>"
        st.markdown(f"""
        <div style="height:600px; overflow-y:auto; border:1px solid #ebebeb; border-radius:8px; padding:0 8px;">
        {html}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No news yet — add rows to your Google Sheet!")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — EQUITY RESEARCH
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Equity Research")

    sp500_sectors = {
        "S&P 500": "^GSPC",
        "Energy": "^GSPE",
        "Information Technology": "^SP500-45",
        "Consumer Staples": "^SP500-30",
        "Consumer Discretionary": "^SP500-25",
        "Financials": "^SP500-40",
        "Health Care": "^SP500-35",
        "Materials": "^SP500-15",
        "Communication Services": "^SP500-50",
        "Industrials": "^SP500-20",
        "Utilities": "^SP500-55",
        "Real Estate": "^SP500-60"
    }

    selected_sectors = st.multiselect(
        "Compare Sectors:",
        options=list(sp500_sectors.keys()),
        default=["S&P 500", "Information Technology", "Energy"]
    )

    eq_custom = st.date_input(
        "Timeframe:",
        value=(datetime.now().date() - timedelta(days=180), datetime.now().date()),
        max_value=datetime.now().date(),
        label_visibility="visible",
        key="eq_custom_range"
    )
    if isinstance(eq_custom, tuple) and len(eq_custom) == 2:
        delta = (eq_custom[1] - eq_custom[0]).days
        if delta <= 30: eq_period_val = "1mo"
        elif delta <= 90: eq_period_val = "3mo"
        elif delta <= 180: eq_period_val = "6mo"
        elif delta <= 365: eq_period_val = "1y"
        elif delta <= 730: eq_period_val = "2y"
        else: eq_period_val = "5y"
    else:
        eq_period_val = "6mo"

    if selected_sectors:
        tickers = [sp500_sectors[s] for s in selected_sectors]
        labels = selected_sectors
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
            tickers, labels, colors,
            percent=True, period=eq_period_val
        ), use_container_width=True)

    st.markdown("---")
    st.markdown("### Sector Notes & Updates")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Edit via Google Sheets → Finance Blog Sectors tab</p>", unsafe_allow_html=True)

    sector_df = load_sector_notes()

    sector_list_no_sp = [s for s in sp500_sectors.keys() if s != "S&P 500"]
    sector_name = st.selectbox(
        "Select a sector to view notes:",
        ["All"] + sector_list_no_sp,
    )

    if not sector_df.empty and "sector" in sector_df.columns:
        s_date_range = st.date_input(
            "Select range:",
            value=(datetime.now().date() - timedelta(days=180), datetime.now().date()),
            max_value=datetime.now().date(),
            label_visibility="collapsed",
            key="sector_date_range"
        )

        if sector_name == "All":
            display_notes = sector_df.to_dict("records")
        else:
            clean_name = sector_name.replace("S&P 500 ", "").replace(" Sector", "")
            filtered = sector_df[sector_df["sector"].str.contains(clean_name, case=False, na=False)]
            display_notes = filtered.to_dict("records")

        display_notes = sorted(display_notes, key=lambda x: x.get("date", ""), reverse=True)

        if isinstance(s_date_range, tuple) and len(s_date_range) == 2:
            start, end = s_date_range
            display_notes = [n for n in display_notes if start.strftime("%Y-%m-%d") <= n.get("date","") <= end.strftime("%Y-%m-%d")]

        html = "<style>\n"
        html += ".sector-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }\n"
        html += ".sector-table th { background-color: #1a1a1a; color: #fafaf8; padding: 12px 10px; font-weight: 500; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }\n"
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
            lines = str(item.get("note", "")).strip().split("\n")
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("-") and not line.startswith("*"):
                    line = "- " + line
                formatted_lines.append(line)
            note_formatted = "<br/>".join(formatted_lines)
            events_html = f"<div style='margin-bottom:4px;'><b>{item.get('headline', '')}</b></div><span style='color:#666; font-size:12px;'>{note_formatted}</span>"
            html += f"<tr><td>{display_date}</td><td><b style='color:#555;'>{sector_disp}</b></td><td>{events_html}</td></tr>\n"

        html += "</table>"
        st.markdown('<div style="height:500px; overflow-y:auto; border:1px solid #ebebeb; border-radius:8px; padding:0 8px;">' + html + '</div>', unsafe_allow_html=True)
    else:
        st.info("No sector notes yet — add rows to your Google Sheet!")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — STRATEGY & RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Strategy & Recommendations")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Updated periodically · Edit via Google Sheets</p>", unsafe_allow_html=True)
    st.markdown("---")

    @st.cache_data(ttl=300)
    def load_strategy():
        try:
            client = get_gsheet_client()
            sheet = client.open_by_key(SPREADSHEET_ID)
            ws = sheet.worksheet("Finance Blog Strategy")
            values = ws.get_all_values()
            headers = values[0]
            rows = values[1:]
            df = pd.DataFrame(rows, columns=headers)
            df = df[df["section"].astype(str).str.strip() != ""]
            return df
        except Exception as e:
            st.error(f"Could not load strategy: {e}")
            return pd.DataFrame(columns=["section", "filename", "drive_link"])

    strategy_df = load_strategy()

    def drive_link_to_embed(link):
        match = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/file/d/{file_id}/preview"
        return link

    def render_section(section_name, df):
        section_df = df[df["section"].str.strip() == section_name]
        if section_df.empty:
            st.markdown("<p style='color:#888; font-size:12px;'>No files yet — add to Google Sheet</p>", unsafe_allow_html=True)
            return
        files = section_df.to_dict("records")
        for i in range(0, len(files), 2):
            cols = st.columns(2)
            for j, file in enumerate(files[i:i+2]):
                with cols[j]:
                    embed_url = drive_link_to_embed(file.get("drive_link", ""))
                    st.markdown(f"""
                    <div style="border:1px solid #ebebeb; border-radius:8px; overflow:hidden; margin-bottom:12px;">
                        <iframe src="{embed_url}" width="100%" height="600" frameborder="0" allowfullscreen></iframe>
                        <div style="padding:8px 10px; font-size:12px; font-weight:500; background:#fafaf8;">{file.get("filename","")}</div>
                    </div>
                    """, unsafe_allow_html=True)

    if not strategy_df.empty:
        sections = strategy_df["section"].unique().tolist()
        memo_sections = [s for s in sections if "memo" in s.lower() or "strategy" in s.lower() or "outlook" in s.lower()]
        pitch_sections = [s for s in sections if "pitch" in s.lower()]
        other_sections = [s for s in sections if s not in memo_sections and s not in pitch_sections]

        if memo_sections:
            st.markdown("#### Memo")
            for s in memo_sections:
                if len(memo_sections) > 1:
                    st.markdown(f"<p style='color:#888; font-size:12px; margin-bottom:6px;'>{s}</p>", unsafe_allow_html=True)
                render_section(s, strategy_df)

        if pitch_sections:
            st.markdown("---")
            st.markdown("#### Stock Pitch Ideas")
            for s in pitch_sections:
                render_section(s, strategy_df)

        for s in other_sections:
            st.markdown("---")
            st.markdown(f"#### {s}")
            render_section(s, strategy_df)
    else:
        st.info("No files yet — add rows to Finance Blog Strategy sheet!")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — NOTES (public reading view)
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### Notes")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Research notes & market commentary</p>", unsafe_allow_html=True)
    st.markdown("---")

    if st.session_state.view_post_id:
        try:
            ws = get_posts_worksheet()
            records = ws.get_all_records()
            post = next((r for r in records if str(r.get("id","")) == str(st.session_state.view_post_id)), None)
            if post and post.get("status") == "published":
                if st.button("← Back to all notes", key="back_btn"):
                    st.session_state.view_post_id = None
                    st.rerun()
                st.markdown(f"## {post.get('title','')}")
                date_str = post.get("date","")
                updated = post.get("updated_at","")
                st.markdown(f"<p style='color:#888; font-size:12px;'>{date_str} · Last updated {updated[:10] if updated else ''}</p>", unsafe_allow_html=True)
                st.markdown("---")
                st.markdown(f"""
                <div style="max-width: 720px; line-height: 1.9; font-size: 15px;">
                {post.get('content','')}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("Post not found or not published.")
                if st.button("← Back", key="back_btn_err"):
                    st.session_state.view_post_id = None
                    st.rerun()
        except Exception as e:
            st.error(f"Could not load post: {e}")
    else:
        try:
            pub_posts = load_posts(status_filter="published")
            if pub_posts.empty:
                st.info("No published notes yet.")
            else:
                for _, post in pub_posts.iterrows():
                    title = post.get("title", "Untitled")
                    date_str = post.get("date", "")
                    content = post.get("content", "")
                    preview_text = re.sub(r'<[^>]+>', '', content)[:200].strip()
                    if len(re.sub(r'<[^>]+>', '', content)) > 200:
                        preview_text += "..."

                    with st.container():
                        col_a, col_b = st.columns([5, 1])
                        with col_a:
                            st.markdown(f"**{title}**")
                            st.markdown(f"<p style='color:#888; font-size:12px; margin-top:-8px;'>{date_str}</p>", unsafe_allow_html=True)
                            st.markdown(f"<p style='color:#555; font-size:13px; line-height:1.6;'>{preview_text}</p>", unsafe_allow_html=True)
                        with col_b:
                            if st.button("Read →", key=f"read_{post['id']}"):
                                st.session_state.view_post_id = post["id"]
                                st.rerun()
                    st.markdown("<hr style='margin: 0.8rem 0; border-color: #f0f0f0;'>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Could not load posts: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — WRITE (password-protected editor)
# ─────────────────────────────────────────────────────────────────────────────
with tab5:

    if not st.session_state.editor_authenticated:
        st.markdown("### Editor Access")
        st.markdown("<p style='color:#888; font-size:13px;'>This area is private.</p>", unsafe_allow_html=True)
        pw_input = st.text_input("Password", type="password", key="pw_input")
        if st.button("Enter", key="pw_btn"):
            correct_pw = st.secrets.get("post_password", "")
            if pw_input == correct_pw and correct_pw != "":
                st.session_state.editor_authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

    st.markdown("### ✏️ Write")

    list_col, editor_col = st.columns([1, 3])

    with list_col:
        st.markdown("**Your posts**")

        if st.button("＋ New post", use_container_width=True, key="new_post_btn"):
            st.session_state.editing_post_id = str(uuid.uuid4())
            st.session_state.editor_title = ""
            st.session_state.editor_content = ""
            st.session_state.editor_status = "draft"

        st.markdown("---")

        try:
            all_posts = load_posts()
            _ = st.session_state.posts_cache_bust

            if all_posts.empty:
                st.markdown("<p style='color:#888; font-size:12px;'>No posts yet.</p>", unsafe_allow_html=True)
            else:
                for _, p in all_posts.iterrows():
                    status_badge = "🟢" if p.get("status") == "published" else "⚪"
                    label = f"{status_badge} {p.get('title','Untitled')[:28]}"
                    if st.button(label, key=f"edit_{p['id']}", use_container_width=True):
                        st.session_state.editing_post_id = p["id"]
                        st.session_state.editor_title = p.get("title", "")
                        st.session_state.editor_content = p.get("content", "")
                        st.session_state.editor_status = p.get("status", "draft")
        except Exception as e:
            st.error(f"Error loading posts: {e}")

    with editor_col:
        if not st.session_state.editing_post_id:
            st.markdown("""
            <div style="text-align:center; padding: 80px 0; color:#ccc;">
                <p style="font-size:48px;">✏️</p>
                <p style="font-size:14px;">Select a post to edit or create a new one</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            new_title = st.text_input(
                "Title",
                value=st.session_state.editor_title,
                placeholder="Post title...",
                label_visibility="collapsed",
                key=f"title_input_{st.session_state.editing_post_id}"
            )
            st.session_state.editor_title = new_title

            quill_html = f"""
<!DOCTYPE html>
<html>
<head>
  <link href="https://cdn.quilljs.com/1.3.7/quill.snow.css" rel="stylesheet">
  <script src="https://cdn.quilljs.com/1.3.7/quill.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: transparent; font-family: 'DM Mono', monospace; }}
    #toolbar {{
      border: 1px solid #e5e5e5;
      border-bottom: none;
      border-radius: 8px 8px 0 0;
      background: #fff;
      padding: 4px;
    }}
    #editor {{
      border: 1px solid #e5e5e5;
      border-radius: 0 0 8px 8px;
      background: #fff;
      min-height: 420px;
      font-size: 14px;
      line-height: 1.8;
    }}
    .ql-editor {{ min-height: 400px; padding: 20px 24px; }}
    .ql-toolbar button {{ color: #1a1a1a !important; }}
    #save-area {{
      margin-top: 12px;
      display: flex;
      gap: 10px;
      align-items: center;
    }}
    #content-out {{
      position: absolute;
      left: -9999px;
      width: 1px;
      height: 1px;
      opacity: 0;
    }}
    #copy-btn {{
      padding: 8px 20px;
      background: #1a1a1a;
      color: #fafaf8;
      border: none;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      font-family: 'DM Mono', monospace;
      letter-spacing: 0.05em;
    }}
    #copy-btn:hover {{ background: #333; }}
    #copied-msg {{ font-size: 12px; color: #27ae60; display: none; }}
  </style>
</head>
<body>
  <div id="toolbar">
    <span class="ql-formats">
      <select class="ql-header">
        <option value="1">Heading 1</option>
        <option value="2">Heading 2</option>
        <option value="3">Heading 3</option>
        <option selected>Normal</option>
      </select>
    </span>
    <span class="ql-formats">
      <button class="ql-bold"></button>
      <button class="ql-italic"></button>
      <button class="ql-underline"></button>
      <button class="ql-strike"></button>
    </span>
    <span class="ql-formats">
      <button class="ql-blockquote"></button>
      <button class="ql-code-block"></button>
    </span>
    <span class="ql-formats">
      <button class="ql-list" value="ordered"></button>
      <button class="ql-list" value="bullet"></button>
    </span>
    <span class="ql-formats">
      <button class="ql-link"></button>
      <button class="ql-clean"></button>
    </span>
  </div>
  <div id="editor"></div>

  <div id="save-area">
    <button id="copy-btn" onclick="copyContent()">Copy HTML to clipboard</button>
    <span id="copied-msg">✓ Copied!</span>
  </div>

  <textarea id="content-out"></textarea>

  <script>
    var quill = new Quill('#editor', {{
      theme: 'snow',
      modules: {{ toolbar: '#toolbar' }},
      placeholder: 'Start writing your note...'
    }});

    var existing = {repr(st.session_state.editor_content)};
    if (existing && existing.trim() !== '') {{
      quill.root.innerHTML = existing;
    }}

    function copyContent() {{
      var html = quill.root.innerHTML;
      navigator.clipboard.writeText(html).then(function() {{
        document.getElementById('copied-msg').style.display = 'inline';
        setTimeout(function() {{
          document.getElementById('copied-msg').style.display = 'none';
        }}, 2000);
      }});
    }}

    setInterval(function() {{
      var html = quill.root.innerHTML;
      window.parent.postMessage({{type: 'quill-content', html: html}}, '*');
    }}, 2000);
  </script>
</body>
</html>
"""

            import streamlit.components.v1 as components
            components.html(quill_html, height=560, scrolling=False)

            st.markdown("""
            <p style='color:#888; font-size:12px; margin-top:8px;'>
            💡 <b>To save:</b> click "Copy HTML to clipboard" above, then paste it into the box below, then click Save.
            </p>
            """, unsafe_allow_html=True)

            pasted_content = st.text_area(
                "Paste HTML content here:",
                value=st.session_state.editor_content,
                height=120,
                placeholder="Click 'Copy HTML to clipboard' above, then paste here...",
                key=f"paste_area_{st.session_state.editing_post_id}",
                label_visibility="collapsed"
            )
            if pasted_content:
                st.session_state.editor_content = pasted_content

            if st.session_state.editor_content and st.session_state.editor_content.strip() not in ("", "<p><br></p>"):
                with st.expander("Preview", expanded=False):
                    st.markdown(f"""
                    <div style="max-width:680px; line-height:1.9; font-size:15px; padding:12px 0;">
                    {st.session_state.editor_content}
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")
            btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 1])

            with btn_col1:
                if st.button("💾 Save as Draft", use_container_width=True, key="save_draft_btn"):
                    if not st.session_state.editor_title.strip():
                        st.error("Please add a title before saving.")
                    else:
                        try:
                            result = save_post(
                                st.session_state.editing_post_id,
                                st.session_state.editor_title,
                                st.session_state.editor_content,
                                "draft"
                            )
                            st.session_state.editor_status = "draft"
                            st.session_state.posts_cache_bust += 1
                            load_posts.clear()
                            st.success(f"Draft saved! ({result})")
                        except Exception as e:
                            st.error(f"Could not save: {e}")

            with btn_col2:
                if st.button("🚀 Publish", use_container_width=True, key="publish_btn"):
                    if not st.session_state.editor_title.strip():
                        st.error("Please add a title before publishing.")
                    elif not st.session_state.editor_content.strip() or st.session_state.editor_content.strip() == "<p><br></p>":
                        st.error("Content is empty.")
                    else:
                        try:
                            result = save_post(
                                st.session_state.editing_post_id,
                                st.session_state.editor_title,
                                st.session_state.editor_content,
                                "published"
                            )
                            st.session_state.editor_status = "published"
                            st.session_state.posts_cache_bust += 1
                            load_posts.clear()
                            st.success("Published! 🎉 Check the Notes tab.")
                        except Exception as e:
                            st.error(f"Could not publish: {e}")

            with btn_col3:
                if st.button("🗑️ Delete", use_container_width=True, key="delete_btn"):
                    try:
                        delete_post(st.session_state.editing_post_id)
                        st.session_state.editing_post_id = None
                        st.session_state.editor_title = ""
                        st.session_state.editor_content = ""
                        st.session_state.posts_cache_bust += 1
                        load_posts.clear()
                        st.success("Post deleted.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not delete: {e}")

            if st.session_state.editor_status:
                status_color = "#27ae60" if st.session_state.editor_status == "published" else "#888"
                st.markdown(f"<p style='color:{status_color}; font-size:12px;'>Status: {st.session_state.editor_status}</p>", unsafe_allow_html=True)

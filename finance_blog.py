import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

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
</style>
""", unsafe_allow_html=True)

# ── Google Sheets connection ──────────────────────────────────────────────────
SPREADSHEET_ID = "1qZWYbXGTFsDMCp9LPOip1PlJEsS_jnOJStxcKkUAS78"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]

@st.cache_resource
def get_gsheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    # Fix private key formatting — replace literal \n with real newlines
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_macro_news():
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SPREADSHEET_ID)
        ws = sheet.worksheet("Finance Blog Macro")
        records = ws.get_all_records()
        df = pd.DataFrame(records)
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
        title=dict(text=title, font=dict(family="DM Serif Display", size=18), x=0),
        paper_bgcolor="#fafaf8", plot_bgcolor="#fafaf8",
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

# ── Header ────────────────────────────────────────────────────────────────────
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
        ["1 Month", "6 Months", "1 Year", "5 Years"],
        horizontal=True,
        index=1
    )
    period_map = {"1 Month": "1mo", "6 Months": "6mo", "1 Year": "1y", "5 Years": "5y"}
    period_val = period_map[period_label]

    st.plotly_chart(make_chart(
        f"US Indices — {period_label}",
        ["^GSPC", "^IXIC", "^DJI"],
        ["S&P 500", "Nasdaq", "Dow Jones"],
        ["#1a1a1a", "#c0392b", "#2980b9"],
        period=period_val
    ), use_container_width=True)

    st.plotly_chart(make_chart(
        f"Asian Indices — {period_label}",
        ["^N225", "^HSI", "^KS11"],
        ["Nikkei", "Hang Seng", "KOSPI"],
        ["#e74c3c", "#e67e22", "#27ae60"],
        period=period_val
    ), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(make_chart(
            f"Gold & Silver — {period_label}",
            ["GC=F", "SI=F"],
            ["Gold", "Silver"],
            ["#b8860b", "#95a5a6"],
            period=period_val
        ), use_container_width=True)
    with col2:
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

    @st.cache_data(ttl=3600)
    def get_yields_history():
        maturities = {
            "1M": "DGS1MO", "3M": "DGS3MO", "6M": "DGS6MO",
            "1Y": "DGS1", "2Y": "DGS2", "5Y": "DGS5",
            "10Y": "DGS10", "20Y": "DGS20", "30Y": "DGS30"
        }
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        df_list = []
        for label, series_id in maturities.items():
            try:
                url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start_date}"
                s = pd.read_csv(url, index_col=0, na_values=".")
                s.columns = [label]
                df_list.append(s)
            except Exception:
                pass
        if not df_list:
            return pd.DataFrame()
        df = pd.concat(df_list, axis=1)
        df = df.dropna(how='all').ffill().dropna()
        df.index = pd.to_datetime(df.index).strftime('%Y-%m-%d')
        return df[[k for k in maturities.keys() if k in df.columns]]

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
            for i, date in enumerate(selected_dates):
                if date in yield_df.index:
                    fig_yield.add_trace(go.Scatter(
                        x=yield_df.columns, y=yield_df.loc[date],
                        mode="lines+markers", name=date,
                        line=dict(color=colors[i % len(colors)], width=2),
                        marker=dict(size=7),
                        hovertemplate="<b>%{x}</b>: %{y:.3f}%<extra></extra>",
                    ))
            fig_yield.update_layout(
                paper_bgcolor="#fafaf8", plot_bgcolor="#fafaf8",
                margin=dict(l=0, r=0, t=20, b=20), height=260,
                legend=dict(orientation="h", y=-0.25, font=dict(size=11)),
                xaxis=dict(showgrid=False, tickfont=dict(size=11)),
                yaxis=dict(showgrid=True, gridcolor="#ebebeb", ticksuffix="%", tickfont=dict(size=11)),
            )
            st.plotly_chart(fig_yield, use_container_width=True)

    # ── Daily News Table ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Daily Notes")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Updated daily at 4pm · Edit via Google Sheets</p>", unsafe_allow_html=True)

    news_df = load_macro_news()

    if not news_df.empty:
        selected_date = st.radio(
            "Select date:",
            options=news_df["date"].tolist(),
            horizontal=True,
            label_visibility="collapsed",
            format_func=lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%b %d")
        )

        for _, row in news_df.iterrows():
            is_selected = row["date"] == selected_date
            bg = "#1a1a1a" if is_selected else "#f0f0ee"
            fg = "#fafaf8" if is_selected else "#1a1a1a"
            sub = "#aaa" if is_selected else "#888"
            display_date = datetime.strptime(row["date"], "%Y-%m-%d").strftime("%b %d, %Y")
            note_html = str(row.get("note", "")).replace("\n", "<br>")
            st.markdown(f"""
            <div style="background:{bg}; color:{fg}; padding:14px 18px; border-radius:6px; margin-bottom:6px;">
                <div style="font-size:11px; color:{sub}; margin-bottom:4px;">{display_date}</div>
                <div style="font-size:13px; line-height:1.7;">{note_html}</div>
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
        "Utilities": "^SP500-55",
        "Industrials": "^SP500-20",
        "Materials": "^SP500-15",
        "Communication Services": "^SP500-50",
        "Real Estate": "^SP500-60",
    }

    selected_sectors = st.multiselect(
        "Compare Sectors:",
        options=list(sp500_sectors.keys()),
        default=["S&P 500", "Information Technology", "Energy"]
    )

    eq_period_label = st.radio(
        "Timeframe:", ["1 Month", "6 Months", "1 Year", "5 Years"],
        horizontal=True, index=1, key="eq_timeframe"
    )
    eq_period_val = {"1 Month": "1mo", "6 Months": "6mo", "1 Year": "1y", "5 Years": "5y"}[eq_period_label]

    if selected_sectors:
        tickers = [sp500_sectors[s] for s in selected_sectors]
        palette = ["#1a1a1a", "#2980b9", "#c0392b", "#27ae60", "#e67e22", "#8e44ad", "#f39c12"]
        colors = [palette[i % len(palette)] for i in range(len(selected_sectors))]
        st.plotly_chart(make_chart(
            "Sector Relative Performance",
            tickers, selected_sectors, colors,
            percent=True, period=eq_period_val
        ), use_container_width=True)

    st.markdown("---")
    st.markdown("### Sector Notes")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Edit via Google Sheets → Finance Blog Sectors tab</p>", unsafe_allow_html=True)

    sector_df = load_sector_notes()

    if not sector_df.empty and "sector" in sector_df.columns:
        sector_filter = st.selectbox(
            "Filter by sector:",
            ["All"] + sorted(sector_df["sector"].unique().tolist())
        )
        filtered = sector_df if sector_filter == "All" else sector_df[sector_df["sector"] == sector_filter]

        for _, row in filtered.iterrows():
            display_date = datetime.strptime(row["date"], "%Y-%m-%d").strftime("%b %d, %Y")
            note_html = str(row.get("note", "")).replace("\n", "<br>")
            st.markdown(f"""
            <div style="background:#f0f0ee; padding:14px 18px; border-radius:6px; margin-bottom:6px;">
                <div style="font-size:11px; color:#888; margin-bottom:2px;">{display_date} · <b>{row.get('sector','')}</b></div>
                <div style="font-size:13px; line-height:1.7;">{note_html}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No sector notes yet — add rows to your Google Sheet!")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — QUARTERLY OUTLOOK
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Q2 2026 Investment Outlook")
    st.markdown("<p style='color:#888; font-size:12px; margin-top:-10px;'>Last updated: April 2026</p>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("""
#### Macro View
- Fed trajectory, inflation, growth outlook

#### Asset Allocation
- Equities / Fixed Income / Commodities / Cash

#### Key Risks
- Geopolitical, policy, earnings

#### High Conviction Ideas
- Names or themes you're watching
    """)

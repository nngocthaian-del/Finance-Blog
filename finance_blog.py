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
        hovermode="x unified",
        xaxis=dict(showgrid=False, tickfont=dict(size=10), zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#ebebeb", tickfont=dict(size=10),
                   zeroline=True, zerolinecolor="#ccc", zerolinewidth=1,
                   ticksuffix="%" if percent else ""),
        height=380,
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

    # US + Asian indices side by side
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

    # Gold/Silver + Oil side by side
    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(make_chart(
            f"Gold & Silver — {period_label}",
            ["GC=F", "SI=F"],
            ["Gold", "Silver"],
            ["#b8860b", "#95a5a6"],
            period=period_val
        ), use_container_width=True)
    with col4:
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

    # ── Daily News Table ──────────────────────────────────────────────────────
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

    # Export button
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
            note_html = note
            events_html = f"<div style='margin-bottom:6px;'><b>{headline}</b></div><div style='color:#666; font-size:12px; line-height:1.8;'>{note_html}</div>"

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
        if sector_name == "All":
            display_notes = sector_df.to_dict("records")
        else:
            clean_name = sector_name.replace("S&P 500 ", "").replace(" Sector", "")
            filtered = sector_df[sector_df["sector"].str.contains(clean_name, case=False, na=False)]
            display_notes = filtered.to_dict("records")

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

        html += "</table>\n"
        st.markdown(html, unsafe_allow_html=True)
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

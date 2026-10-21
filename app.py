import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import requests
import io
import feedparser
import re
from datetime import datetime, timedelta
from time import mktime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="📈 NSE AI Assistant", layout="wide")

# ---------------- CONSTANTS ----------------

NSE_EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

FALLBACK_STOCK_MAP = {
    "RELIANCE": "Reliance Industries", "TCS": "Tata Consultancy Services",
    "HDFCBANK": "HDFC Bank", "INFY": "Infosys", "ICICIBANK": "ICICI Bank",
    "HINDUNILVR": "Hindustan Unilever", "SBIN": "State Bank of India",
    "BHARTIARTL": "Bharti Airtel", "ITC": "ITC Limited", "KOTAKBANK": "Kotak Mahindra Bank",
    "LT": "Larsen & Toubro", "AXISBANK": "Axis Bank", "ASIANPAINT": "Asian Paints",
    "MARUTI": "Maruti Suzuki", "SUNPHARMA": "Sun Pharmaceutical", "TITAN": "Titan Company",
    "ULTRACEMCO": "UltraTech Cement", "WIPRO": "Wipro", "NESTLEIND": "Nestle India",
    "TATAMOTORS": "Tata Motors", "TATASTEEL": "Tata Steel", "POWERGRID": "Power Grid",
    "NTPC": "NTPC Limited", "HFCL": "HFCL Limited", "ZEEL": "Zee Entertainment",
    "BAJFINANCE": "Bajaj Finance",
}

SECTOR_INDICES = [
    ("Nifty 50", "^NSEI"), ("Sensex", "^BSESN"), ("Bank Nifty", "^NSEBANK"),
    ("Nifty Auto", "^CNXAUTO"), ("Nifty IT", "^CNXIT"), ("Nifty Pharma", "^CNXPHARMA"),
    ("Nifty FMCG", "^CNXFMCG"), ("Nifty Metal", "^CNXMETAL"), ("Nifty Energy", "^CNXENERGY"),
]

TOP20_NIFTY500_TICKERS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS","HINDUNILVR.NS",
    "SBIN.NS","BHARTIARTL.NS","ITC.NS","KOTAKBANK.NS","LT.NS","AXISBANK.NS",
    "ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS","TITAN.NS","ULTRACEMCO.NS","WIPRO.NS",
    "NESTLEIND.NS","TATAMOTORS.NS",
]

NIFTY50_TICKERS = TOP20_NIFTY500_TICKERS + [
    "TATASTEEL.NS","POWERGRID.NS","NTPC.NS","BAJFINANCE.NS","HCLTECH.NS","ADANIENT.NS",
    "ADANIPORTS.NS","BAJAJFINSV.NS","BPCL.NS","CIPLA.NS","COALINDIA.NS","DIVISLAB.NS",
    "DRREDDY.NS","EICHERMOT.NS","GRASIM.NS","HDFCLIFE.NS","HEROMOTOCO.NS","HINDALCO.NS",
    "INDUSINDBK.NS","JSWSTEEL.NS","M&M.NS","ONGC.NS","SBILIFE.NS","SHREECEM.NS",
    "TATACONSUM.NS","TECHM.NS","UPL.NS","APOLLOHOSP.NS","BRITANNIA.NS","LTIM.NS",
]

ALL_FEED_URLS = [
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.moneycontrol.com/rss/business.xml",
    "https://www.moneycontrol.com/rss/results.xml",
    "https://www.livemint.com/rss/markets",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://www.thehindubusinessline.com/markets/feeder/default.rss",
]

NSE_ANNOUNCEMENTS_URL = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
NSE_CORPORATE_ACTION_URL = "https://nsearchives.nseindia.com/content/RSS/corpAll.xml"
NSE_FINANCIAL_RESULTS_URL = "https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml"

NSE_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
FEED_TIMEOUT = 5

POSITIVE_WORDS = ["surge","rally","gain","jump","rise","soar","upgrade","profit","beat",
                   "record","strong","growth","bullish","buy","outperform","high"]
NEGATIVE_WORDS = ["fall","drop","decline","plunge","loss","downgrade","weak","miss",
                   "low","bearish","sell","underperform","crash","slump","cut"]

COMMON_SUFFIX_WORDS = {"limited","ltd","industries","inc","corp","corporation","company",
                        "co","group","india","holdings","enterprises","international"}

# ---------------- STOCK LIST LOADING ----------------

@st.cache_data(ttl=86400)
def load_full_nse_stock_map():
    try:
        resp = requests.get(NSE_EQUITY_LIST_URL, headers=NSE_HEADERS, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        stock_map = {}
        for _, row in df.iterrows():
            symbol = str(row.get("SYMBOL", "")).strip()
            name = str(row.get("NAME OF COMPANY", "")).strip()
            if symbol and name:
                stock_map[symbol] = name
        if len(stock_map) >= 100:
            return stock_map
        return FALLBACK_STOCK_MAP
    except Exception:
        return FALLBACK_STOCK_MAP

@st.cache_data(ttl=86400)
def load_nifty500_list():
    try:
        url = "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"
        resp = requests.get(url, headers=NSE_HEADERS, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        symbols = [f"{str(s).strip()}.NS" for s in df["Symbol"].tolist() if str(s).strip()]
        if len(symbols) >= 100:
            return symbols
        return NIFTY50_TICKERS
    except Exception:
        return NIFTY50_TICKERS

def search_stocks(query, stock_map):
    if not query:
        return []
    query_upper = query.upper()
    results = []
    for symbol, name in stock_map.items():
        if query_upper in symbol.upper() or query_upper in name.upper():
            results.append((symbol, name))
    return results[:30]

# ---------------- NEWS MATCHING ----------------

def get_significant_words(company_name):
    words = re.findall(r"[A-Za-z]+", company_name.lower())
    return [w for w in words if w not in COMMON_SUFFIX_WORDS and len(w) > 2]

def headline_matches_company(headline, company_name):
    sig_words = get_significant_words(company_name)
    if not sig_words:
        return False
    headline_lower = headline.lower()
    headline_words = set(re.findall(r"[a-z]+", headline_lower))
    return all(w in headline_words for w in sig_words)

# ---------------- QUOTE / MARKET DATA ----------------

def get_accurate_quote(ticker):
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        last_price = fi.get("lastPrice") or fi.get("last_price")
        prev_close = fi.get("previousClose") or fi.get("previous_close")
        volume = fi.get("lastVolume") or fi.get("last_volume") or 0
        if last_price is None or prev_close is None:
            return None
        change = last_price - prev_close
        pct_change = (change / prev_close) * 100 if prev_close else 0
        return {
            "price": last_price, "prev_close": prev_close,
            "change": change, "pct_change": pct_change, "volume": volume,
        }
    except Exception:
        return None

def get_ticker_banner_html():
    items = []
    for ticker in TOP20_NIFTY500_TICKERS:
        q = get_accurate_quote(ticker)
        if q:
            symbol = ticker.replace(".NS", "")
            color = "#00ff00" if q["change"] >= 0 else "#ff4444"
            arrow = "▲" if q["change"] >= 0 else "▼"
            items.append(
                f'<span style="color:{color}; margin-right:40px;">{symbol} {q["price"]:.2f} '
                f'{arrow} {q["pct_change"]:.2f}%</span>'
            )
    content = "".join(items) if items else "<span style='color:#ffffff;'>Loading market data...</span>"
    return content

def render_marquee_banner():
    content = get_ticker_banner_html()
    html = f"""
    <marquee behavior="scroll" direction="left" scrollamount="6"
             style="background-color:#1e3a8a; color:#ffffff; padding:8px 0; font-size:16px; font-family:Arial, sans-serif;">
        {content}
    </marquee>
    """
    components.html(html, height=45)

@st.cache_data(ttl=60)
def get_sector_indices_snapshot():
    snapshot = []
    for name, ticker in SECTOR_INDICES:
        q = get_accurate_quote(ticker)
        if q:
            snapshot.append((name, q["price"], q["change"], q["pct_change"]))
        else:
            snapshot.append((name, None, None, None))
    return snapshot

# ---------------- NEWS FEEDS ----------------

def _parse_feed(url):
    try:
        resp = requests.get(url, headers=NSE_HEADERS, timeout=FEED_TIMEOUT)
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception:
        try:
            return feedparser.parse(url)
        except Exception:
            return None

@st.cache_data(ttl=900)
def get_general_news():
    all_entries = []
    for url in ALL_FEED_URLS:
        feed = _parse_feed(url)
        if feed and feed.entries:
            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_dt = datetime.fromtimestamp(mktime(published)) if published else datetime.now()
                all_entries.append({"title": title, "link": link, "published": pub_dt})
    all_entries.sort(key=lambda x: x["published"], reverse=True)
    return all_entries[:50]

@st.cache_data(ttl=900)
def get_nse_announcements():
    feed = _parse_feed(NSE_ANNOUNCEMENTS_URL)
    entries = []
    if feed and feed.entries:
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            pub_dt = datetime.fromtimestamp(mktime(published)) if published else datetime.now()
            entries.append({"title": title, "link": link, "published": pub_dt})
    return entries

@st.cache_data(ttl=900)
def get_nse_corporate_actions():
    feed = _parse_feed(NSE_CORPORATE_ACTION_URL)
    entries = []
    if feed and feed.entries:
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            pub_dt = datetime.fromtimestamp(mktime(published)) if published else datetime.now()
            entries.append({"title": title, "link": link, "published": pub_dt})
    return entries

@st.cache_data(ttl=900)
def get_nse_financial_results():
    feed = _parse_feed(NSE_FINANCIAL_RESULTS_URL)
    entries = []
    if feed and feed.entries:
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            pub_dt = datetime.fromtimestamp(mktime(published)) if published else datetime.now()
            entries.append({"title": title, "link": link, "published": pub_dt})
    return entries

@st.cache_data(ttl=300)
def get_latest_news_sorted():
    return get_general_news()

def render_news_section(entries, empty_message="No news found."):
    if not entries:
        st.info(empty_message)
        return
    for entry in entries:
        st.markdown(f"**{entry['title']}**")
        st.caption(entry["published"].strftime("%d %b %Y, %I:%M %p"))
        if entry.get("link"):
            st.markdown(f"[Read more]({entry['link']})")
        st.divider()

# ---------------- ANALYSIS ENGINE ----------------

def run_full_analysis(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 50:
            return None
        info = stock.info

        close = hist["Close"]
        volume = hist["Volume"]
        price = close.iloc[-1]

        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else ma50

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        macd_bullish = macd_line.iloc[-1] > signal_line.iloc[-1]

        avg_volume = volume.rolling(20).mean().iloc[-1]
        vol_healthy = volume.iloc[-1] > avg_volume * 0.8

        support = close.rolling(50).min().iloc[-1]
        near_support = price <= support * 1.05

        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = (bb_mid + 2 * bb_std).iloc[-1]
        bb_lower = (bb_mid - 2 * bb_std).iloc[-1]
        bb_favorable = bb_lower <= price <= bb_upper

        low14 = close.rolling(14).min()
        high14 = close.rolling(14).max()
        stoch_k = ((close - low14) / (high14 - low14).replace(0, 1e-9) * 100).iloc[-1]
        stoch_ok = 20 <= stoch_k <= 80

        adx_proxy = abs(close.pct_change().rolling(14).mean().iloc[-1]) * 1000
        adx_ok = adx_proxy > 1

        obv = (volume * ((close.diff() > 0).astype(int) * 2 - 1)).cumsum()
        obv_rising = obv.iloc[-1] > obv.iloc[-10] if len(obv) > 10 else True

        williams_r = ((high14.iloc[-1] - price) / (high14.iloc[-1] - low14.iloc[-1] + 1e-9)) * -100
        williams_ok = -80 <= williams_r <= -20

        tp = (hist["High"] + hist["Low"] + hist["Close"]) / 3
        cci = ((tp.iloc[-1] - tp.rolling(20).mean().iloc[-1]) /
               (0.015 * tp.rolling(20).std().iloc[-1] + 1e-9))
        cci_ok = -100 <= cci <= 100

        fib_high = close.rolling(100).max().iloc[-1]
        fib_low = close.rolling(100).min().iloc[-1]
        fib50 = fib_low + 0.5 * (fib_high - fib_low)
        fib_ok = price >= fib50

        golden_cross = ma50 > ma200

        tech_checks = [
            price > ma20, price > ma50, price > ma200,
            30 <= rsi <= 70, macd_bullish, vol_healthy, near_support,
            bb_favorable, stoch_ok, adx_ok, obv_rising, williams_ok,
            cci_ok, fib_ok, golden_cross,
        ]
        tech_labels = [
            "Price above 20-day MA", "Price above 50-day MA", "Price above 200-day MA",
            "RSI in healthy range (30-70)", "MACD bullish crossover", "Volume healthy",
            "Near support level", "Within Bollinger Bands", "Stochastic in range (20-80)",
            "ADX trend strength", "OBV rising", "Williams %R in range",
            "CCI in normal range", "Above Fibonacci 50% level", "Golden Cross (50MA > 200MA)",
        ]
        tech_details = list(zip(tech_labels, tech_checks))
        tech_score = sum(tech_checks) / len(tech_checks) * 100

        profit_margin = info.get("profitMargins", 0) or 0
        roe = info.get("returnOnEquity", 0) or 0
        debt_equity = info.get("debtToEquity", 999) or 999
        revenue_growth = info.get("revenueGrowth", 0) or 0
        pe = info.get("trailingPE", -1) or -1
        pb = info.get("priceToBook", -1) or -1
        earnings_growth = info.get("earningsGrowth", 0) or 0
        current_ratio = info.get("currentRatio", 0) or 0
        operating_margin = info.get("operatingMargins", 0) or 0
        fcf = info.get("freeCashflow", 0) or 0
        div_yield = info.get("dividendYield", 0) or 0
        peg = info.get("pegRatio", -1) or -1
        roa = info.get("returnOnAssets", 0) or 0
        quick_ratio = info.get("quickRatio", 0) or 0
        gross_margin = info.get("grossMargins", 0) or 0

        fund_checks = [
            profit_margin > 0.10, roe > 0.15, debt_equity < 100, revenue_growth > 0.05,
            0 < pe < 40, 0 < pb < 6, earnings_growth > 0.05, current_ratio > 1,
            operating_margin > 0.10, fcf > 0, div_yield > 0, 0 < peg < 2,
            roa > 0.05, quick_ratio > 1, gross_margin > 0.20,
        ]
        fund_labels = [
            "Profit margin > 10%", "ROE > 15%", "Debt/Equity < 100", "Revenue growth > 5%",
            "P/E between 0-40", "P/B between 0-6", "Earnings growth > 5%", "Current ratio > 1",
            "Operating margin > 10%", "Positive free cash flow", "Pays dividend",
            "PEG between 0-2", "ROA > 5%", "Quick ratio > 1", "Gross margin > 20%",
        ]
        fund_details = list(zip(fund_labels, fund_checks))
        fund_score = sum(fund_checks) / len(fund_checks) * 100

        fund_metrics = {
            "Profit Margin": f"{profit_margin*100:.1f}%", "ROE": f"{roe*100:.1f}%",
            "Debt/Equity": f"{debt_equity:.1f}", "Revenue Growth": f"{revenue_growth*100:.1f}%",
            "P/E Ratio": f"{pe:.1f}", "P/B Ratio": f"{pb:.1f}",
            "Earnings Growth": f"{earnings_growth*100:.1f}%", "Current Ratio": f"{current_ratio:.2f}",
            "Operating Margin": f"{operating_margin*100:.1f}%", "Free Cash Flow": f"{fcf:,.0f}",
            "Dividend Yield": f"{div_yield*100:.2f}%", "PEG Ratio": f"{peg:.2f}",
            "ROA": f"{roa*100:.1f}%", "Quick Ratio": f"{quick_ratio:.2f}",
            "Gross Margin": f"{gross_margin*100:.1f}%",
        }

        company_name = info.get("longName", ticker)
        news_entries = get_general_news()
        matched_news = [e for e in news_entries if headline_matches_company(e["title"], company_name)]

        pos_count = sum(1 for e in matched_news if any(w in e["title"].lower() for w in POSITIVE_WORDS))
        neg_count = sum(1 for e in matched_news if any(w in e["title"].lower() for w in NEGATIVE_WORDS))
        total_sentiment = pos_count + neg_count
        news_score = (pos_count / total_sentiment * 100) if total_sentiment > 0 else 50

        overall_score = tech_score * 0.43 + fund_score * 0.43 + news_score * 0.14

        entry_price = price * 0.98
        stop_loss = price * 0.95
        profit_zone_low = price * 1.05
        profit_zone_high = price * 1.10

        return (overall_score, tech_score, fund_score, news_score, price,
                tech_details, fund_details, fund_metrics, entry_price,
                stop_loss, profit_zone_low, profit_zone_high, matched_news, company_name)
    except Exception:
        return None

def quick_score_only(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo")
        if hist.empty or len(hist) < 30:
            return None
        info = stock.info
        close = hist["Close"]
        volume = hist["Volume"]
        price = close.iloc[-1]

        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(min(50, len(close))).mean().iloc[-1]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_bullish = ema12.iloc[-1] > ema26.iloc[-1]
        avg_volume = volume.rolling(20).mean().iloc[-1]
        vol_healthy = volume.iloc[-1] > avg_volume * 0.8

        tech_checks = [price > ma20, price > ma50, 30 <= rsi <= 70, macd_bullish, vol_healthy,
                       price > close.iloc[-5], close.pct_change().tail(10).mean() > 0]
        tech_score = sum(tech_checks) / len(tech_checks) * 100

        profit_margin = info.get("profitMargins", 0) or 0
        roe = info.get("returnOnEquity", 0) or 0
        pe = info.get("trailingPE", -1) or -1
        revenue_growth = info.get("revenueGrowth", 0) or 0
        debt_equity = info.get("debtToEquity", 999) or 999

        fund_checks = [profit_margin > 0.10, roe > 0.15, 0 < pe < 40,
                       revenue_growth > 0.05, debt_equity < 100]
        fund_score = sum(fund_checks) / len(fund_checks) * 100

        overall = tech_score * 0.6 + fund_score * 0.4
        return (ticker.replace(".NS", ""), info.get("longName", ticker), overall, price)
    except Exception:
        return None

def verdict_label(score):
    if score >= 70:
        return "STRONG BUY", "#00c853"
    elif score >= 55:
        return "BUY", "#aeea00"
    elif score >= 40:
        return "HOLD", "#ffd600"
    else:
        return "AVOID", "#ff1744"

# ---------------- UI ----------------

st.title("📈 NSE AI Assistant")

tab_home, tab_analysis, tab_compare, tab_screener, tab_news = st.tabs(
    ["🏠 Home", "🔍 Stock Analysis", "⚖️ vs Nifty 50", "🏆 Nifty 500 Screener", "📰 News"]
)

# ---------------- HOME TAB ----------------
with tab_home:
    st_autorefresh(interval=15 * 60 * 1000, key="refresh_home")

    render_marquee_banner()

    st.subheader("Market Snapshot")
    snapshot = get_sector_indices_snapshot()
    cols = st.columns(len(snapshot))
    for col, (name, price, change, pct) in zip(cols, snapshot):
        with col:
            if price is not None:
                color = "green" if change >= 0 else "red"
                arrow = "▲" if change >= 0 else "▼"
                st.markdown(f"**{name}**")
                st.markdown(f":{color}[{price:,.2f} {arrow} {pct:.2f}%]")
            else:
                st.markdown(f"**{name}**")
                st.caption("Unavailable")

    st.subheader("Latest Headlines")
    headlines = get_latest_news_sorted()
    if headlines:
        for entry in headlines[:15]:
            st.markdown(f"• {entry['title']}")
    else:
        st.info("No headlines available right now.")

# ---------------- STOCK ANALYSIS TAB ----------------
with tab_analysis:
    st.subheader("Stock Analysis")
    stock_map = load_full_nse_stock_map()
    query = st.text_input("Search for a stock (symbol or company name)", key="analysis_search")

    if query:
        matches = search_stocks(query, stock_map)
        if matches:
            options = [f"{sym} — {name}" for sym, name in matches]
            choice = st.radio("Select a stock", options, key="analysis_radio")
            selected_symbol = choice.split(" — ")[0]
            ticker = f"{selected_symbol}.NS"

            with st.spinner(f"Analyzing {selected_symbol}..."):
                result = run_full_analysis(ticker)

            if result:
                (overall_score, tech_score, fund_score, news_score, price,
                 tech_details, fund_details, fund_metrics, entry_price,
                 stop_loss, profit_zone_low, profit_zone_high, matched_news, company_name) = result

                label, color = verdict_label(overall_score)

                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"### {company_name}")
                    st.markdown(f"**Current Price:** ₹{price:,.2f}")
                with col2:
                    st.markdown(
                        f"<div style='background-color:{color}; padding:12px; border-radius:8px; text-align:center;'>"
                        f"<span style='color:black; font-weight:bold; font-size:18px;'>{label}</span><br>"
                        f"<span style='color:black;'>Score: {overall_score:.1f}/100</span></div>",
                        unsafe_allow_html=True,
                    )

                st.markdown("---")
                mcol1, mcol2, mcol3 = st.columns(3)
                mcol1.metric("Technical Score", f"{tech_score:.0f}/100")
                mcol2.metric("Fundamental Score", f"{fund_score:.0f}/100")
                mcol3.metric("News Sentiment", f"{news_score:.0f}/100")

                with st.expander("🎯 Overall Verdict — Entry, Stop-Loss & Profit Zone"):
                    st.markdown(f"**Suggested Entry Price:** ₹{entry_price:,.2f}")
                    st.markdown(f"**Stop-Loss:** ₹{stop_loss:,.2f}")
                    st.markdown(f"**Profit Zone:** ₹{profit_zone_low:,.2f} – ₹{profit_zone_high:,.2f}")

                with st.expander("📊 Technical Breakdown"):
                    for label_text, passed in tech_details:
                        icon = "✅" if passed else "❌"
                        st.markdown(f"{icon} {label_text}")

                with st.expander("📑 Fundamental Breakdown"):
                    metric_items = list(fund_metrics.items())
                    for i in range(0, len(metric_items), 4):
                        row = metric_items[i:i+4]
                        cols = st.columns(4)
                        for col, (k, v) in zip(cols, row):
                            col.metric(k, v)
                    st.markdown("---")
                    for label_text, passed in fund_details:
                        icon = "✅" if passed else "❌"
                        st.markdown(f"{icon} {label_text}")

                with st.expander("📰 Related News"):
                    render_news_section(matched_news, empty_message="No recent news found for this company.")
            else:
                st.error("Could not fetch analysis for this stock. Please try again.")
        else:
            st.info("No matching stocks found.")

# ---------------- VS NIFTY 50 TAB ----------------
with tab_compare:
    st.subheader("Compare vs Nifty 50")
    stock_map = load_full_nse_stock_map()
    query = st.text_input("Search for a stock to compare", key="compare_search")
    period = st.selectbox("Period", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)

    if query:
        matches = search_stocks(query, stock_map)
        if matches:
            options = [f"{sym} — {name}" for sym, name in matches]
            choice = st.radio("Select a stock", options, key="compare_radio")
            selected_symbol = choice.split(" — ")[0]
            ticker = f"{selected_symbol}.NS"

            with st.spinner("Loading comparison..."):
                try:
                    stock_hist = yf.Ticker(ticker).history(period=period)["Close"]
                    nifty_hist = yf.Ticker("^NSEI").history(period=period)["Close"]

                    if not stock_hist.empty and not nifty_hist.empty:
                        stock_norm = stock_hist / stock_hist.iloc[0] * 100
                        nifty_norm = nifty_hist / nifty_hist.iloc[0] * 100

                        chart_df = pd.DataFrame({
                            selected_symbol: stock_norm,
                            "Nifty 50": nifty_norm,
                        })
                        st.line_chart(chart_df)

                        stock_return = (stock_hist.iloc[-1] / stock_hist.iloc[0] - 1) * 100
                        nifty_return = (nifty_hist.iloc[-1] / nifty_hist.iloc[0] - 1) * 100
                        outperformance = stock_return - nifty_return

                        c1, c2, c3 = st.columns(3)
                        c1.metric(f"{selected_symbol} Return", f"{stock_return:.2f}%")
                        c2.metric("Nifty 50 Return", f"{nifty_return:.2f}%")
                        c3.metric("Outperformance", f"{outperformance:.2f}%")
                    else:
                        st.error("Could not load price history.")
                except Exception:
                    st.error("Could not load comparison data.")
        else:
            st.info("No matching stocks found.")

# ---------------- NIFTY 500 SCREENER TAB ----------------
with tab_screener:
    st.subheader("Nifty 500 Screener")
    st.caption("Scans the Nifty 500 universe and buckets stocks by quick score. This may take a few minutes.")

    if st.button("Run Screener"):
        tickers = load_nifty500_list()
        total = len(tickers)
        status_box = st.empty()
        progress = st.progress(0)
        results = []

        for i, ticker in enumerate(tickers):
            status_box.text(f"Scanning {ticker}... ({i+1}/{total})")
            res = quick_score_only(ticker)
            if res:
                results.append(res)
            progress.progress((i + 1) / total)

        status_box.empty()
        progress.empty()

        strong_buy = sorted([r for r in results if r[2] >= 75], key=lambda x: -x[2])[:25]
        buy = sorted([r for r in results if 60 <= r[2] < 75], key=lambda x: -x[2])[:25]
        hold = sorted([r for r in results if 40 <= r[2] < 60], key=lambda x: -x[2])[:25]
        avoid = sorted([r for r in results if r[2] < 40], key=lambda x: x[2])[:25]

        def render_bucket(title, bucket):
            st.markdown(f"#### {title} ({len(bucket)})")
            if bucket:
                df = pd.DataFrame(bucket, columns=["Symbol", "Company", "Score", "Price"])
                df["Score"] = df["Score"].round(1)
                df["Price"] = df["Price"].round(2)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.caption("No stocks in this bucket.")

        render_bucket("🟢 Strong Buy", strong_buy)
        render_bucket("🟡 Buy", buy)
        render_bucket("🟠 Hold", hold)
        render_bucket("🔴 Strongly Avoid", avoid)

# ---------------- NEWS TAB ----------------
with tab_news:
    st.subheader("News")
    news_section = st.radio(
        "Select category",
        ["General Market News", "NSE Corporate Actions", "NSE Announcements", "NSE Financial Results"],
        horizontal=True,
    )

    with st.spinner("Loading news feeds..."):
        if news_section == "General Market News":
            render_news_section(get_general_news())
        elif news_section == "NSE Corporate Actions":
            render_news_section(get_nse_corporate_actions())
        elif news_section == "NSE Announcements":
            render_news_section(get_nse_announcements())
        elif news_section == "NSE Financial Results":
            render_news_section(get_nse_financial_results())
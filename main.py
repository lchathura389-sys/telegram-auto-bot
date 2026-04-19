import asyncio
import time
import math
import requests
import feedparser
from statistics import mean
from telegram import Bot

# =========================
# USER SETTINGS
# =========================
BOT_TOKEN = "8620001412:AAGg3cJTeyy-iR8xkEz-CDHuRyw94C0V0ic"
CHAT_ID = "-5180250509"

SYMBOLS = ["BTCUSDT", "XRPUSDT", "SOLUSDT"]

TREND_INTERVAL = "4h"      # swing direction
TRIGGER_INTERVAL = "1h"    # entry trigger
CHECK_EVERY = 1800         # 30 minutes
COOLDOWN = 6 * 3600        # 6 hours per symbol/side
MIN_SCORE_TO_SEND = 3.5

NEWS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed"
]

# Replace locally only. Do NOT share token.
bot = Bot(token=BOT_TOKEN)
last_signal_time = {}

# =========================
# BINANCE DATA
# =========================
def get_klines(symbol: str, interval: str, limit: int = 300):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def closes(kl):
    return [float(x[4]) for x in kl]

def highs(kl):
    return [float(x[2]) for x in kl]

def lows(kl):
    return [float(x[3]) for x in kl]

def volumes(kl):
    return [float(x[5]) for x in kl]

def ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [mean(values[:period])]
    for p in values[period:]:
        out.append((p * k) + out[-1] * (1 - k))
    return out

def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

    avg_gain = mean(gains)
    avg_loss = mean(losses) if mean(losses) != 0 else 1e-10

    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0)
        loss = abs(min(delta, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period if avg_loss != 0 else 1e-10

    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    return 100 - (100 / (1 + rs))

def atr(highs_, lows_, closes_, period=14):
    if len(closes_) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes_)):
        tr = max(
            highs_[i] - lows_[i],
            abs(highs_[i] - closes_[i - 1]),
            abs(lows_[i] - closes_[i - 1]),
        )
        trs.append(tr)
    current_atr = mean(trs[:period])
    for tr in trs[period:]:
        current_atr = ((current_atr * (period - 1)) + tr) / period
    return current_atr

def pct_distance(a, b):
    if b == 0:
        return 0.0
    return abs((a - b) / b) * 100

# =========================
# SIMPLE NEWS SENTIMENT
# =========================
def symbol_keywords(symbol: str):
    if symbol == "BTCUSDT":
        return ["bitcoin", "btc", "etf"]
    if symbol == "XRPUSDT":
        return ["xrp", "ripple"]
    if symbol == "SOLUSDT":
        return ["solana", "sol"]
    return []

POSITIVE_WORDS = {
    "breakout", "surge", "rally", "inflow", "approval", "adoption",
    "partnership", "launch", "gains", "bullish", "recovery"
}
NEGATIVE_WORDS = {
    "hack", "exploit", "selloff", "drop", "decline", "lawsuit",
    "risk", "bearish", "outflow", "delay", "weakness"
}

def fetch_news_sentiment(symbol: str):
    keys = symbol_keywords(symbol)
    score = 0
    matched = []

    for feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = (entry.get("title") or "").lower()
                summary = (entry.get("summary") or "").lower()
                text = f"{title} {summary}"

                if any(k in text for k in keys):
                    pos_hits = sum(1 for w in POSITIVE_WORDS if w in text)
                    neg_hits = sum(1 for w in NEGATIVE_WORDS if w in text)
                    local = pos_hits - neg_hits
                    score += local
                    if len(matched) < 3:
                        matched.append(entry.get("title", "No title"))
        except Exception:
            continue

    # clamp to manageable range
    if score > 3:
        score = 3
    if score < -3:
        score = -3

    return score, matched

# =========================
# TECHNICAL LOGIC
# =========================
def trend_bias(symbol: str):
    kl = get_klines(symbol, TREND_INTERVAL, 250)
    c = closes(kl)
    e20 = ema(c, 20)
    e50 = ema(c, 50)
    e200 = ema(c, 200)

    if not e20 or not e50 or not e200:
        return "NONE", {}

    last = c[-1]
    info = {
        "price": last,
        "e20": e20[-1],
        "e50": e50[-1],
        "e200": e200[-1],
    }

    if last > e20[-1] > e50[-1] > e200[-1]:
        return "BUY", info
    if last < e20[-1] < e50[-1] < e200[-1]:
        return "SELL", info
    return "NONE", info

def trigger_setup(symbol: str):
    kl = get_klines(symbol, TRIGGER_INTERVAL, 250)
    c = closes(kl)
    h = highs(kl)
    l = lows(kl)
    v = volumes(kl)

    e9 = ema(c, 9)
    e21 = ema(c, 21)
    e50 = ema(c, 50)
    last_rsi = rsi(c, 14)
    last_atr = atr(h, l, c, 14)

    if not e9 or not e21 or not e50 or last_rsi is None or last_atr is None:
        return None

    current = c[-1]
    prev = c[-2]
    avg_vol = mean(v[-20:])
    vol_ok = v[-1] >= avg_vol * 1.05

    bias, info = trend_bias(symbol)
    if bias == "NONE":
        return None

    news_score, headlines = fetch_news_sentiment(symbol)

    # Score components
    tech_score = 0.0
    if bias == "BUY" and current > e9[-1] > e21[-1] > e50[-1]:
        tech_score += 2.0
    elif bias == "SELL" and current < e9[-1] < e21[-1] < e50[-1]:
        tech_score += 2.0

    if vol_ok:
        tech_score += 0.8

    # RSI filter
    if bias == "BUY" and 52 <= last_rsi <= 68:
        tech_score += 1.0
    elif bias == "SELL" and 32 <= last_rsi <= 48:
        tech_score += 1.0

    # Momentum confirm
    if bias == "BUY" and current > prev:
        tech_score += 0.5
    elif bias == "SELL" and current < prev:
        tech_score += 0.5

    total_score = tech_score + (news_score * 0.7)

    # Entry/SL/TP
    if bias == "BUY":
        entry = current
        sl = entry - (last_atr * 1.5)
        tp1 = entry + (last_atr * 2.0)
        tp2 = entry + (last_atr * 3.5)
        reason = "4H uptrend + 1H momentum + headline filter"
    else:
        entry = current
        sl = entry + (last_atr * 1.5)
        tp1 = entry - (last_atr * 2.0)
        tp2 = entry - (last_atr * 3.5)
        reason = "4H downtrend + 1H momentum + headline filter"

    risk = abs(entry - sl)
    reward1 = abs(tp1 - entry)
    rr1 = reward1 / risk if risk else 0.0

    return {
        "symbol": symbol,
        "side": bias,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rsi": last_rsi,
        "atr": last_atr,
        "news_score": news_score,
        "headlines": headlines,
        "score": round(total_score, 2),
        "rr1": round(rr1, 2),
        "reason": reason
    }

def choose_best_setup():
    candidates = []
    for symbol in SYMBOLS:
        try:
            s = trigger_setup(symbol)
            if s is not None:
                candidates.append(s)
        except Exception as e:
            print(f"{symbol} error: {e}")

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x["score"], x["rr1"]), reverse=True)
    best = candidates[0]
    if best["score"] < MIN_SCORE_TO_SEND:
        return None
    return best

# =========================
# TELEGRAM
# =========================
def can_send(symbol: str, side: str):
    key = f"{symbol}_{side}"
    now = time.time()
    prev = last_signal_time.get(key, 0)
    if now - prev >= COOLDOWN:
        last_signal_time[key] = now
        return True
    return False

def fmt(x):
    if x >= 1000:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:.4f}"
    return f"{x:.6f}"

def format_signal(sig: dict):
    news_text = "\n".join([f"• {h}" for h in sig["headlines"][:3]]) if sig["headlines"] else "• No strong matching headlines"

    return f"""
📊 Swing Setup Alert

Symbol: {sig['symbol']}
Side: {sig['side']}
Entry: {fmt(sig['entry'])}
Stop Loss: {fmt(sig['sl'])}
TP1: {fmt(sig['tp1'])}
TP2: {fmt(sig['tp2'])}

RR (to TP1): {sig['rr1']}
RSI: {sig['rsi']:.2f}
News Score: {sig['news_score']}
Setup Score: {sig['score']}

Reason:
{sig['reason']}

Recent headlines:
{news_text}

⚠️ Educational use only. Manage risk.
""".strip()

async def send_text(text: str):
    await bot.send_message(chat_id=CHAT_ID, text=text)

async def main_loop():
    await send_text("✅ News + Swing bot started\nSymbols: BTCUSDT, XRPUSDT, SOLUSDT\nLogic: 4H trend + 1H trigger + headline sentiment")

    while True:
        try:
            sig = choose_best_setup()
            if sig and can_send(sig["symbol"], sig["side"]):
                await send_text(format_signal(sig))
        except Exception as e:
            try:
                await send_text(f"⚠️ Bot error: {str(e)}")
            except Exception:
                pass

        await asyncio.sleep(CHECK_EVERY)

if __name__ == "__main__":
    asyncio.run(main_loop())

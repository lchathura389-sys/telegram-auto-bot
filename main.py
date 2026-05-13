import requests
import pandas as pd
from telegram import Bot
import asyncio

# ===== SETTINGS =====
TELEGRAM_TOKEN = "8655142333:AAFTVIKOX6SC5ec58yfhtMSC959p2AGw"
CHAT_ID = "1003948155655"
API_KEY = "b3b1cf16f1a0417192ca7d304fe20b11"

SYMBOL = "XAU/USD"
INTERVAL = "15min"

# ===== BOT =====
bot = Bot(token=TELEGRAM_TOKEN)

# ===== GET DATA =====
def get_data():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&outputsize=100&apikey={API_KEY}"
    
    response = requests.get(url)
    data = response.json()

    if "values" not in data:
        print("API ERROR:", data)
        return None

    df = pd.DataFrame(data["values"])

    df = df.rename(columns={"datetime": "time"})
    df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)

    return df.iloc[::-1].reset_index(drop=True)

# ===== SMC LOGIC =====
def smc_ict_analysis(df):

    last = df.iloc[-1]

    signal = "NO TRADE"

    bos_buy = last['high'] > df['high'].rolling(10).max().iloc[-2]
    bos_sell = last['low'] < df['low'].rolling(10).min().iloc[-2]

    fvg_buy = df.iloc[-3]['high'] < df.iloc[-1]['low']
    fvg_sell = df.iloc[-3]['low'] > df.iloc[-1]['high']

    liquidity_buy = last['low'] < df['low'].rolling(20).min().iloc[-2]
    liquidity_sell = last['high'] > df['high'].rolling(20).max().iloc[-2]

    if bos_buy and fvg_buy:
        signal = "BUY"
    elif bos_sell and fvg_sell:
        signal = "SELL"

    entry = round(last['close'], 2)

    if signal == "BUY":
        sl = entry - 5
        tp = entry + 10
    elif signal == "SELL":
        sl = entry + 5
        tp = entry - 10
    else:
        sl = None
        tp = None

    return {
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "liquidity_buy": liquidity_buy,
        "liquidity_sell": liquidity_sell
    }

# ===== SEND MSG =====
async def send_signal(msg):
    await bot.send_message(chat_id=CHAT_ID, text=msg)

# ===== MAIN =====
async def main():

    last_signal = None

    while True:
        try:
            df = get_data()

            if df is None:
                await asyncio.sleep(60)
                continue

            result = smc_ict_analysis(df)

            if result["signal"] != "NO TRADE" and result["signal"] != last_signal:

                msg = f"""
📡 XAUUSD SMC + ICT SIGNAL

Signal: {result['signal']}
Entry: {result['entry']}
SL: {result['sl']}
TP: {result['tp']}

Liquidity Buy: {result['liquidity_buy']}
Liquidity Sell: {result['liquidity_sell']}
"""

                await send_signal(msg)
                print(msg)

                last_signal = result["signal"]

            await asyncio.sleep(60)

        except Exception as e:
            print("ERROR:", e)
            await asyncio.sleep(60)

asyncio.run(main())


import requests
import pandas as pd
import numpy as np
from telegram import Bot
import asyncio
import time

# ===== SETTINGS =====
TELEGRAM_TOKEN = "8655142333:AAFTVI-kKOX6SC5ec58yfhtMSC959np2AGw"
CHAT_ID = "8655142333"

SYMBOL = "XAUUSD"
TIMEFRAME = "15m"

# ===== TELEGRAM =====
bot = Bot(token=8655142333:AAFTVI-kKOX6SC5ec58yfhtMSC959np2AGw)

# ===== GET MARKET DATA =====
def get_data():

    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=15min&outputsize=100&apikey={b3b1cf16f1a0417192ca7d304fe20b11}"

    response = requests.get(url)
    data = response.json()

    df = pd.DataFrame(data['values'])

    df = df.rename(columns={
        'datetime':'time'
    })

    df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)

    return df[::-1]


# ===== SMC + ICT ANALYSIS =====
def smc_ict_analysis(df):

    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "NO TRADE"

    # Break Of Structure
    bos_buy = last['high'] > df['high'].rolling(10).max().iloc[-2]
    bos_sell = last['low'] < df['low'].rolling(10).min().iloc[-2]

    # Fair Value Gap
    fvg_buy = df.iloc[-3]['high'] < df.iloc[-1]['low']
    fvg_sell = df.iloc[-3]['low'] > df.iloc[-1]['high']

    # Liquidity Sweep
    liquidity_buy = last['low'] < df['low'].rolling(20).min().iloc[-2]
    liquidity_sell = last['high'] > df['high'].rolling(20).max().iloc[-2]

    # BUY SIGNAL
    if bos_buy and fvg_buy:
        signal = "BUY"

    # SELL SIGNAL
    elif bos_sell and fvg_sell:
        signal = "SELL"

    entry = round(last['close'], 2)

    if signal == "BUY":
        sl = round(entry - 5, 2)
        tp = round(entry + 10, 2)

    elif signal == "SELL":
        sl = round(entry + 5, 2)
        tp = round(entry - 10, 2)

    else:
        sl = "-"
        tp = "-"

    return {
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "liquidity_buy": liquidity_buy,
        "liquidity_sell": liquidity_sell
    }

# ===== SEND TELEGRAM ALERT =====
async def send_signal(message):
    await bot.send_message(chat_id=CHAT_ID, text=message)

# ===== MAIN LOOP =====
async def main():

    last_signal = ""

    while True:
        try:
            df = get_data()
            result = smc_ict_analysis(df)

            current_signal = result['signal']

            if current_signal != "NO TRADE" and current_signal != last_signal:

                msg = f"""
📡 XAUUSD SMC + ICT SIGNAL

Signal: {result['signal']}
Entry: {result['entry']}
SL: {result['sl']}
TP: {result['tp']}

Liquidity Buy Sweep: {result['liquidity_buy']}
Liquidity Sell Sweep: {result['liquidity_sell']}

⚠️ Auto Generated Signal
"""

                await send_signal(msg)
                print(msg)

                last_signal = current_signal

            time.sleep(60)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(60)

# ===== RUN =====
asyncio.run(main())

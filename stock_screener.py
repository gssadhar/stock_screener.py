import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd
import yfinance as yf

# Email Settings from GitHub Secrets
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", "g_lally@yahoo.co.uk")

# Diversified Global Multi-Cap Universe
SCREEN_UNIVERSE = [
    # Growth / Tech Leaders
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "AVGO",
    "AMD",
    "TSLA",
    # Value / Defensive / Large Caps
    "BRK-B",
    "JPM",
    "BAC",
    "V",
    "MA",
    "PG",
    "KO",
    "PEP",
    "COST",
    "HD",
    "CAT",
    "GE",
    "XOM",
    "CVX",
    # Healthcare
    "LLY",
    "JNJ",
    "UNH",
    "PFE",
    "ABBV",
    "MRK",
    # Global Giants (Europe, UK, Asia ADRs)
    "SHEL",
    "AZN",
    "GSK",
    "HSBC",
    "UL",
    "NVO",
    "ASML",
    "SAP",
    "TSM",
    "BABA",
    "SONY",
    # Mid/Small Caps
    "CROX",
    "CELH",
    "ELF",
    "DUOL",
    "ONTO",
    "MEDP",
    "WING",
    "BOOT",
    "SBUX",
]


def classify_market_cap(mcap):
  if not mcap or mcap == 0:
    return "N/A"
  elif mcap >= 10_000_000_000:
    return "Large Cap"
  elif mcap >= 2_000_000_000:
    return "Mid Cap"
  else:
    return "Small Cap"


def generate_signal_and_reason(
    uptrend, golden_cross, macd_bull, rsi, peg_ratio, price, sma_200
):
  """Evaluates data to assign Buy/Hold/Sell signal with primary reasoning."""
  reasons = []

  # Check Technical Conditions
  if uptrend:
    reasons.append("Above 200-SMA")
  else:
    reasons.append("Below 200-SMA (Downtrend)")

  if golden_cross:
    reasons.append("50-SMA > 200-SMA Cross")

  if macd_bull:
    reasons.append("MACD Bullish Momentum")
  else:
    reasons.append("MACD Bearish Crossover")

  # Valuation & RSI Checks
  if rsi > 70:
    reasons.append("Overbought RSI (>70)")
  elif rsi < 30:
    reasons.append("Oversold RSI (<30)")

  if peg_ratio and peg_ratio > 2.5:
    reasons.append("High Valuation (PEG > 2.5)")

  # --- Signal Decision Logic ---
  if not uptrend and macd_bull == False:
    signal = "SELL / AVOID"
    primary_reason = "Strong Downtrend & Bearish MACD Momentum"
  elif rsi > 72 or (peg_ratio and peg_ratio > 3.0):
    signal = "SELL / TRIM"
    primary_reason = "Overbought RSI or Overextended Valuation"
  elif uptrend and golden_cross and macd_bull and (35 <= rsi <= 65):
    if peg_ratio and peg_ratio <= 1.5:
      signal = "STRONG BUY"
      primary_reason = "Bullish Technical Setup + Growth at Reasonable Price"
    else:
      signal = "BUY"
      primary_reason = "Bullish Trend Confirmation & Healthy RSI Momentum"
  elif uptrend or macd_bull:
    signal = "HOLD"
    primary_reason = "Mixed Signals; Price Holding Trend Support"
  else:
    signal = "HOLD"
    primary_reason = "Consolidating Neutral Setup"

  return signal, primary_reason


def screen_stock(symbol):
  ticker_obj = yf.Ticker(symbol)
  df = ticker_obj.history(period="1y", interval="1d")

  if len(df) < 200:
    return None

  try:
    info = ticker_obj.info
    mcap = info.get("marketCap", 0)
    pe_ratio = info.get("forwardPE", info.get("trailingPE", None))
    peg_ratio = info.get("pegRatio", None)
    sector = info.get("sector", "N/A")
  except Exception:
    mcap, pe_ratio, peg_ratio, sector = 0, None, None, "N/A"

  cap_category = classify_market_cap(mcap)

  # Technical Indicators
  df["SMA_50"] = df["Close"].rolling(50).mean()
  df["SMA_200"] = df["Close"].rolling(200).mean()

  delta = df["Close"].diff()
  gain = (delta.where(delta > 0, 0)).rolling(14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
  rs = gain / loss
  df["RSI"] = 100 - (100 / (1 + rs))

  ema12 = df["Close"].ewm(span=12, adjust=False).mean()
  ema26 = df["Close"].ewm(span=26, adjust=False).mean()
  df["MACD"] = ema12 - ema26
  df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

  latest = df.iloc[-1]

  uptrend = bool(latest["Close"] > latest["SMA_200"])
  golden_cross = bool(latest["SMA_50"] > latest["SMA_200"])
  macd_bull = bool(latest["MACD"] > latest["Signal"])
  rsi_val = float(latest["RSI"])

  # Generate Signal & Rationale
  signal, primary_reason = generate_signal_and_reason(
      uptrend=uptrend,
      golden_cross=golden_cross,
      macd_bull=macd_bull,
      rsi=rsi_val,
      peg_ratio=peg_ratio,
      price=latest["Close"],
      sma_200=latest["SMA_200"],
  )

  fifty_two_high = df["High"].max()
  pullback = round(((fifty_two_high - latest["Close"]) / fifty_two_high) * 100, 1)

  return {
      "Ticker": symbol,
      "Sector": sector,
      "Cap Size": cap_category,
      "Price": f"${latest['Close']:.2f}",
      "Signal": signal,
      "Primary Rationale": primary_reason,
      "RSI": round(rsi_val, 1),
      "P/E": round(pe_ratio, 1) if pe_ratio else "N/A",
      "PEG": round(peg_ratio, 2) if peg_ratio else "N/A",
      "Off 52W High": f"-{pullback}%",
  }


def send_email_alert(report_df):
  if not SENDER_EMAIL or not SENDER_PASSWORD:
    print("Missing email configuration credentials. Skipping send.")
    return

  msg = MIMEMultipart("alternative")
  msg["Subject"] = (
      f"🌐 GLOBAL EQUITY SIGNALS ({len(report_df)} Tickers Evaluated)"
  )
  msg["From"] = SENDER_EMAIL
  msg["To"] = RECEIVER_EMAIL

  html_table = report_df.to_html(index=False, border=1, justify="center")

  html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #222;">
        <h2>Global Multi-Cap Equity Signals & Rationale</h2>
        <p>Breakdown of Buy, Hold, and Sell signals with primary rationale across global equities:</p>
        {html_table}
        <br>
        <p><b>Signals Key:</b> STRONG BUY / BUY (Trend & Valuation Aligned), HOLD (Neutral/Consolidating), SELL (Downtrend or Overextended).</p>
      </body>
    </html>
    """

  msg.attach(MIMEText(html_body, "html"))

  try:
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    server.quit()
    print(f"-> Alert email sent successfully to {RECEIVER_EMAIL}!")
  except Exception as e:
    print(f"Failed sending email: {e}")


def run_screener():
  print("=== EVALUATING GLOBAL EQUITIES WITH SIGNALS ===")
  results = []

  for ticker in SCREEN_UNIVERSE:
    try:
      candidate = screen_stock(ticker)
      if candidate:
        results.append(candidate)
    except Exception as e:
      print(f"Error evaluating {ticker}: {e}")

  if results:
    report_df = pd.DataFrame(results)
    print("\n--- GLOBAL WATCHLIST SIGNALS ---")
    print(report_df.to_string(index=False))
    send_email_alert(report_df)


if __name__ == "__main__":
  run_screener()

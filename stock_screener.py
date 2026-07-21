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

# Multi-Cap, Global, Sector-Diversified Universe (Large, Mid, Small Caps & Value/Growth)
SCREEN_UNIVERSE = [
    # US Mega/Large Growth & Tech
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "AVGO",
    "AMD",
    "TSLA",
    # US Large Value, Financials & Industrial
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
    # Healthcare & Biotech
    "LLY",
    "JNJ",
    "UNH",
    "PFE",
    "ABBV",
    "MRK",
    # Global / International ADRs (UK, Europe, Asia)
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
    # Mid-Cap & Small-Cap High Growth / Value
    "CROX",
    "CELH",
    "ELF",
    "DUOL",
    "RBNK",
    "ONTO",
    "MEDP",
    "WING",
    "BOOT",
    "SBUX",
    "PATH",
]


def classify_market_cap(mcap):
  """Classifies company into Large, Mid, or Small Cap."""
  if not mcap or mcap == 0:
    return "N/A"
  elif mcap >= 10_000_000_000:
    return "Large Cap"
  elif mcap >= 2_000_000_000:
    return "Mid Cap"
  else:
    return "Small Cap"


def screen_stock(symbol):
  """Evaluates technicals & fundamentals across Growth, Value, and Size."""
  ticker_obj = yf.Ticker(symbol)

  # Download 1 year daily history
  df = ticker_obj.history(period="1y", interval="1d")
  if len(df) < 200:
    return None

  # Retrieve Fundamental Data safely
  try:
    info = ticker_obj.info
    mcap = info.get("marketCap", 0)
    pe_ratio = info.get("forwardPE", info.get("trailingPE", None))
    peg_ratio = info.get("pegRatio", None)
    sector = info.get("sector", "N/A")
  except Exception:
    mcap, pe_ratio, peg_ratio, sector = 0, None, None, "N/A"

  cap_category = classify_market_cap(mcap)

  # --- Technical Calculations ---
  df["SMA_50"] = df["Close"].rolling(50).mean()
  df["SMA_200"] = df["Close"].rolling(200).mean()

  # RSI
  delta = df["Close"].diff()
  gain = (delta.where(delta > 0, 0)).rolling(14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
  rs = gain / loss
  df["RSI"] = 100 - (100 / (1 + rs))

  # MACD
  ema12 = df["Close"].ewm(span=12, adjust=False).mean()
  ema26 = df["Close"].ewm(span=26, adjust=False).mean()
  df["MACD"] = ema12 - ema26
  df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

  latest = df.iloc[-1]

  # --- Screening Conditions ---
  uptrend = latest["Close"] > latest["SMA_200"]
  golden_cross = latest["SMA_50"] > latest["SMA_200"]
  macd_bull = latest["MACD"] > latest["Signal"]
  rsi_healthy = 40 <= latest["RSI"] <= 65

  # Valuation check (Value or Growth at Reasonable Price)
  valuation_ok = True
  if peg_ratio and peg_ratio > 2.5:  # Filter out hyper-overvalued growth
    valuation_ok = False

  score = sum([uptrend, golden_cross, macd_bull, rsi_healthy, valuation_ok])

  # Require 4+ score for candidate shortlist
  if score >= 4:
    fifty_two_high = df["High"].max()
    pullback = round(((fifty_two_high - latest["Close"]) / fifty_two_high) * 100, 1)

    return {
        "Ticker": symbol,
        "Sector": sector,
        "Cap Size": cap_category,
        "Price": f"${latest['Close']:.2f}",
        "Score": f"{score}/5",
        "RSI": round(latest["RSI"], 1),
        "P/E": round(pe_ratio, 1) if pe_ratio else "N/A",
        "PEG": round(peg_ratio, 2) if peg_ratio else "N/A",
        "50 SMA Supp": f"${latest['SMA_50']:.2f}",
        "Off 52-Wk High": f"-{pullback}%",
    }
  return None


def send_email_alert(report_df):
  """Sends structured HTML report to user email."""
  if not SENDER_EMAIL or not SENDER_PASSWORD:
    print("Missing email configuration credentials. Skipping send.")
    return

  msg = MIMEMultipart("alternative")
  msg["Subject"] = (
      f"🌐 GLOBAL MULTI-CAP STOCK SCREENER ({len(report_df)} Watchlist Picks)"
  )
  msg["From"] = SENDER_EMAIL
  msg["To"] = RECEIVER_EMAIL

  html_table = report_df.to_html(index=False, border=1, justify="center")

  html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #222;">
        <h2>Global Diversified Stock Screener</h2>
        <p>Shortlist of global equities matching institutional trend & fundamental valuation thresholds:</p>
        {html_table}
        <br>
        <p><b>Legend:</b> Score is out of 5 (Technicals + Valuation). P/E & PEG monitor Growth vs Value parameters.</p>
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
  print("=== SCREENING GLOBAL MULTI-CAP EQUITIES ===")
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
    print("\n--- QUALIFIED GLOBAL WATCHLIST ---")
    print(report_df.to_string(index=False))
    send_email_alert(report_df)
  else:
    print("\nNo stocks met all high-conviction criteria today.")


if __name__ == "__main__":
  run_screener()

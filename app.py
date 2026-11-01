from flask import Flask, jsonify, send_from_directory, request
import requests
import io
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

import yfinance as yf
import pandas as pd
from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)


app = Flask(__name__, static_folder='frontend', static_url_path='')

ASSETS = [
    {'ticker': 'BNP.PA', 'name': 'BNP Paribas'}, {'ticker': 'ISP.MI', 'name': 'Intesa Sanpaolo'},
    {'ticker': 'PST.MI', 'name': 'Poste'}, {'ticker': 'G.MI', 'name': 'Generali'},
    {'ticker': 'CS.PA', 'name': 'AXA'}, {'ticker': 'ALV.DE', 'name': 'Allianz'},
    {'ticker': 'OR.PA', 'name': "L'Oréal"}, {'ticker': 'TTE.PA', 'name': 'TotalEnergies'},
    {'ticker': 'GOOGL', 'name': 'Google'}, {'ticker': '^GSPC', 'name': 'S&P 500'},
    {'ticker': '^IXIC', 'name': 'Nasdaq'}, {'ticker': 'CL=F', 'name': 'Brent'},
    {'ticker': '^VIX', 'name': 'VIX'}, {'ticker': '^TNX', 'name': 'Treasury 10Y'},
    {'ticker': '^HSI', 'name': 'Hang Seng (HK)'},
    {'ticker': '^N225', 'name': 'Nikkei 225 (JP)'},
    {'ticker': '^KS11', 'name': 'KOSPI (KR)'},
    {'ticker': '^TWII', 'name': 'Taiwan Weighted (TW)'}
]

PERIOD_MAP = {'1D': '1d', '1W': '5d', '1M': '1mo', '1Y': '1y', '5Y': '5y', 'MAX': 'max'}

@app.route('/')
def index(): return send_from_directory('frontend', 'index.html')

@app.route('/api/assets')
def get_assets(): return jsonify(ASSETS)

@app.route('/api/history/<path:ticker>')
def get_history(ticker):
    period = PERIOD_MAP.get(request.args.get('period', '1M').upper(), '1mo')
    clean_ticker = ticker.replace('$', '')
    try:
        data = yf.Ticker(clean_ticker).history(period=period)
        if data.empty: return jsonify([])
        data.reset_index(inplace=True)
        records = []
        for _, row in data.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d') if hasattr(row['Date'], 'strftime') else str(row['Date'])[:10]
            records.append({'time': date_str, 'value': float(row['Close'])})
        return jsonify(records)
    except Exception as e:
        print(f"Errore per {ticker}: {e}")
        return jsonify([])

@app.route('/api/dividends/<path:ticker>')
def get_dividends(ticker):
    clean_ticker = ticker.replace('$', '')
    try:
        t = yf.Ticker(clean_ticker)
        divs = t.dividends
        if divs.empty: return jsonify([])
        records = []
        for date, value in divs.items():
            records.append({'date': date.strftime('%Y-%m-%d'), 'amount': float(value)})
        return jsonify(records[::-1]) # Dal più recente
    except Exception as e:
        return jsonify([])

@app.route('/api/candles/<path:ticker>')
def get_candles(ticker):
    clean_ticker = ticker.replace('$', '')
    period = PERIOD_MAP.get(request.args.get('period', '1M').upper(), '1mo')
    try:
        data = yf.Ticker(clean_ticker).history(period=period)
        if data.empty: return jsonify([])
        data.reset_index(inplace=True)
        records = []
        for _, row in data.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d') if hasattr(row['Date'], 'strftime') else str(row['Date'])[:10]
            records.append({
                'time': date_str,
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close'])
            })
        return jsonify(records)
    except Exception as e:
        return jsonify([])

@app.route('/api/financials/<path:ticker>')
def get_financials(ticker):
    clean_ticker = ticker.replace('$', '')
    statement = request.args.get('statement', 'income') # income, balance, cashflow
    period = request.args.get('period', 'annual') # annual, quarterly
    
    try:
        t = yf.Ticker(clean_ticker)
        if period == 'annual':
            if statement == 'income':
                df = t.get_income_stmt(freq='yearly')
                if df is None or df.empty: df = t.income_stmt
            elif statement == 'balance':
                df = t.get_balance_sheet(freq='yearly')
                if df is None or df.empty: df = t.balance_sheet
            else:
                df = t.get_cash_flow(freq='yearly')
                if df is None or df.empty: df = t.cashflow
        else:
            if statement == 'income':
                df = t.get_income_stmt(freq='quarterly')
                if df is None or df.empty: df = t.quarterly_income_stmt
            elif statement == 'balance':
                df = t.get_balance_sheet(freq='quarterly')
                if df is None or df.empty: df = t.quarterly_balance_sheet
            else:
                df = t.get_cash_flow(freq='quarterly')
                if df is None or df.empty: df = t.quarterly_cashflow
            
        if df is None or df.empty: return jsonify({})
        
        # Formatta le date come stringhe per il JSON
        df.columns = [col.strftime('%Y-%m-%d') if hasattr(col, 'strftime') else str(col) for col in df.columns]
        # Pulisci i valori NaN
        df = df.fillna(0)
        return jsonify(df.to_dict())
    except Exception as e:
        print(f"Errore bilanci {ticker}: {e}")
        return jsonify({})

@app.route('/api/calendar/<path:ticker>')
def get_calendar(ticker):
    clean_ticker = ticker.replace('$', '')
    result = {}
    
    # 1. Date Utili (via Alpha Vantage)
    ALPHA_KEY = 'BTTG7OK3VW8SSEGN'
    try:
        url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&symbol={clean_ticker}&horizon=3month&apikey={ALPHA_KEY}"
        r = requests.get(url)
        if r.status_code == 200 and 'symbol' in r.text:
            lines = r.text.strip().split('\n')
            if len(lines) > 1:
                # Il CSV ha: symbol,name,reportDate,fiscalDateEnding,estimate,currency
                parts = lines[1].split(',') 
                if len(parts) >= 3:
                    result['Prossima Trimestrale'] = parts[2] # reportDate
    except Exception as e:
        print(f"Errore AlphaVantage: {e}")

    # 2. Dividendi (via yfinance)
    try:
        t = yf.Ticker(clean_ticker)
        info = t.info
        div_date = info.get('dividendDate') or info.get('exDividendDate')
        if div_date:
            result['Data Dividendo'] = pd.to_datetime(div_date, unit='s').strftime('%Y-%m-%d')
        div_rate = info.get('dividendRate')
        if div_rate:
            result['Importo Div. Atteso'] = f"{div_rate:.2f}"
    except Exception as e:
        print(f"Errore Dividendi: {e}")
        
    return jsonify(result)

@app.route('/api/yields')
def get_yields():
    year = datetime.now().year
    url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
    try:
        response = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        # Il formato delle date è MM/DD/YYYY
        df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y', errors='coerce')
        df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
        latest = df.iloc[-1]
        
        # Le colonne del CSV hanno nomi come "1 Mo", "2 Mo", ..., "30 Yr"
        column_map = {
            '1 Mo': '1M', '2 Mo': '2M', '3 Mo': '3M', '4 Mo': '4M', '6 Mo': '6M',
            '1 Yr': '1Y', '2 Yr': '2Y', '3 Yr': '3Y', '5 Yr': '5Y', '7 Yr': '7Y',
            '10 Yr': '10Y', '20 Yr': '20Y', '30 Yr': '30Y'
        }
        curve = {}
        for col, label in column_map.items():
            if col in df.columns:
                val = latest[col]
                if pd.notna(val):
                    try:
                        curve[label] = round(float(val), 3)
                    except (ValueError, TypeError):
                        pass
        
        print(f"[YIELDS] Data: {latest['Date'].strftime('%Y-%m-%d')}, Scadenze trovate: {list(curve.keys())}")
        return jsonify({
            'date': latest['Date'].strftime('%Y-%m-%d'),
            'curve': curve
        })
    except Exception as e:
        print(f"[YIELDS] Errore: {e}")
        return jsonify({'error': str(e), 'curve': {}})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    ticker = data.get('ticker')
    message = data.get('message', 'Fai un\'analisi completa del titolo.')
    
    if not ticker:
        return jsonify({'reply': 'Ticker mancante.'}), 400
    
    clean_ticker = ticker.replace('$', '')
    t = yf.Ticker(clean_ticker)
    
    try:
        # 1. Raccolta dati tecnici (1 anno di storico)
        hist = t.history(period='1y')
        if hist.empty:
            return jsonify({'reply': 'Dati storici non disponibili per questo titolo.'})
        
        close_prices = hist['Close']
        current_price = float(close_prices.iloc[-1])
        
        ema50 = float(close_prices.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close_prices.ewm(span=200, adjust=False).mean().iloc[-1])
        
        delta = close_prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs)).iloc[-1])
        
        # 2. Raccolta dati fondamentali
        info = t.info
        div_rate = info.get('dividendRate', 0) or 0
        div_yield_gross = (div_rate / current_price * 100) if current_price > 0 else 0
        div_yield_net = div_yield_gross * 0.74  # Stima netta con tassazione 26%
        
        eps = info.get('trailingEps', 0) or 0
        pe_ratio = (current_price / eps) if eps != 0 else 0
        
        target_mean = info.get('targetMeanPrice', 0) or 0
        target_high = info.get('targetHighPrice', 0) or 0
        target_low = info.get('targetLowPrice', 0) or 0
        recommendation = info.get('recommendationKey', 'N/D')
        num_analysts = info.get('numberOfAnalystOpinions', 0) or 0
        upside = ((target_mean - current_price) / current_price * 100) if target_mean and current_price else 0
        
        # 3. Dati macro
        vix_data = yf.Ticker('^VIX').history(period='1d')
        vix = float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 0
        tnx_data = yf.Ticker('^TNX').history(period='1d')
        tnx = float(tnx_data['Close'].iloc[-1]) if not tnx_data.empty else 0
        
        # 4. Notizie recenti (prime 5)
        news_items = t.news[:5] if t.news else []
        news_titles = "\n".join([f"- {n.get('title', 'Senza titolo')}" for n in news_items]) if news_items else "Nessuna notizia recente."
        
        # 5. Bilanci
        income = t.income_stmt
        cashflow = t.cashflow
        income_summary = "Non disponibile"
        cashflow_summary = "Non disponibile"
        
        if not income.empty:
            rev = income.loc['Total Revenue'].iloc[0] if 'Total Revenue' in income.index else 0
            net = income.loc['Net Income'].iloc[0] if 'Net Income' in income.index else 0
            income_summary = f"Ricavi: {rev}, Utile Netto: {net}"
            
        if not cashflow.empty:
            ocf = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
            fcf = cashflow.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cashflow.index else 0
            cashflow_summary = f"Cash Flow Operativo: {ocf}, Free Cash Flow: {fcf}"

        # 6. Costruzione del Prompt per Gemini
        trend = "rialzista" if ema50 > ema200 else "ribassista"
        rsi_zone = "ipercomprato" if rsi > 70 else "ipervenduto" if rsi < 30 else "neutro"
        macro_status = "risk-off" if vix > 20 else "risk-on" if vix < 15 else "neutro"

        prompt = f"""
Sei un analista finanziario esperto. Rispondi alla domanda dell'utente usando i dati forniti qui sotto come base principale per i dati tecnici e fondamentali (EMA, RSI, Dividend Yield, P/E, bilanci). Se la domanda riguarda informazioni che NON sono nei dati (es. nomi di banche d'affari che coprono il titolo, target price individuali, notizie recentissime), puoi e devi usare la Ricerca Google per trovarle, citando la fonte.

DATI PER {clean_ticker}:
- Prezzo attuale: {current_price:.2f}
- EMA 50: {ema50:.2f}, EMA 200: {ema200:.2f} → Trend: {trend}
- RSI (14): {rsi:.2f} → Zona: {rsi_zone}
- Dividend Yield Lordo: {div_yield_gross:.2f}% (Netto stimato: {div_yield_net:.2f}%)
- P/E ratio: {pe_ratio:.2f} (EPS: {eps:.2f})
- Consensus analisti: {recommendation} ({num_analysts} analisti)
- Target price medio: {target_mean:.2f} (range {target_low:.2f} - {target_high:.2f})
- Upside potenziale: {upside:.2f}% rispetto al prezzo attuale
- VIX: {vix:.2f} → Sentiment: {macro_status}
- Rendimento Treasury 10Y: {tnx:.2f}%


NOTIZIE RECENTI (ultime 5):
{news_titles}

DATI DI BILANCIO (ultimo anno):
Conto Economico: {income_summary}
Cash Flow: {cashflow_summary}

ISTRUZIONI PER LA RISPOSTA:
Se la domanda dell'utente è generica (es. "Come va il titolo?", "Fai un'analisi", "Analizza il titolo") oppure è la prima richiesta automatica, fornisci un'analisi completa strutturata ESATTAMENTE nei seguenti 6 punti:
1. Analisi del trend tecnico (EMA e RSI).
2. Valutazione e Dividendi (Dividend Yield e P/E).
3. Consensus degli analisti e Upside.
4. Contesto macroeconomico e Notizie.
5. Salute finanziaria (bilancio dell'ultimo anno).
6. Sintesi, Rischi e Opportunità.

Se invece la domanda dell'utente è specifica (es. "Qual è il P/E?", "Conviene comprare?", "Che dividendo paga?", "Chi è l'AD?"), rispondi in modo mirato e sintetico, usando SOLO i dati forniti. NON ripetere l'analisi completa se non richiesto.

Domanda dell'utente: {message}
"""

        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt
        )
        return jsonify({'reply': response.text})

    except Exception as e:
        print(f"Errore chat: {e}")
        return jsonify({'reply': f"Errore durante l'elaborazione: {str(e)}"})

if __name__ == '__main__': app.run(debug=True, port=5000, threaded=True)


import yfinance as yf
import json

tickers = ['BNP.PA', 'ISP.MI', 'PST.MI', 'G.MI', 'CS.PA', 'ALV.DE', 'OR.PA', 'TTE.PA', 'GOOGL']

# Dizionario per salvare i campi
schema_completo = {}

for ticker in tickers:
    t = yf.Ticker(ticker)
    schema_completo[ticker] = {
        'income_annual': list(t.income_stmt.index) if t.income_stmt is not None and not t.income_stmt.empty else [],
        'balance_annual': list(t.balance_sheet.index) if t.balance_sheet is not None and not t.balance_sheet.empty else [],
        'cashflow_annual': list(t.cashflow.index) if t.cashflow is not None and not t.cashflow.empty else [],
        'income_quarterly': list(t.quarterly_income_stmt.index) if t.quarterly_income_stmt is not None and not t.quarterly_income_stmt.empty else [],
        'balance_quarterly': list(t.quarterly_balance_sheet.index) if t.quarterly_balance_sheet is not None and not t.quarterly_balance_sheet.empty else [],
        'cashflow_quarterly': list(t.quarterly_cashflow.index) if t.quarterly_cashflow is not None and not t.quarterly_cashflow.empty else []
    }

with open('campi_bilanci.json', 'w') as f:
    json.dump(schema_completo, f, indent=2)

print("Estrazione completata. File 'campi_bilanci.json' creato con successo.")

# Doctor Quant

A local, read-only forensic tool for systematic trading incidents. It does not trade, route orders, or change broker accounts.

At any point in a position history it shows what the algorithm knew, what it decided, what it intended to own, what actually filled, and which evidence links that chain to P&L.

## Install and start

Requires Python 3.10 or newer and a web browser. `requirements.txt` is empty because the app uses only the Python standard library.

Confirm Python:

```text
Windows:  py -3 --version
macOS:    python3 --version
```

### Windows

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python .\run-doctorquant.py
```

If PowerShell blocks activation, run `.\.venv\Scripts\python.exe .\run-doctorquant.py` instead. You can also double-click `Start-DoctorQuant-Server.cmd`.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Leave the terminal open; press `Ctrl+C` to stop.

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run-doctorquant.py
```

Or run `./start-doctorquant.sh` / double-click `Start-DoctorQuant.command` after `chmod +x start-doctorquant.sh Start-DoctorQuant.command`.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Press `Control+C` to stop.

### Another port

```powershell
$env:PORT = "8001"
python .\run-doctorquant.py
```

```bash
PORT=8001 python run-doctorquant.py
```

Then open `http://127.0.0.1:8001`. Recorder examples must use the same `--server` URL.

## Run the demo

1. Start Doctor Quant and open the dashboard.
2. Click **Run complete CSV demo**.
3. Choose AAPL, MSFT, NVDA, JPM, or XOM.
4. Click any point on the position line.
5. Read the **Algorithm Action Receipt**. Expand **What the algorithm knew** and **Verification Details** as needed.

Each stock uses a different strategy (RSI, momentum, volatility, bank fundamentals, oil). The demo CSV is [`sample_data/full_product_demo.csv`](sample_data/full_product_demo.csv).

## Analyse your own data

- **Upload one incident CSV** — needs `timestamp` and, for statistical analysis, `pnl` (at least 50 rows). Useful extras: `symbol`, `action`, `decision_reason`, `position_quantity`.
- **Upload fundamentals + P&L** — two CSVs joined on `timestamp`/`symbol` without using future data.
- **Open latest recorded strategy** — keep the app running and, in a second terminal, post events from an instrumented strategy:

```powershell
py -3 .\examples\instrumented_strategy.py --server http://127.0.0.1:8000
```

```bash
python3 examples/instrumented_strategy.py --server http://127.0.0.1:8000
```

The recorder observes; it never places an order. See [`examples/instrumented_strategy.py`](examples/instrumented_strategy.py) and [`doctorquant_core/recorder.py`](doctorquant_core/recorder.py).

Receipt statuses: **supported**, **missing**, **contradicted**, **time-invalid**, or **inferred**. Doctor Quant does not invent missing actions or reasons.

## Tests

```powershell
py -3 -m unittest discover -s tests -q
```

```bash
python3 -m unittest discover -s tests -q
```

Optional: `node --check app.js` and `npx playwright test`.

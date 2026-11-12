# AGENTS.md — Santander Statement Expense Report Pipeline

This repository contains the Python OCR and reporting pipeline for extracting monthly Santander Unique Rewards credit card statements (scanned image PDFs) and generating self-contained interactive HTML expense dashboards.

---

## 1. Environment & Dependencies

All scripts **must** be executed inside the local Python virtual environment (`venv`).

### Initial Setup (if `venv` does not exist yet)
```bash
python -m venv venv
```

### Activate the Virtual Environment
- **Windows (PowerShell)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Windows (Command Prompt / Git Bash)**:
  ```bash
  venv\Scripts\activate
  # or in Git Bash:
  source venv/Scripts/activate
  ```
- **Unix / macOS**:
  ```bash
  source venv/bin/activate
  ```

### Install Dependencies
```bash
pip install -r requirements.txt
```

Key packages listed in [`requirements.txt`](requirements.txt):
- `pypdfium2` — Renders PDF pages to PIL images at high DPI (`scale=3.5`).
- `rapidocr-onnxruntime` & `onnxruntime` — Local ONNX OCR engine used to extract bounding boxes and text from statement pages.
- `pillow` — Image manipulation.

---

## 2. Pipeline Architecture

All scripts are parameterized via CLI arguments and share merchant/OCR rules from [`merchants.json`](merchants.json), so **no Python code needs to be modified from month to month**.

1. **[`merchants.json`](merchants.json)**
   - `replacements`: Regex/text normalizations for OCR spacing and character artifacts.
   - `credit_keywords_without_plus`: Identifiers (`pagoportransferencia`, `santa`, `totalplayappregcr`) that should be treated as credits (`-`) when the `+` sign column is absent.
   - `rules`: Ordered merchant classification rules (`group`, `group_key`, `match`, optional `exclude`, optional `match_first_word`).

2. **[`extract_statement.py`](extract_statement.py)** (`<mes>_<año>.pdf` → `<mes>_<año>.md` + `<mes>_<año>_movimientos.json`)
   - Auto-detects the billing period (`Periodo: Del DD-Mmm-YYYY al DD-Mmm-YYYY`) from page 2 (index `1`) if `--period` is not provided.
   - Renders statement movement pages (`--pages 3 4 5`, corresponding to 1-based pages 4–6) at `--scale 3.5`.
   - Runs `RapidOCR`, clusters text boxes into horizontal rows (`cluster_rows` with `y_tol=12.0`), and writes pipe-delimited OCR lines to `<mes>_<año>.md` and raw parsed rows to `<mes>_<año>_movimientos.json`.

3. **[`analyze_expenses.py`](analyze_expenses.py)** (`<mes>_<año>.md` → `<mes>_<año>_gastos.json`)
   - Parses the pipe-delimited markdown lines from `DESGLOSE DE MOVIMIENTOS`.
   - Auto-detects `Periodo`, `Total de cargos`, and `Total de abonos` directly from `<mes>_<año>.md` (or accepts `--period`, `--expected-charges`, and `--expected-credits` via CLI).
   - Separates the **MSI schedule** (`COMPRAS Y CARGOS DIFERIDOS A MESES SIN INTERESES`) from **regular movements** (`CARGOS, ABONOS Y COMPRAS REGULARES (NO A MESES)`).
   - Applies [`merchants.json`](merchants.json) rules and verifies that `delta charges` and `delta credits` equal `0.0`.

4. **[`build_ui.py`](build_ui.py)** (`<mes>_<año>_gastos.json` → `gastos_<mes>_<año>.html`)
   - Enriches `AMAZON A MESES` installment charges with their original purchase date, original amount, and remaining balance from `msi_schedule`.
   - Auto-derives `<title>`, `<h1>`, `localStorage` key, and tag export filename from the month slug (or accepts `--title`, `--heading`, `--store-key`, `--export-name` via CLI).
   - Outputs a self-contained HTML dashboard `gastos_<mes>_<año>.html`.

---

## 3. How to Generate a Report for a New Month

Activate `venv` first, then run the three stages passing the month slug (e.g. `nov_2026` when `nov_2026.pdf` is placed in the workspace):

```bash
# 1. Extract OCR Markdown and raw movements JSON from nov_2026.pdf
python extract_statement.py nov_2026

# 2. Group expenses and reconcile totals into nov_2026_gastos.json
python analyze_expenses.py nov_2026

# 3. Build self-contained dashboard gastos_nov_2026.html
python build_ui.py nov_2026
```

### Optional CLI Arguments
Each script also accepts explicit flags when you need to override defaults:
- `extract_statement.py`:
  ```bash
  python extract_statement.py nov_2026 --pages 3 4 5 --period "10-Nov-2026 al 10-Dic-2026" --config merchants.json
  ```
- `analyze_expenses.py`:
  ```bash
  python analyze_expenses.py nov_2026 --expected-charges 31200.50 --expected-credits 27215.04 --config merchants.json
  ```
- `build_ui.py`:
  ```bash
  python build_ui.py nov_2026 --input nov_2026_gastos.json --out gastos_nov_2026.html --heading "Gastos de noviembre"
  ```

### Adding New Merchants
If `analyze_expenses.py` prints any new merchant under its raw fallback name, add a matching entry in [`merchants.json`](merchants.json) under `replacements` and `rules`, then re-run `analyze_expenses.py` and `build_ui.py`.

---

## 4. Santander Statement Quirks & Domain Rules

- **MSI (Meses Sin Intereses) Double-Counting Prevention**:
  - The `COMPRAS Y CARGOS DIFERIDOS A MESES SIN INTERESES` table at the top of the movements section shows `[Monto original, Saldo pendiente, Pago requerido]`.
  - **Do not** include those rows in the sum of charges: Santander posts each monthly installment again at the bottom of the regular movements table on the cutoff date as `AMAZON A MESES`.
  - Keep the top table as `kind: "msi_schedule"` so `build_ui.py` can match `round(item["amount"], 2)` and display original date/amount and remaining balance next to each `AMAZON A MESES` charge.
- **Missing `-` Sign on Credits/Abonos**:
  - Regular charges have an explicit `| + |` column in the PDF.
  - Payments and refunds (`PAGOPORTRANSFERENCIA`, `SANTA <RFC>`, or $0.01 card verification reversals like `TOTALPLAYAPPREGCR` without `+`) often have **no** sign symbol in the PDF. These keywords are configured in `credit_keywords_without_plus` inside [`merchants.json`](merchants.json).
- **Uber Eats vs. Uber Rides Descriptors**:
  - **Uber Eats** (`food_delivery`) appears across statements under several descriptors (`DLOUBEREATS`, `DLODELUBEREATS`, `DLOSERVUBEREATS`, `PAYPAL UBRPAGOSMEX`, `PAYPAL UBRFLEXMEXI`, `UBRFLEXMEXICO`).
  - **Uber Rides** (`uber_rides`) appears as `DLO UBER` / `DLOUBER` **without** `EATS`.
- **OCR Character Confusions**:
  - `Ag0` instead of `Ago` in August dates (`normalize_date` replaces `Ag0` → `Ago`).
  - `3.808.71` instead of `3,808.71` on thousand separators (`parse_amount` detects two dots with a 2-digit cent suffix and merges the thousands).

---

## 5. Privacy & Repository Rules

- **Never commit** `.pdf` statements, `.jpg`/`.png` scans, extracted `.md`/`.json` statement data, or generated `.html` reports.
- Only commit the Python scripts, [`merchants.json`](merchants.json), [`requirements.txt`](requirements.txt), [`.gitignore`](.gitignore), and documentation ([`agents.md`](agents.md)).

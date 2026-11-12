"""OCR Santander statement movement tables into JSON + markdown."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "merchants.json"

MONEY_RE = re.compile(r"^\$?\s*-?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?$")
DATE_RE = re.compile(r"^\d{2}-[A-Za-z0]{3}-\d{4}$")
PERIOD_RE = re.compile(
    r"Del\s*(\d{2}-[A-Za-z0]{3}-\d{4})\s*al\s*(\d{2}-[A-Za-z0]{3}-\d{4})",
    re.I,
)

MONTH_NAMES_ES = {
    "ene": "enero",
    "feb": "febrero",
    "mar": "marzo",
    "abr": "abril",
    "may": "mayo",
    "jun": "junio",
    "jul": "julio",
    "ago": "agosto",
    "sep": "septiembre",
    "oct": "octubre",
    "nov": "noviembre",
    "dic": "diciembre",
}


def load_replacements(config_path: Path) -> list[tuple[str, str]]:
    if not config_path.exists():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return [(a, b) for a, b in data.get("replacements", [])]


def parse_money(text: str) -> float | None:
    t = text.strip().replace(" ", "").replace("$", "")
    t = t.replace(",", "")
    if re.fullmatch(r"-?\d+(?:\.\d{1,2})?", t):
        return float(t)
    return None


def cluster_rows(items: list, y_tol: float = 12.0) -> list[list]:
    rows: list[tuple[float, list]] = []
    for box, text, conf in items:
        y = sum(p[1] for p in box) / 4
        x = min(p[0] for p in box)
        placed = False
        for row in rows:
            if abs(row[0] - y) <= y_tol:
                row[1].append((x, y, text.strip(), conf, box))
                row[0] = (row[0] * (len(row[1]) - 1) + y) / len(row[1])
                placed = True
                break
        if not placed:
            rows.append([y, [(x, y, text.strip(), conf, box)]])
    rows.sort(key=lambda r: r[0])
    for _, cells in rows:
        cells.sort(key=lambda c: c[0])
    return [cells for _, cells in rows]


def clean_desc(parts: list[str], replacements: list[tuple[str, str]]) -> str:
    text = " ".join(parts)
    text = re.sub(r"\s+", " ", text).strip()
    for a, b in replacements:
        text = re.sub(a, b, text, flags=re.I)
    return text


def classify_row(cells: list, replacements: list[tuple[str, str]]) -> dict | None:
    texts = [c[2] for c in cells]
    dates = [t for t in texts if DATE_RE.match(t)]
    if not dates:
        return None
    amounts = []
    others = []
    signs = []
    for t in texts:
        if DATE_RE.match(t):
            continue
        if t in {"+", "-"}:
            signs.append(t)
            continue
        money = parse_money(t)
        if money is not None and MONEY_RE.match(t.replace(" ", "")) or (
            t.startswith("$") and parse_money(t) is not None
        ):
            amounts.append(parse_money(t))
            continue
        if parse_money(t) is not None and re.search(r"\d+\.\d{2}", t):
            amounts.append(parse_money(t))
            continue
        others.append(t)

    if not amounts:
        return None

    sign = "-" if "-" in signs else "+"
    desc = clean_desc(others, replacements)
    if len(amounts) >= 3 and "MESES" in desc.upper():
        return {
            "kind": "msi",
            "op_date": dates[0],
            "post_date": dates[1] if len(dates) > 1 else dates[0],
            "description": desc,
            "original": amounts[0],
            "pending": amounts[1],
            "amount": amounts[2],
            "sign": "+",
        }

    amount = amounts[-1]
    return {
        "kind": "regular",
        "op_date": dates[0],
        "post_date": dates[1] if len(dates) > 1 else dates[0],
        "description": desc,
        "amount": amount,
        "sign": sign,
    }


def detect_period(ocr: RapidOCR, pdf: pdfium.PdfDocument, scale: float) -> str | None:
    if len(pdf) < 2:
        return None
    pil = pdf[1].render(scale=scale).to_pil()
    result, _ = ocr(pil)
    if not result:
        return None
    for _, text, _ in result:
        m = PERIOD_RE.search(text)
        if m:
            return f"{m.group(1)} al {m.group(2)}"
    return None


def format_month_label(slug: str) -> str:
    m = re.match(r"^([a-z]{3})_(\d{4})$", slug.lower())
    if m and m.group(1) in MONTH_NAMES_ES:
        return f"{MONTH_NAMES_ES[m.group(1)]} {m.group(2)}"
    return slug


def ocr_pages(
    pdf_path: Path,
    out_md: Path,
    out_json: Path,
    page_indexes: list[int],
    scale: float,
    period: str | None,
    title_label: str,
    replacements: list[tuple[str, str]],
):
    ocr = RapidOCR()
    pdf = pdfium.PdfDocument(str(pdf_path))
    resolved_period = period or detect_period(ocr, pdf, scale) or ""

    all_tx = []
    current_section = None
    current_card = None
    md_parts = [f"# Estado de cuenta Santander — {title_label}\n"]
    if resolved_period:
        md_parts.append(f"Periodo: {resolved_period}\n")
    md_parts.append(f"Fuente: OCR de `{pdf_path.name}` (documento de imagen).\n")

    for idx in page_indexes:
        if idx >= len(pdf):
            continue
        page = pdf[idx]
        pil = page.render(scale=scale).to_pil()
        result, _ = ocr(pil)
        if not result:
            continue
        md_parts.append(f"\n## Página {idx + 1}\n")
        rows = cluster_rows(result)
        for cells in rows:
            joined = " | ".join(c[2] for c in cells)
            md_parts.append(joined)
            low = joined.lower().replace(" ", "")
            if "comprasycargosdiferidosameses" in low:
                current_section = "msi"
            elif "cargos,abonosycomprasregulares" in low or "comprasregulares(noameses)" in low:
                current_section = "regular"
            if "tarjetaadicional" in low or "tarjetatitular" in low:
                m = re.search(r"(\d{10,})", joined.replace(" ", ""))
                current_card = m.group(1) if m else current_card
                card_role = "titular" if "titular" in low else "adicional"
            else:
                card_role = None

            tx = classify_row(cells, replacements)
            if tx:
                tx["card"] = current_card
                tx["section"] = current_section or tx["kind"]
                if card_role:
                    tx["card_role"] = card_role
                all_tx.append(tx)

    out_md.write_text("\n".join(md_parts), encoding="utf-8")
    out_json.write_text(json.dumps(all_tx, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"transactions {len(all_tx)}")
    charges = sum(t["amount"] for t in all_tx if t["sign"] == "+")
    credits = sum(t["amount"] for t in all_tx if t["sign"] == "-")
    print(f"charges {charges:.2f} credits {credits:.2f}")
    by_kind = defaultdict(float)
    for t in all_tx:
        if t["sign"] == "+":
            by_kind[t["kind"]] += t["amount"]
    print(dict(by_kind))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OCR Santander PDF statement movement pages into Markdown and JSON."
    )
    parser.add_argument(
        "month",
        nargs="?",
        help="Statement slug (e.g. oct_2026). Sets default --pdf, --out-md, and --out-json.",
    )
    parser.add_argument("--pdf", type=Path, help="Input PDF path (default: <month>.pdf)")
    parser.add_argument("--out-md", type=Path, help="Output Markdown path (default: <month>.md)")
    parser.add_argument(
        "--out-json",
        type=Path,
        help="Output movements JSON path (default: <month>_movimientos.json)",
    )
    parser.add_argument(
        "--period",
        help="Billing period text (e.g. '10-Oct-2026 al 10-Nov-2026'). Auto-detected from page 2 if omitted.",
    )
    parser.add_argument(
        "--title",
        help="Month label for the Markdown heading (e.g. 'octubre 2026'). Derived from month slug if omitted.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        nargs="+",
        default=[3, 4, 5],
        help="0-based PDF page indices to OCR for movements (default: 3 4 5).",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=3.5,
        help="Render scale factor for OCR (default: 3.5).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to merchants.json configuration file.",
    )
    args = parser.parse_args()
    if not args.month and not args.pdf:
        parser.error("Provide either a month slug (e.g. oct_2026) or --pdf.")
    slug = args.month or args.pdf.stem
    args.pdf = args.pdf or (ROOT / f"{slug}.pdf")
    args.out_md = args.out_md or (ROOT / f"{slug}.md")
    args.out_json = args.out_json or (ROOT / f"{slug}_movimientos.json")
    args.title = args.title or format_month_label(slug)
    return args


if __name__ == "__main__":
    cli_args = parse_args()
    ocr_pages(
        pdf_path=cli_args.pdf,
        out_md=cli_args.out_md,
        out_json=cli_args.out_json,
        page_indexes=cli_args.pages,
        scale=cli_args.scale,
        period=cli_args.period,
        title_label=cli_args.title,
        replacements=load_replacements(cli_args.config),
    )

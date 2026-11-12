"""Parse OCR markdown into grouped expenses JSON using merchants.json."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "merchants.json"

DATE_RE = re.compile(
    r"(\d{2}-(?:Ene|Feb|Mar|Abr|May|Jun|Jul|Ag[o0]|Sep|Oct|Nov|Dic)-\d{4})",
    re.I,
)
AMT_RE = re.compile(r"\$\s*([\d.,]+)")
HEADER_PERIOD_RE = re.compile(r"^Periodo:\s*(.+)$", re.I)


def load_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


def normalize_date(d: str) -> str:
    return d.replace("Ag0", "Ago").replace("ag0", "Ago")


def parse_amount(raw: str) -> float:
    t = raw.strip().replace(" ", "")
    # Hostinger-style OCR: 3.808.71 means 3,808.71
    if t.count(".") == 2 and t.count(",") == 0:
        a, b, c = t.split(".")
        if len(c) == 2:
            t = f"{a}{b}.{c}"
    t = t.replace(",", "")
    return float(t)


def merchant_group(desc: str, rules: list[dict]) -> tuple[str, str]:
    u = re.sub(r"\s+", " ", desc.upper()).strip()
    u = u.replace("|", "I")
    u_nospace = u.replace(" ", "")
    first_word = u.split()[0] if u else ""

    for rule in rules:
        first_words = [w.upper() for w in rule.get("match_first_word", [])]
        if first_words and first_word in first_words:
            return (rule["group"], rule["group_key"])

        matches = [m.upper() for m in rule.get("match", [])]
        if not matches:
            continue

        excludes = [e.upper() for e in rule.get("exclude", [])]
        if any(e in u or e.replace(" ", "") in u_nospace for e in excludes):
            continue

        if any(m in u or m.replace(" ", "") in u_nospace for m in matches):
            return (rule["group"], rule["group_key"])

    return (re.sub(r"\s+", " ", desc).strip()[:40], "other")


def apply_replacements(desc: str, replacements: list[list[str]]) -> str:
    text = desc
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return re.sub(r"\s+", " ", text).strip()


def parse_md(md_path: Path, config: dict) -> tuple[list[dict], str | None, float | None, float | None]:
    text = md_path.read_text(encoding="utf-8")
    text = text.replace("Ag0", "Ago")
    rows = []
    in_msi = False
    in_regular = False
    detected_period = None
    detected_total_charges = None
    detected_total_credits = None

    replacements = config.get("replacements", [])
    credit_keywords = [k.lower() for k in config.get("credit_keywords_without_plus", [])]
    rules = config.get("rules", [])

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        m_period = HEADER_PERIOD_RE.match(line)
        if m_period and not detected_period:
            detected_period = m_period.group(1).strip()
            continue

        compact = line.lower().replace(" ", "")
        if "comprasycargosdiferidosameses" in compact:
            in_msi = True
            in_regular = False
            continue
        if "cargos,abonosycomprasregulares" in compact:
            in_msi = False
            in_regular = True
            continue
        if "totaldecargos" in compact:
            amts = AMT_RE.findall(line)
            if amts:
                detected_total_charges = parse_amount(amts[-1])
            continue
        if "totaldeabonos" in compact:
            amts = AMT_RE.findall(line)
            if amts:
                detected_total_credits = parse_amount(amts[-1])
            continue
        if not in_regular and not in_msi:
            continue

        dates = [normalize_date(d) for d in DATE_RE.findall(line)]
        if not dates:
            continue
        amounts = AMT_RE.findall(line)
        if not amounts:
            continue

        has_plus = bool(re.search(r"\|\s*\+\s*\|", line))
        has_minus = bool(re.search(r"\|\s*-\s*\|", line))
        sign = "-" if has_minus else "+"
        if not has_plus:
            for kw in credit_keywords:
                if kw == "santa":
                    if re.search(r"\bsanta\b", compact):
                        sign = "-"
                elif kw in compact:
                    sign = "-"

        desc_parts = []
        for part in line.split("|"):
            p = part.strip()
            if DATE_RE.fullmatch(p.replace("Ag0", "Ago")):
                continue
            if p in {"+", "-"}:
                continue
            if (
                AMT_RE.search(p)
                and parse_amount(AMT_RE.search(p).group(1)) is not None
                and re.match(r"^\$", p.strip())
            ):
                continue
            if DATE_RE.search(p) and len(p) < 16:
                continue
            desc_parts.append(p)

        desc = apply_replacements(" ".join(desc_parts), replacements)

        if in_msi:
            nums = [parse_amount(a) for a in amounts]
            rows.append({
                "kind": "msi_schedule",
                "op_date": dates[0],
                "post_date": dates[0],
                "description": desc,
                "original": nums[0] if nums else None,
                "pending": nums[1] if len(nums) > 1 else None,
                "amount": nums[2] if len(nums) > 2 else nums[-1],
                "sign": "+",
            })
            continue

        amount = parse_amount(amounts[-1])
        if "Descripcion" in desc:
            continue
        group, gkey = merchant_group(desc, rules)
        rows.append({
            "kind": "regular",
            "op_date": dates[0],
            "post_date": dates[1] if len(dates) > 1 else dates[0],
            "description": desc,
            "amount": amount,
            "sign": sign,
            "group": group,
            "group_key": gkey,
        })
    return rows, detected_period, detected_total_charges, detected_total_credits


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze OCR markdown statement into grouped JSON expenses."
    )
    parser.add_argument(
        "month",
        nargs="?",
        help="Statement slug (e.g. oct_2026). Sets default --md and --out.",
    )
    parser.add_argument("--md", type=Path, help="Input OCR Markdown file (default: <month>.md)")
    parser.add_argument(
        "--out",
        type=Path,
        help="Output grouped expenses JSON file (default: <month>_gastos.json)",
    )
    parser.add_argument(
        "--period",
        help="Statement period string (auto-detected from Markdown if omitted).",
    )
    parser.add_argument(
        "--expected-charges",
        type=float,
        help="Official Total de cargos for reconciliation (auto-detected from Markdown if omitted).",
    )
    parser.add_argument(
        "--expected-credits",
        type=float,
        help="Official Total de abonos for reconciliation (auto-detected from Markdown if omitted).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to merchants.json mapping file.",
    )
    args = parser.parse_args()
    if not args.month and not args.md:
        parser.error("Provide either a month slug (e.g. oct_2026) or --md.")
    slug = args.month or args.md.stem
    args.md = args.md or (ROOT / f"{slug}.md")
    args.out = args.out or (ROOT / f"{slug}_gastos.json")
    return args


def main():
    args = parse_args()
    config = load_config(args.config)
    rows, det_period, det_charges, det_credits = parse_md(args.md, config)

    period = args.period or det_period or ""
    expected_charges = (
        args.expected_charges if args.expected_charges is not None else det_charges
    )
    expected_credits = (
        args.expected_credits if args.expected_credits is not None else det_credits
    )

    charges = [r for r in rows if r["kind"] == "regular" and r["sign"] == "+"]
    credits = [r for r in rows if r["kind"] == "regular" and r["sign"] == "-"]
    msi = [r for r in rows if r["kind"] == "msi_schedule"]

    sum_ch = round(sum(r["amount"] for r in charges), 2)
    sum_cr = round(sum(r["amount"] for r in credits), 2)
    print("n charges", len(charges), "credits", len(credits), "msi", len(msi))
    print("sum charges", sum_ch, "expected", expected_charges)
    print("sum credits", sum_cr, "expected", expected_credits)
    if expected_charges is not None:
        print("delta charges", round(sum_ch - expected_charges, 2))
    if expected_credits is not None:
        print("delta credits", round(sum_cr - expected_credits, 2))

    groups = defaultdict(lambda: {"charges": 0.0, "credits": 0.0, "items": []})
    for r in rows:
        if r["kind"] != "regular":
            continue
        g = r["group"]
        if r["sign"] == "+":
            groups[g]["charges"] += r["amount"]
        else:
            groups[g]["credits"] += r["amount"]
        groups[g]["items"].append(r)

    summary = []
    for name, data in groups.items():
        net = round(data["charges"] - data["credits"], 2)
        summary.append({
            "group": name,
            "charges": round(data["charges"], 2),
            "credits": round(data["credits"], 2),
            "net": net,
            "count": len(data["items"]),
            "items": data["items"],
        })
    summary.sort(key=lambda x: x["net"], reverse=True)

    for s in summary:
        print(f"{s['net']:10.2f}  {s['count']:3d}  {s['group']}")

    payload = {
        "period": period,
        "statement_total_charges": expected_charges if expected_charges is not None else sum_ch,
        "statement_total_credits": expected_credits if expected_credits is not None else sum_cr,
        "parsed_charges": sum_ch,
        "parsed_credits": sum_cr,
        "groups": summary,
        "msi_schedule": msi,
    }
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()

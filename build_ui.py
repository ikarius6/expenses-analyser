"""Build self-contained HTML expense report from a *_gastos.json file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

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

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #F7F6F3;
      --ink: #2F3437;
      --muted: #787774;
      --line: #EAEAEA;
      --card: #FFFFFF;
      --pale-red: #FDEBEC;
      --red: #9F2F2D;
      --pale-blue: #E1F3FE;
      --blue: #1F6C9F;
      --pale-green: #EDF3EC;
      --green: #346538;
      --pale-yellow: #FBF3DB;
      --yellow: #956400;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; background: var(--bg); color: var(--ink); }
    body {
      font-family: "Helvetica Neue", "SF Pro Display", Geist, sans-serif;
      line-height: 1.6;
    }
    h1, h2, .serif { font-family: "Instrument Serif", "Newsreader", Georgia, serif; letter-spacing: -0.03em; }
    code, .mono, input, textarea, select, button, .amt {
      font-family: "IBM Plex Mono", "SF Mono", ui-monospace, monospace;
    }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 48px 24px 96px; }
    header { display: grid; grid-template-columns: 1.4fr 1fr; gap: 32px; align-items: end; margin-bottom: 40px; }
    h1 { font-size: 48px; line-height: 1.05; font-weight: 400; margin: 0 0 8px; }
    .lede { color: var(--muted); margin: 0; max-width: 42ch; }
    .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .stat {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px 18px;
    }
    .stat b { display: block; font-size: 20px; font-weight: 500; letter-spacing: -0.03em; }
    .stat span { color: var(--muted); font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }
    .toolbar {
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
      margin-bottom: 28px; padding-bottom: 20px; border-bottom: 1px solid var(--line);
    }
    input[type="search"], input[type="text"], select {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 4px;
      color: var(--ink);
      padding: 8px 10px;
      font-size: 13px;
    }
    input[type="search"] { min-width: 240px; flex: 1; }
    button {
      background: #111111;
      color: #fff;
      border: 0;
      border-radius: 5px;
      padding: 8px 14px;
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: pointer;
    }
    button:hover { background: #333; }
    button.ghost {
      background: transparent;
      color: var(--ink);
      border: 1px solid var(--line);
    }
    .tag {
      display: inline-block;
      font-size: 10px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 9999px;
      background: var(--pale-yellow);
      color: var(--yellow);
    }
    .tag.ok { background: var(--pale-green); color: var(--green); }
    .tag.warn { background: var(--pale-red); color: var(--red); }
    .tag.info { background: var(--pale-blue); color: var(--blue); }
    .group {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      margin-bottom: 12px;
      overflow: hidden;
    }
    .ghead {
      display: grid;
      grid-template-columns: 28px 1fr auto auto;
      gap: 14px;
      align-items: center;
      padding: 16px 18px;
      cursor: pointer;
      width: 100%;
      background: transparent;
      color: inherit;
      text-transform: none;
      letter-spacing: 0;
      font-size: 16px;
      font-family: "Helvetica Neue", sans-serif;
      text-align: left;
      border-radius: 0;
    }
    .ghead:hover { background: #FBFBFA; }
    .ghead .name { font-weight: 500; }
    .ghead .meta { color: var(--muted); font-size: 12px; }
    .amt { font-size: 14px; white-space: nowrap; }
    .amt.credit { color: var(--green); }
    .chev { color: var(--muted); font-size: 18px; }
    .gbody { display: none; border-top: 1px solid var(--line); padding: 8px 12px 16px; }
    .group.open .gbody { display: block; }
    .row {
      display: grid;
      grid-template-columns: 108px 108px 1fr 120px 220px;
      gap: 10px;
      align-items: center;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
    }
    .row:last-child { border-bottom: 0; }
    .row .d { color: var(--muted); font-size: 12px; }
    .row .desc { font-size: 13px; }
    .row input[type="text"] { width: 100%; }
    .hint { font-size: 11px; color: var(--muted); }
    .empty { color: var(--muted); padding: 24px; }
    footer { margin-top: 36px; color: var(--muted); font-size: 12px; }
    @media (max-width: 860px) {
      header { grid-template-columns: 1fr; }
      h1 { font-size: 36px; }
      .row { grid-template-columns: 1fr 1fr; }
      .row .desc { grid-column: 1 / -1; }
      .row input[type="text"] { grid-column: 1 / -1; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>__HEADING__</h1>
        <p class="lede" id="period"></p>
      </div>
      <div class="stats">
        <div class="stat"><b id="st-charges"></b><span>Cargos</span></div>
        <div class="stat"><b id="st-credits"></b><span>Abonos</span></div>
        <div class="stat"><b id="st-food"></b><span>Uber Eats agrupado</span></div>
        <div class="stat"><b id="st-amazon"></b><span>Amazon por etiquetar</span></div>
      </div>
    </header>

    <div class="toolbar">
      <input type="search" id="q" placeholder="Buscar comercio, fecha o etiqueta" />
      <select id="filter">
        <option value="all">Todos los grupos</option>
        <option value="amazon">Solo Amazon (ítems)</option>
        <option value="untagged">Amazon sin etiqueta</option>
        <option value="food">Solo Uber Eats</option>
      </select>
      <button type="button" id="expand">Abrir todos</button>
      <button type="button" class="ghost" id="export">Exportar etiquetas</button>
      <button type="button" class="ghost" id="imp">Importar</button>
      <input type="file" id="file" accept="application/json" hidden />
    </div>

    <div id="list"></div>
    <footer>Las etiquetas se guardan en este navegador. Amazon queda ítem por ítem; el resto se agrupa y también se puede etiquetar cada cargo.</footer>
  </div>
  <script id="data" type="application/json">__DATA__</script>
  <script>
    const DATA = JSON.parse(document.getElementById("data").textContent);
    const STORE = "__STORE_KEY__";
    const mxn = (n) => n.toLocaleString("es-MX", { style: "currency", currency: "MXN" });
    const load = () => JSON.parse(localStorage.getItem(STORE) || "{}");
    const save = (t) => localStorage.setItem(STORE, JSON.stringify(t));
    let tags = load();

    const food = DATA.groups.find(g => g.group_key === "food_delivery" || g.group.includes("Uber Eats"));
    const amazon = DATA.groups.find(g => g.items[0]?.group_key === "amazon");
    document.getElementById("period").textContent = DATA.period + " · Santander Unique Rewards";
    document.getElementById("st-charges").textContent = mxn(DATA.statement_total_charges);
    document.getElementById("st-credits").textContent = mxn(DATA.statement_total_credits);
    document.getElementById("st-food").textContent = mxn(food ? food.net : 0);

    function amazonPending() {
      const items = amazon ? amazon.items : [];
      const missing = items.filter(i => !((tags[i.id] || "").trim()));
      return { total: items.length, missing: missing.length };
    }

    function refreshAmazonStat() {
      const a = amazonPending();
      document.getElementById("st-amazon").textContent = a.missing + " / " + a.total;
    }

    function setTag(id, value) {
      if (value.trim()) tags[id] = value;
      else delete tags[id];
      save(tags);
      refreshAmazonStat();
    }

    function visibleGroups() {
      const q = document.getElementById("q").value.trim().toLowerCase();
      const f = document.getElementById("filter").value;
      return DATA.groups.filter(g => {
        if (f === "amazon" || f === "untagged") return g.items[0]?.group_key === "amazon";
        if (f === "food") return g.items[0]?.group_key === "food_delivery";
        if (!q) return true;
        const blob = (g.group + " " + g.items.map(i => i.description + " " + (tags[i.id] || "")).join(" ")).toLowerCase();
        return blob.includes(q);
      });
    }

    function render() {
      const root = document.getElementById("list");
      const groups = visibleGroups();
      const f = document.getElementById("filter").value;
      const q = document.getElementById("q").value.trim().toLowerCase();
      if (!groups.length) {
        root.innerHTML = '<p class="empty">Nada coincide con el filtro.</p>';
        refreshAmazonStat();
        return;
      }
      root.innerHTML = groups.map(g => {
        const key = g.items[0]?.group_key || "";
        const isAmazon = key === "amazon";
        const items = g.items.filter(i => {
          if (f === "untagged") return !((tags[i.id] || "").trim());
          if (!q) return true;
          return (i.description + " " + i.op_date + " " + (tags[i.id] || "")).toLowerCase().includes(q);
        });
        const tagged = g.items.filter(i => (tags[i.id] || "").trim()).length;
        const badge = isAmazon
          ? `<span class="tag ${tagged === g.items.length ? "ok" : "warn"}">${tagged}/${g.count} etiquetados</span>`
          : `<span class="tag info">${g.count} movimientos</span>`;
        const amtClass = g.net < 0 ? "amt credit" : "amt";
        const rows = items.map(i => {
          const sign = i.sign === "-" ? "credit" : "";
          const ph = isAmazon ? "Qué artículo fue" : "Etiqueta opcional";
          return `<div class="row">
            <div class="d mono">${i.op_date}</div>
            <div class="d mono">${i.post_date}</div>
            <div class="desc">${i.description}${i.sign === "-" ? ' <span class="tag ok">abono</span>' : ""}</div>
            <div class="amt ${sign}">${i.sign === "-" ? "−" : ""}${mxn(i.amount)}</div>
            <input type="text" data-id="${i.id}" value="${(tags[i.id] || "").replaceAll('"','&quot;')}" placeholder="${ph}" />
          </div>`;
        }).join("");
        return `<section class="group ${isAmazon || f !== "all" ? "open" : ""}" data-group="${g.group}">
          <button class="ghead" type="button">
            <span class="chev">${isAmazon || f !== "all" ? "−" : "+"}</span>
            <span><span class="name">${g.group}</span><div class="meta">${badge}</div></span>
            <span class="${amtClass}">${mxn(g.net)}</span>
          </button>
          <div class="gbody">${rows || '<p class="empty">Sin movimientos en este filtro.</p>'}</div>
        </section>`;
      }).join("");

      root.querySelectorAll(".ghead").forEach(btn => {
        btn.addEventListener("click", () => {
          const box = btn.parentElement;
          box.classList.toggle("open");
          btn.querySelector(".chev").textContent = box.classList.contains("open") ? "−" : "+";
        });
      });
      root.querySelectorAll("input[data-id]").forEach(inp => {
        inp.addEventListener("input", () => setTag(inp.dataset.id, inp.value));
      });
      refreshAmazonStat();
    }

    document.getElementById("q").addEventListener("input", render);
    document.getElementById("filter").addEventListener("change", render);
    document.getElementById("expand").addEventListener("click", () => {
      document.querySelectorAll(".group").forEach(g => {
        g.classList.add("open");
        const c = g.querySelector(".chev");
        if (c) c.textContent = "−";
      });
    });
    document.getElementById("export").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(tags, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "__EXPORT_NAME__";
      a.click();
    });
    document.getElementById("imp").addEventListener("click", () => document.getElementById("file").click());
    document.getElementById("file").addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          tags = { ...tags, ...JSON.parse(reader.result) };
          save(tags);
          render();
        } catch { alert("JSON inválido"); }
      };
      reader.readAsText(file);
    });

    render();
  </script>
</body>
</html>
'''


def derive_month_defaults(slug: str) -> tuple[str, str, str, str]:
    m = re.match(r"^([a-z]{3})_(\d{4})$", slug.lower())
    if m and m.group(1) in MONTH_NAMES_ES:
        mon_abbr, year = m.group(1), m.group(2)
        mon_name = MONTH_NAMES_ES[mon_abbr]
        title = f"Gastos · {mon_name} {year}"
        heading = f"Gastos de {mon_name}"
        store_key = f"estadocuenta.{mon_abbr}{year}.tags.v1"
        export_name = f"etiquetas-{mon_abbr}-{year}.json"
        return title, heading, store_key, export_name
    clean = re.sub(r"[^a-z0-9]+", "", slug.lower()) or "mes"
    return (
        f"Gastos · {slug}",
        f"Gastos ({slug})",
        f"estadocuenta.{clean}.tags.v1",
        f"etiquetas-{slug}.json",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build self-contained HTML expense dashboard from *_gastos.json."
    )
    parser.add_argument(
        "month",
        nargs="?",
        help="Statement slug (e.g. oct_2026). Sets default --input, --out, and UI labels.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input grouped expenses JSON file (default: <month>_gastos.json)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output HTML file (default: gastos_<month>.html)",
    )
    parser.add_argument("--title", help="HTML <title> text")
    parser.add_argument("--heading", help="HTML <h1> heading text")
    parser.add_argument("--store-key", help="localStorage key for item tags")
    parser.add_argument("--export-name", help="Default filename when exporting tags JSON")

    args = parser.parse_args()
    if not args.month and not args.input:
        parser.error("Provide either a month slug (e.g. oct_2026) or --input.")

    slug = args.month or re.sub(r"_gastos$", "", args.input.stem)
    default_title, default_heading, default_store, default_export = derive_month_defaults(slug)

    args.input = args.input or (ROOT / f"{slug}_gastos.json")
    args.out = args.out or (ROOT / f"gastos_{slug}.html")
    args.title = args.title or default_title
    args.heading = args.heading or default_heading
    args.store_key = args.store_key or default_store
    args.export_name = args.export_name or default_export
    return args


def main():
    args = parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))

    msi_by_amount = {}
    for m in data.get("msi_schedule") or []:
        msi_by_amount.setdefault(round(m["amount"], 2), []).append(m)

    for g in data["groups"]:
        for i, item in enumerate(g["items"]):
            item["id"] = (
                f"{item.get('group_key','x')}|{item['op_date']}|{item['post_date']}|"
                f"{item['sign']}|{item['amount']:.2f}|{i}"
            )
            item["needs_item_tag"] = item.get("group_key") == "amazon"
            if item.get("group_key") == "amazon" and "MESES" in item.get("description", "").upper():
                hits = msi_by_amount.get(round(item["amount"], 2), [])
                if hits:
                    h = hits[0]
                    item["description"] = (
                        f"{item['description']} · original {h['op_date']} "
                        f"${h.get('original'):,.2f} · saldo ${h.get('pending'):,.2f}"
                    )

    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    out = (
        HTML_TEMPLATE.replace("__TITLE__", args.title)
        .replace("__HEADING__", args.heading)
        .replace("__STORE_KEY__", args.store_key)
        .replace("__EXPORT_NAME__", args.export_name)
        .replace("__DATA__", payload)
    )
    args.out.write_text(out, encoding="utf-8")
    print("wrote", args.out, "bytes", len(out.encode("utf-8")))


if __name__ == "__main__":
    main()

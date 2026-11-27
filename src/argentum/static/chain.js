const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");
const summary = document.querySelector("#summary");
const expirySelect = document.querySelector("#expiry");
const legend = document.querySelector("#legend");
const smileCanvas = document.querySelector("#smile");
const localCanvas = document.querySelector("#local");
const fitsTable = document.querySelector("#fits");
const arbTable = document.querySelector("#arb");
const fileInput = document.querySelector("#chain-file");
const fileStatus = document.querySelector("#file-status");

const COLORS = {
  quotes: "#ece6d8",
  ssvi: "#c4a574",
  black_scholes: "rgba(236,230,216,0.45)",
  merton: "#8fb3a3",
  variance_gamma: "#b9c3cc",
  nig: "#a68fc4",
  heston: "#d67860",
  bates: "#7fb0d6",
};
const LABELS = {
  quotes: "Quotes",
  ssvi: "SSVI",
  black_scholes: "Black–Scholes",
  merton: "Merton",
  variance_gamma: "Variance Gamma",
  nig: "NIG",
  heston: "Heston",
  bates: "Bates",
};

let rows = null;
let latest = null;
const hidden = new Set();

function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  const caption = document.createElement("span");
  const number = document.createElement("strong");
  caption.textContent = label;
  number.textContent = value;
  el.append(caption, number);
  return el;
}

function cells(tr, tag, values) {
  for (const value of values) {
    const el = document.createElement(tag);
    el.textContent = value;
    tr.appendChild(el);
  }
}

function vp(x) {
  return Number.isFinite(x) ? `${(x * 100).toFixed(2)} vp` : "—";
}

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) throw new Error("CSV needs a header and at least one quote");
  const head = lines[0].split(",").map((h) => h.trim().toLowerCase());
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    return Object.fromEntries(head.map((key, i) => [key, (values[i] ?? "").trim()]));
  });
}

function parseChain(name, text) {
  if (name.toLowerCase().endsWith(".json")) {
    const payload = JSON.parse(text);
    const list = Array.isArray(payload) ? payload : payload.rows || payload.quotes;
    if (!Array.isArray(list)) throw new Error("JSON must be a list or contain rows/quotes");
    return list;
  }
  return parseCsv(text);
}

function seriesFor(slice) {
  const out = [];
  if (!hidden.has("quotes")) {
    out.push({ dots: true, xs: slice.quotes.k, ys: slice.quotes.iv.map((v) => v * 100), color: COLORS.quotes });
  }
  if (slice.ssvi_iv && !hidden.has("ssvi")) {
    out.push({ ys: slice.ssvi_iv.map((v) => v * 100), color: COLORS.ssvi, width: 2 });
  }
  for (const [family, vols] of Object.entries(slice.models)) {
    if (hidden.has(family)) continue;
    out.push({ ys: vols.map((v) => (v === null ? null : v * 100)), color: COLORS[family] });
  }
  return out;
}

function paintLegend(slice) {
  const keys = ["quotes", ...(slice.ssvi_iv ? ["ssvi"] : []), ...Object.keys(slice.models)];
  legend.replaceChildren(
    ...keys.map((key) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.setAttribute("aria-pressed", String(!hidden.has(key)));
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = COLORS[key];
      button.append(swatch, document.createTextNode(LABELS[key] || key));
      button.addEventListener("click", () => {
        if (hidden.has(key)) hidden.delete(key);
        else hidden.add(key);
        paintCharts();
      });
      return button;
    })
  );
}

function paintCharts() {
  if (!latest) return;
  const slice = latest.slices[Number(expirySelect.value) || 0];
  paintLegend(slice);
  multiLineChart(smileCanvas, slice.k, seriesFor(slice), { yLabel: "implied vol % vs ln(K/F)", digits: 2, marker: 0 });
  if (slice.local_vol && slice.ssvi_iv) {
    multiLineChart(
      localCanvas,
      slice.k,
      [
        { ys: slice.local_vol.map((v) => v * 100), color: "#d67860", width: 2 },
        { ys: slice.ssvi_iv.map((v) => v * 100), color: COLORS.ssvi },
      ],
      { yLabel: "local (red) vs implied (gold) %", digits: 2, marker: 0 }
    );
  } else {
    localCanvas.getContext("2d").clearRect(0, 0, localCanvas.width, localCanvas.height);
  }
}

function paintTables(data) {
  fitsTable.replaceChildren();
  const head = document.createElement("tr");
  cells(head, "th", ["model", "IV RMSE", "worst", "quotes", "below precision", "parameters"]);
  fitsTable.appendChild(head);
  const rowsOut = [];
  if (data.ssvi) {
    rowsOut.push([
      "SSVI surface",
      vp(data.ssvi.rmse_vol),
      vp(data.ssvi.max_abs_vol_error),
      String(data.ssvi.n_quotes),
      "—",
      `ρ ${data.ssvi.rho.toFixed(3)} · η ${data.ssvi.eta.toFixed(3)} · γ ${data.ssvi.gamma.toFixed(3)}`,
    ]);
  }
  for (const fit of data.fits) {
    const params = Object.entries(fit.params)
      .map(([k, v]) => `${k} ${Number(v).toPrecision(3)}`)
      .join(" · ");
    rowsOut.push([LABELS[fit.family] || fit.family, vp(fit.rmse_vol), vp(fit.max_abs_vol_error), String(fit.n_quotes), String(fit.n_below_precision), params]);
  }
  for (const values of rowsOut) {
    const tr = document.createElement("tr");
    cells(tr, "td", values);
    fitsTable.appendChild(tr);
  }

  arbTable.replaceChildren();
  const ah = document.createElement("tr");
  cells(ah, "th", ["kind", "expiry", "where", "amount"]);
  arbTable.appendChild(ah);
  const violations = data.arbitrage.violations;
  if (!violations.length) {
    const tr = document.createElement("tr");
    cells(tr, "td", ["none", "—", "bounds, verticals, butterflies and calendars all hold", "—"]);
    arbTable.appendChild(tr);
  }
  for (const v of violations.slice(0, 100)) {
    const tr = document.createElement("tr");
    const expiry = Array.isArray(v.texp) ? v.texp.map((t) => t.toFixed(3)).join(" → ") : v.texp.toFixed(3);
    const where = v.strikes ? `K ${v.strikes.map((k) => k.toFixed(2)).join(" / ")}` : `k ${v.k.toFixed(3)}`;
    cells(tr, "td", [v.kind, expiry, where, v.amount.toExponential(2)]);
    arbTable.appendChild(tr);
  }
}

async function run() {
  err.textContent = "";
  const data = new FormData(form);
  const body = {
    spot: data.get("spot"),
    rate: data.get("rate"),
    div: data.get("div"),
    models: data.getAll("models"),
  };
  if (rows) body.rows = rows;
  const res = await fetch("/api/chain", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await res.json();
  if (!res.ok) {
    err.textContent = payload.error || "fit failed";
    return;
  }
  latest = payload;
  const cert = payload.ssvi ? payload.ssvi.certificate : null;
  metrics.replaceChildren(
    metric("Quotes", String(payload.n_quotes)),
    metric("Arbitrage", payload.arbitrage.arbitrage_free ? "none" : `${payload.arbitrage.n_violations} found`),
    metric("SSVI RMSE", payload.ssvi ? vp(payload.ssvi.rmse_vol) : "—"),
    metric("SSVI certificate", cert ? (cert.arbitrage_free && cert.butterfly_condition ? "arbitrage-free" : "check") : "—")
  );
  const best = payload.fits[0];
  summary.textContent =
    `Source: ${payload.source}. ${payload.expiries.length} expiries` +
    (payload.n_dropped ? `, ${payload.n_dropped} quote${payload.n_dropped === 1 ? "" : "s"} dropped` : "") +
    (best ? `. Best model: ${LABELS[best.family] || best.family} at ${vp(best.rmse_vol)} RMSE.` : ".");
  const previous = expirySelect.value;
  expirySelect.replaceChildren(
    ...payload.expiries.map((t, i) => {
      const option = document.createElement("option");
      option.value = String(i);
      option.textContent = `${t.toFixed(3)} y`;
      return option;
    })
  );
  if (previous && Number(previous) < payload.expiries.length) expirySelect.value = previous;
  paintTables(payload);
  paintCharts();
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    rows = null;
    fileStatus.textContent = "Using the synthetic demo chain.";
    return;
  }
  try {
    rows = parseChain(file.name, await file.text());
    fileStatus.textContent = `${file.name} · ${rows.length} quote${rows.length === 1 ? "" : "s"} loaded in this browser.`;
    await run();
  } catch (exc) {
    rows = null;
    err.textContent = String(exc);
    fileStatus.textContent = "The file was not loaded.";
  }
});

expirySelect.addEventListener("change", () => paintCharts());
form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});
window.addEventListener("resize", () => paintCharts());
run().catch((exc) => {
  err.textContent = String(exc);
});

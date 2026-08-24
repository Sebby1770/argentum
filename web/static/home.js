const form = document.querySelector("#feed-form");
const sourceEl = document.querySelector("#feed-source");
const presetEl = document.querySelector("#feed-preset");
const httpFields = document.querySelector("#http-fields");
const statusEl = document.querySelector("#feed-status");
const hintEl = document.querySelector("#feed-hint");
const qSymbol = document.querySelector("#q-symbol");
const qSpot = document.querySelector("#q-spot");
const qMeta = document.querySelector("#q-meta");
const qLab = document.querySelector("#q-lab");
const qBa = document.querySelector("#q-ba");
const qBid = document.querySelector("#q-bid");
const qAsk = document.querySelector("#q-ask");
const qChg = document.querySelector("#q-chg");
const watchBody = document.querySelector("#watch-body");
const sessionTape = document.querySelector("#session-tape");

const HINTS = {
  demo: "Offline SHA-256 book. Same ticker, same last, bid, ask. No network.",
  stooq: "Public daily close from stooq.com. Delayed. Good for a walkthrough.",
  http: "GET your URL with {symbol}. JSON, CSV, or a vendor shape. Localhost is fine.",
};

let PRESETS = {};

function formBody() {
  return form ? Object.fromEntries(new FormData(form).entries()) : { source: "demo", symbol: "AAPL" };
}

function toggleHttp() {
  if (!httpFields || !sourceEl) return;
  httpFields.hidden = sourceEl.value !== "http";
  if (hintEl) hintEl.textContent = HINTS[sourceEl.value] || HINTS.demo;
}

function applyPreset() {
  if (!presetEl || !PRESETS[presetEl.value]) return;
  const spec = PRESETS[presetEl.value];
  const url = form.elements.namedItem("url");
  const field = form.elements.namedItem("field");
  const header = form.elements.namedItem("header_name");
  if (url) url.value = spec.url || "";
  if (field) field.value = spec.field || "";
  if (header) header.value = spec.header_name || "";
  if (hintEl) hintEl.textContent = spec.note || HINTS.http;
}

function fillForm(feed) {
  if (!form || !feed) return;
  for (const [key, value] of Object.entries(feed)) {
    if (key === "has_secret") continue;
    const field = form.elements.namedItem(key);
    if (field && value != null) field.value = value;
  }
  toggleHttp();
}

function showQuote(quote) {
  if (!quote) return;
  qSymbol.textContent = quote.symbol + (quote.name && quote.name !== quote.symbol ? ` · ${quote.name}` : "");
  qSpot.textContent = Number(quote.spot).toFixed(4);
  const bits = [quote.source];
  if (quote.asof) bits.push(String(quote.asof));
  if (quote.vol) bits.push(`vol ${Number(quote.vol).toFixed(3)}`);
  if (quote.latency_ms != null) bits.push(`${Number(quote.latency_ms).toFixed(0)} ms`);
  if (quote.stale) bits.push("stale");
  if (quote.cached) bits.push("cached");
  qMeta.textContent = bits.join(" · ");
  if (quote.bid != null && quote.ask != null) {
    qBa.hidden = false;
    qBid.textContent = Number(quote.bid).toFixed(4);
    qAsk.textContent = Number(quote.ask).toFixed(4);
    const chg = quote.change_pct != null ? quote.change_pct : quote.change;
    qChg.textContent = chg == null ? "—" : `${Number(chg).toFixed(2)}${quote.change_pct != null ? "%" : ""}`;
  } else if (qBa) {
    qBa.hidden = true;
  }
  const params = new URLSearchParams({
    spot: String(quote.spot),
    strike: String(quote.spot),
    symbol: quote.symbol,
  });
  if (quote.vol) params.set("vol", String(quote.vol));
  if (quote.rate != null) params.set("rate", String(quote.rate));
  if (quote.div != null) params.set("div", String(quote.div));
  qLab.href = `/lab?${params.toString()}`;
  const tapeSpot = document.querySelector("#t-spot");
  const tapeLabel = document.querySelector("#t-spot-label");
  if (tapeSpot) tapeSpot.textContent = Number(quote.spot).toFixed(2);
  if (tapeLabel) tapeLabel.textContent = quote.symbol;
  loadTape(quote.spot, quote.vol);
}

function paintWatch(quotes, errors) {
  if (!watchBody) return;
  const rows = [];
  for (const quote of quotes || []) {
    const chg = quote.change_pct == null ? "—" : `${Number(quote.change_pct).toFixed(2)}%`;
    rows.push(
      `<tr><td>${quote.symbol}</td><td>${Number(quote.spot).toFixed(2)}</td><td>${
        quote.bid == null ? "—" : Number(quote.bid).toFixed(2)
      }</td><td>${quote.ask == null ? "—" : Number(quote.ask).toFixed(2)}</td><td>${chg}</td></tr>`
    );
  }
  if (errors) {
    for (const [sym, err] of Object.entries(errors)) {
      rows.push(`<tr><td>${sym}</td><td colspan="4">${err}</td></tr>`);
    }
  }
  watchBody.innerHTML = rows.join("") || `<tr><td colspan="5">No prints yet.</td></tr>`;
}

function paintPrints(prints) {
  if (!sessionTape) return;
  sessionTape.innerHTML = (prints || [])
    .slice(0, 8)
    .map((row) => {
      const extra = row.stale ? " stale" : row.cached ? " cached" : "";
      return `<li><strong>${row.symbol}</strong> ${Number(row.spot).toFixed(4)} <span>${row.source}${extra}</span></li>`;
    })
    .join("");
}

async function loadTape(spot, vol) {
  const s = spot == null ? 100 : spot;
  const v = vol == null || vol === "" ? 0.2 : vol;
  const res = await fetch(`/api/vanilla?spot=${s}&strike=${s}&rate=0.05&vol=${v}&texp=1&type=call`);
  if (!res.ok) return;
  const data = await res.json();
  document.querySelector("#t-npv").textContent = Number(data.npv).toFixed(4);
  document.querySelector("#t-delta").textContent = Number(data.greeks.delta).toFixed(4);
  document.querySelector("#t-vega").textContent = Number(data.greeks.vega).toFixed(3);
}

async function pullQuote(body) {
  statusEl.textContent = "Pulling…";
  statusEl.classList.remove("ok");
  const res = await fetch("/api/quote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    statusEl.textContent = data.error || "quote failed";
    return null;
  }
  statusEl.textContent = "Print in.";
  statusEl.classList.add("ok");
  showQuote(data.quote);
  localStorage.setItem("argentum.quote", JSON.stringify(data.quote));
  return data.quote;
}

async function refreshBoard() {
  const res = await fetch("/api/watch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(formBody()),
  });
  const data = await res.json();
  if (!res.ok) {
    statusEl.textContent = data.error || "watch failed";
    return;
  }
  paintWatch(data.quotes, data.errors);
  const tape = await fetch("/api/tape").then((r) => r.json()).catch(() => null);
  if (tape) paintPrints(tape.prints);
}

async function probe() {
  statusEl.textContent = "Probing…";
  statusEl.classList.remove("ok");
  const res = await fetch("/api/probe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(formBody()),
  });
  const data = await res.json();
  if (!data.ok) {
    statusEl.textContent = data.error || "probe failed";
    return;
  }
  statusEl.textContent = `Probe ${data.latency_ms} ms · ${ (data.fields || []).slice(0, 6).join(", ") }`;
  statusEl.classList.add("ok");
  if (data.quote) showQuote(data.quote);
}

function revealConnect() {
  if (location.hash !== "#connect") return;
  const el = document.querySelector("#connect");
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadPresets() {
  const data = await fetch("/api/presets").then((r) => r.json()).catch(() => null);
  PRESETS = (data && data.presets) || {};
  if (!presetEl) return;
  const current = presetEl.value;
  presetEl.innerHTML =
    `<option value="">Custom URL</option>` +
    Object.entries(PRESETS)
      .map(([id, spec]) => `<option value="${id}">${spec.label || id}</option>`)
      .join("");
  if (current) presetEl.value = current;
}

async function boot() {
  toggleHttp();
  await loadPresets();
  const saved = await fetch("/api/feed").then((r) => r.json()).catch(() => null);
  if (saved && saved.feed) fillForm(saved.feed);
  const cached = localStorage.getItem("argentum.quote");
  if (cached) {
    try {
      showQuote(JSON.parse(cached));
    } catch {
      /* ignore */
    }
  }
  await pullQuote(formBody());
  await refreshBoard();
  revealConnect();
}

if (sourceEl) sourceEl.addEventListener("change", toggleHttp);
if (presetEl) presetEl.addEventListener("change", applyPreset);
window.addEventListener("hashchange", revealConnect);

if (form) {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const body = formBody();
    statusEl.textContent = "Saving…";
    statusEl.classList.remove("ok");
    fetch("/api/feed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          statusEl.textContent = data.error || "save failed";
          return;
        }
        await pullQuote(body);
        return refreshBoard();
      })
      .catch((exc) => {
        statusEl.textContent = String(exc);
      });
  });
}

const probeBtn = document.querySelector("#feed-probe");
if (probeBtn) probeBtn.addEventListener("click", () => probe().catch((exc) => (statusEl.textContent = String(exc))));
const watchBtn = document.querySelector("#feed-watch");
if (watchBtn) watchBtn.addEventListener("click", () => refreshBoard().catch((exc) => (statusEl.textContent = String(exc))));

boot().catch(() => loadTape(100, 0.2));

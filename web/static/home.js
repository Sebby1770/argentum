const form = document.querySelector("#feed-form");
const sourceEl = document.querySelector("#feed-source");
const httpFields = document.querySelector("#http-fields");
const statusEl = document.querySelector("#feed-status");
const hintEl = document.querySelector("#feed-hint");
const qSymbol = document.querySelector("#q-symbol");
const qSpot = document.querySelector("#q-spot");
const qMeta = document.querySelector("#q-meta");
const qLab = document.querySelector("#q-lab");

const HINTS = {
  demo: "Offline SHA-256 book. Same ticker, same last, no network.",
  stooq: "Public daily close from stooq.com. Delayed. Good for a walkthrough.",
  http: "GET your URL with {symbol}. JSON with spot/last/price/close. Localhost is fine.",
};

function toggleHttp() {
  if (!httpFields || !sourceEl) return;
  httpFields.hidden = sourceEl.value !== "http";
  if (hintEl) hintEl.textContent = HINTS[sourceEl.value] || HINTS.demo;
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
  if (quote.asof) bits.push(quote.asof);
  if (quote.vol) bits.push(`vol ${Number(quote.vol).toFixed(3)}`);
  qMeta.textContent = bits.join(" · ");
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

function revealConnect() {
  if (location.hash !== "#connect") return;
  const el = document.querySelector("#connect");
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function boot() {
  toggleHttp();
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
  const body = form ? Object.fromEntries(new FormData(form).entries()) : { source: "demo", symbol: "AAPL" };
  await pullQuote(body);
  revealConnect();
}

if (sourceEl) sourceEl.addEventListener("change", toggleHttp);
window.addEventListener("hashchange", revealConnect);

if (form) {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(form).entries());
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
        return pullQuote(body);
      })
      .catch((exc) => {
        statusEl.textContent = String(exc);
      });
  });
}

boot().catch(() => loadTape(100, 0.2));

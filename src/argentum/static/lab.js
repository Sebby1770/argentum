const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");
const engines = document.querySelector("#engines");
const compare = document.querySelector("#compare");
const chart = document.querySelector("#chart");

function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  el.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
  return el;
}

function applyQuery() {
  const q = new URLSearchParams(window.location.search);
  q.forEach((value, key) => {
    const field = form.elements.namedItem(key);
    if (field) field.value = value;
  });
}

async function mark() {
  err.textContent = "";
  const body = Object.fromEntries(new FormData(form).entries());
  const qs = new URLSearchParams(body);
  history.replaceState(null, "", `/lab?${qs.toString()}`);
  const res = await fetch("/api/vanilla", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "mark failed";
    return;
  }
  metrics.replaceChildren(
    metric("NPV", data.npv.toFixed(6)),
    metric("Delta", data.greeks.delta.toFixed(4)),
    metric("Gamma", data.greeks.gamma.toFixed(5)),
    metric("Vega", data.greeks.vega.toFixed(4)),
    metric("Theta / day", (data.greeks.theta / 365).toFixed(4)),
    metric("Rho", data.greeks.rho.toFixed(4)),
    metric("Volga", data.greeks.volga.toFixed(4)),
    metric("American", data.american.toFixed(6))
  );
  engines.replaceChildren(
    metric("Analytic", data.npv.toFixed(6)),
    metric("Tree", data.tree.toFixed(6)),
    metric("FD", data.fd.toFixed(6)),
    metric("MC ±", `${data.mc.toFixed(4)} ± ${data.mc_error.toFixed(4)}`)
  );
  compare.textContent = `Analytic − tree = ${(data.npv - data.tree).toFixed(6)} · FD gap ${(data.npv - data.fd).toFixed(4)} · intrinsic ${data.intrinsic.toFixed(4)}`;
  lineChart(chart, data.grid.spot, data.grid.value, {
    color: "#c4a574",
    yLabel: "value",
    zero: true,
    second: data.grid.payoff,
    secondColor: "rgba(185,195,204,0.55)",
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  mark().catch((exc) => {
    err.textContent = String(exc);
  });
});

applyQuery();

const pull = document.querySelector("#pull-spot");
const symbolField = document.querySelector("#lab-symbol");
if (pull) {
  pull.addEventListener("click", async () => {
    err.textContent = "";
    const symbol = (symbolField && symbolField.value) || "AAPL";
    const res = await window.argentumFetch("/api/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    const data = await res.json();
    if (!res.ok) {
      err.textContent = data.error || "quote failed";
      return;
    }
    form.elements.namedItem("spot").value = data.quote.spot;
    if (!form.elements.namedItem("strike").value) {
      form.elements.namedItem("strike").value = data.quote.spot;
    } else {
      form.elements.namedItem("strike").value = data.quote.spot;
    }
    if (data.quote.vol) form.elements.namedItem("vol").value = data.quote.vol;
    if (data.quote.rate != null) form.elements.namedItem("rate").value = data.quote.rate;
    if (data.quote.div != null) form.elements.namedItem("div").value = data.quote.div;
    await mark();
  });
}

mark().catch(() => {});

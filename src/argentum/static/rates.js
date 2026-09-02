const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");
const blurb = document.querySelector("#blurb");

function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  el.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
  return el;
}

async function run() {
  err.textContent = "";
  const qs = new URLSearchParams(new FormData(form)).toString();
  const res = await fetch(`/api/swap?${qs}`);
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "swap failed";
    return;
  }
  const money = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
  metrics.replaceChildren(
    metric("NPV", money.format(data.npv)),
    metric("Par", (data.par * 100).toFixed(4) + "%"),
    metric("DV01", money.format(data.dv01)),
    metric("Annuity", money.format(data.annuity))
  );
  blurb.textContent = `Pay-fixed ${data.tenor} on ${data.notional.toLocaleString()} notional · evaluation date ${data.as_of}.`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});

run().catch(() => {});

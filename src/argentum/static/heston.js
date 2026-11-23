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
  const res = await fetch(`/api/heston?${qs}`);
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "heston failed";
    return;
  }
  metrics.replaceChildren(
    metric("Heston", data.npv.toFixed(6)),
    metric("Black–Scholes", data.black_scholes.toFixed(6)),
    metric("Gap", (data.npv - data.black_scholes).toFixed(6)),
    metric("Feller", data.feller.toFixed(4))
  );
  blurb.textContent = data.feller_ok
    ? "Feller condition 2κθ ≥ σ² holds."
    : "Feller is violated — the COS engine still prices, the CIR variance can hit zero.";
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});
run().catch(() => {});

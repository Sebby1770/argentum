async function loadTape() {
  const res = await fetch("/api/vanilla?spot=100&strike=100&rate=0.05&vol=0.2&texp=1&type=call");
  if (!res.ok) return;
  const data = await res.json();
  const fmt = (x, d) => Number(x).toFixed(d);
  document.querySelector("#t-npv").textContent = fmt(data.npv, 4);
  document.querySelector("#t-delta").textContent = fmt(data.greeks.delta, 4);
  document.querySelector("#t-vega").textContent = fmt(data.greeks.vega, 3);
}

loadTape().catch(() => {});

const form = document.querySelector("#form");
const err = document.querySelector("#err");
const chart = document.querySelector("#chart");
const table = document.querySelector("#table");

async function run() {
  err.textContent = "";
  const qs = new URLSearchParams(new FormData(form)).toString();
  const res = await fetch(`/api/smile?${qs}`);
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "smile failed";
    return;
  }
  const xs = data.grid.map((row) => row.strike);
  const ys = data.grid.map((row) => row.vol * 100);
  lineChart(chart, xs, ys, { color: "#b9c3cc", yLabel: "vol %", digits: 3 });
  const head = "<tr><th>K</th><th>moneyness</th><th>vol</th></tr>";
  const rows = data.grid
    .map((row) => `<tr><td>${row.strike.toFixed(4)}</td><td>${row.moneyness.toFixed(3)}</td><td>${(row.vol * 100).toFixed(3)}%</td></tr>`)
    .join("");
  table.innerHTML = head + rows;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});

run().catch(() => {});

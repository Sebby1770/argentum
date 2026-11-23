const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");
const table = document.querySelector("#table");
const fileInput = document.querySelector("#portfolio-file");
const fileStatus = document.querySelector("#file-status");
const exportButton = document.querySelector("#export-report");

let positions = null;
let latestReport = null;

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

function csvMatrix(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell.replace(/\r$/, ""));
      if (row.some((value) => value.trim())) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  row.push(cell.replace(/\r$/, ""));
  if (row.some((value) => value.trim())) rows.push(row);
  if (quoted) throw new Error("CSV contains an unclosed quoted field");
  return rows;
}

function parsePortfolio(name, text) {
  if (name.toLowerCase().endsWith(".json")) {
    const payload = JSON.parse(text);
    const rows = Array.isArray(payload) ? payload : payload.positions;
    if (!Array.isArray(rows)) throw new Error("JSON must be a list or contain a positions list");
    return rows;
  }
  const matrix = csvMatrix(text);
  if (matrix.length < 2) throw new Error("CSV needs a header and at least one position");
  const headers = matrix[0].map((value) => value.trim().toLowerCase());
  return matrix.slice(1).map((values) => Object.fromEntries(headers.map((key, index) => [key, values[index] ?? ""])));
}

function paintScenarios(rows) {
  table.replaceChildren();
  const header = document.createElement("tr");
  for (const label of ["scenario", "NPV", "PnL", "delta", "vega"]) {
    const th = document.createElement("th");
    th.textContent = label;
    header.appendChild(th);
  }
  table.appendChild(header);
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const value of [row.label, row.npv.toFixed(4), row.pnl.toFixed(4), row.delta.toFixed(4), row.vega.toFixed(4)]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    }
    table.appendChild(tr);
  }
}

async function run() {
  err.textContent = "";
  exportButton.disabled = true;
  const body = positions ? { positions } : {};
  const res = await fetch("/api/book", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "portfolio mark failed";
    return;
  }
  latestReport = data.report;
  exportButton.disabled = false;
  metrics.replaceChildren(
    metric("NPV", data.npv.toFixed(4)),
    metric("Delta", data.greeks.delta.toFixed(4)),
    metric("Vega", data.greeks.vega.toFixed(4)),
    metric("Positions", String(data.n))
  );
  paintScenarios(data.scenarios);
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    positions = null;
    fileStatus.textContent = "Using the three-position demonstration book.";
    return;
  }
  try {
    positions = parsePortfolio(file.name, await file.text());
    fileStatus.textContent = `${file.name} · ${positions.length} position${positions.length === 1 ? "" : "s"} loaded in this browser.`;
    await run();
  } catch (exc) {
    positions = null;
    err.textContent = String(exc);
    fileStatus.textContent = "The file was not loaded.";
  }
});

exportButton.addEventListener("click", () => {
  if (!latestReport) return;
  const blob = new Blob([`${JSON.stringify(latestReport, null, 2)}\n`], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "argentum-risk-report.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => { err.textContent = String(exc); });
});

run().catch(() => {});

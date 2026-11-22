function lineChart(canvas, xs, ys, opts) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 48, r: 16, t: 16, b: 28 };
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const extra = opts.second || [];
  const ymin = Math.min(0, ...ys, ...extra);
  const ymax = Math.max(...ys, ...extra);
  const xspan = xmax - xmin || 1;
  const yspan = ymax - ymin || 1;
  const xOf = (x) => pad.l + ((x - xmin) / xspan) * (w - pad.l - pad.r);
  const yOf = (y) => h - pad.b - ((y - ymin) / yspan) * (h - pad.t - pad.b);
  ctx.strokeStyle = "rgba(236,230,216,0.12)";
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, h - pad.b);
  ctx.lineTo(w - pad.r, h - pad.b);
  ctx.stroke();
  ctx.strokeStyle = opts.color || "#c4a574";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  xs.forEach((x, i) => {
    const px = xOf(x);
    const py = yOf(ys[i]);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();
  if (opts.second && opts.second.length === xs.length) {
    ctx.strokeStyle = opts.secondColor || "rgba(185,195,204,0.5)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    xs.forEach((x, i) => {
      const px = xOf(x);
      const py = yOf(opts.second[i]);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }
  if (opts.zero) {
    ctx.strokeStyle = "rgba(236,230,216,0.2)";
    ctx.beginPath();
    ctx.moveTo(pad.l, yOf(0));
    ctx.lineTo(w - pad.r, yOf(0));
    ctx.stroke();
  }
  ctx.fillStyle = "#cfc8b8";
  ctx.font = "11px 'IBM Plex Mono', monospace";
  ctx.fillText(opts.yLabel || "", 8, 14);
  ctx.fillText(String(xmin.toFixed(opts.digits ?? 2)), pad.l, h - 8);
  ctx.fillText(String(xmax.toFixed(opts.digits ?? 2)), w - pad.r - 36, h - 8);
}

function _chartFrame(canvas) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h, pad: { l: 48, r: 16, t: 16, b: 28 } };
}

// Several named series on shared axes. Gaps (null) break the line.
function multiLineChart(canvas, xs, series, opts = {}) {
  const { ctx, w, h, pad } = _chartFrame(canvas);
  const all = series.flatMap((s) => s.ys.filter((y) => y !== null && Number.isFinite(y)));
  if (!all.length || !xs.length) return;
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  let ymin = Math.min(...all);
  let ymax = Math.max(...all);
  const margin = (ymax - ymin) * 0.08 || Math.abs(ymax) * 0.05 || 1;
  ymin -= margin;
  ymax += margin;
  const xOf = (x) => pad.l + ((x - xmin) / (xmax - xmin || 1)) * (w - pad.l - pad.r);
  const yOf = (y) => h - pad.b - ((y - ymin) / (ymax - ymin || 1)) * (h - pad.t - pad.b);
  ctx.strokeStyle = "rgba(236,230,216,0.12)";
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, h - pad.b);
  ctx.lineTo(w - pad.r, h - pad.b);
  ctx.stroke();
  if (opts.marker !== undefined) {
    ctx.strokeStyle = "rgba(236,230,216,0.22)";
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.moveTo(xOf(opts.marker), pad.t);
    ctx.lineTo(xOf(opts.marker), h - pad.b);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  series.forEach((s) => {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = s.width || 1.5;
    ctx.beginPath();
    let open = false;
    xs.forEach((x, i) => {
      const y = s.ys[i];
      if (y === null || !Number.isFinite(y)) {
        open = false;
        return;
      }
      if (open) ctx.lineTo(xOf(x), yOf(y));
      else ctx.moveTo(xOf(x), yOf(y));
      open = true;
    });
    ctx.stroke();
  });
  ctx.fillStyle = "#cfc8b8";
  ctx.font = "11px 'IBM Plex Mono', monospace";
  ctx.fillText(opts.yLabel || "", 8, 14);
  ctx.fillText(ymax.toFixed(opts.yDigits ?? 1), 4, pad.t + 12);
  ctx.fillText(ymin.toFixed(opts.yDigits ?? 1), 4, h - pad.b);
  ctx.fillText(String(xmin.toFixed(opts.digits ?? 0)), pad.l, h - 8);
  ctx.fillText(String(xmax.toFixed(opts.digits ?? 0)), w - pad.r - 36, h - 8);
}

// P&L histogram with the VaR cut drawn as a vertical rule; loss bars tinted.
function histogramChart(canvas, edges, counts, opts = {}) {
  const { ctx, w, h, pad } = _chartFrame(canvas);
  if (!counts.length) return;
  const xmin = edges[0];
  const xmax = edges[edges.length - 1];
  const cmax = Math.max(...counts) || 1;
  const xOf = (x) => pad.l + ((x - xmin) / (xmax - xmin || 1)) * (w - pad.l - pad.r);
  const yOf = (c) => h - pad.b - (c / cmax) * (h - pad.t - pad.b);
  counts.forEach((c, i) => {
    const x0 = xOf(edges[i]);
    const x1 = xOf(edges[i + 1]);
    const tail = opts.cut !== undefined && edges[i + 1] <= opts.cut;
    ctx.fillStyle = tail ? "rgba(214,120,96,0.75)" : "rgba(196,165,116,0.55)";
    ctx.fillRect(x0 + 0.5, yOf(c), Math.max(x1 - x0 - 1, 1), h - pad.b - yOf(c));
  });
  ctx.strokeStyle = "rgba(236,230,216,0.12)";
  ctx.beginPath();
  ctx.moveTo(pad.l, h - pad.b);
  ctx.lineTo(w - pad.r, h - pad.b);
  ctx.stroke();
  if (opts.cut !== undefined) {
    ctx.strokeStyle = "#d67860";
    ctx.beginPath();
    ctx.moveTo(xOf(opts.cut), pad.t);
    ctx.lineTo(xOf(opts.cut), h - pad.b);
    ctx.stroke();
  }
  ctx.fillStyle = "#cfc8b8";
  ctx.font = "11px 'IBM Plex Mono', monospace";
  ctx.fillText(opts.label || "P&L", 8, 14);
  ctx.fillText(xmin.toFixed(2), pad.l, h - 8);
  ctx.fillText(xmax.toFixed(2), w - pad.r - 40, h - 8);
}

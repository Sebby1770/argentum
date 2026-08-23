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
  const ymin = Math.min(0, ...ys);
  const ymax = Math.max(...ys);
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

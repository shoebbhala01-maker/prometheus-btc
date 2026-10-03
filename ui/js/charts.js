/**
 * PROMETHEUS BTC TERMINAL: Lightweight Canvas & SVG Visualizer
 * High-performance rendering of Candlesticks, CVD, and Order Book Depth without external charting bloat.
 */

class TerminalCharts {
  static renderCandlesticks(canvasId, candles) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !candles || candles.length === 0) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.parentElement.clientWidth || 800;
    const height = canvas.height = 320;

    ctx.clearRect(0, 0, width, height);

    const minLow = Math.min(...candles.map(c => c.low));
    const maxHigh = Math.max(...candles.map(c => c.high));
    const priceRange = Math.max(1.0, maxHigh - minLow);

    const padding = 20;
    const plotHeight = height - (padding * 2);
    const n = candles.length;
    const candleWidth = Math.max(2, (width - (padding * 2)) / n - 2);

    // Draw Price Grid lines
    ctx.strokeStyle = '#222938';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding + (plotHeight * (i / 4));
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(width - padding, y);
      ctx.stroke();

      const pVal = maxHigh - (priceRange * (i / 4));
      ctx.fillStyle = '#64748b';
      ctx.font = '10px monospace';
      ctx.fillText(`$${pVal.toFixed(1)}`, width - padding + 5, y + 3);
    }

    // Draw candles
    candles.forEach((c, idx) => {
      const x = padding + (idx * ((width - (padding * 2)) / n)) + 2;
      const yHigh = padding + plotHeight * ((maxHigh - c.high) / priceRange);
      const yLow = padding + plotHeight * ((maxHigh - c.low) / priceRange);
      const yOpen = padding + plotHeight * ((maxHigh - c.open) / priceRange);
      const yClose = padding + plotHeight * ((maxHigh - c.close) / priceRange);

      const isBull = c.close >= c.open;
      const color = isBull ? '#10b981' : '#ef4444';

      // Wick
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x + candleWidth / 2, yHigh);
      ctx.lineTo(x + candleWidth / 2, yLow);
      ctx.stroke();

      // Body
      ctx.fillStyle = color;
      const bodyTop = Math.min(yOpen, yClose);
      const bodyHeight = Math.max(2, Math.abs(yClose - yOpen));
      ctx.fillRect(x, bodyTop, candleWidth, bodyHeight);
    });
  }

  static renderCVD(canvasId, cvdValues) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !cvdValues || cvdValues.length === 0) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.parentElement.clientWidth || 400;
    const height = canvas.height = 140;

    ctx.clearRect(0, 0, width, height);

    const minCvd = Math.min(0, ...cvdValues);
    const maxCvd = Math.max(0, ...cvdValues);
    const range = Math.max(1.0, maxCvd - minCvd);

    const padding = 10;
    const plotH = height - (padding * 2);
    const n = cvdValues.length;

    // Zero line
    const zeroY = padding + plotH * (maxCvd / range);
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(padding, zeroY);
    ctx.lineTo(width - padding, zeroY);
    ctx.stroke();
    ctx.setLineDash([]);

    // CVD Line
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2;
    ctx.beginPath();
    cvdValues.forEach((val, i) => {
      const x = padding + (i * ((width - (padding * 2)) / (n - 1 || 1)));
      const y = padding + plotH * ((maxCvd - val) / range);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  static renderDepthBars(containerId, bids, asks) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const maxBidSize = Math.max(...bids.map(b => b.size), 1);
    const maxAskSize = Math.max(...asks.map(a => a.size), 1);
    const maxSize = Math.max(maxBidSize, maxAskSize);

    let html = `
      <div style="display:flex; justify-content:space-between; gap:10px;">
        <div style="flex:1;">
          <div style="font-size:10px; color:#64748b; font-weight:700; margin-bottom:4px;">BUY DEPTH (BIDS)</div>
          ${bids.slice(0, 8).map(b => `
            <div style="display:flex; justify-content:space-between; position:relative; padding:2px 4px; font-size:11px; font-family:monospace; margin-bottom:2px;">
              <div style="position:absolute; right:0; top:0; bottom:0; width:${(b.size/maxSize)*100}%; background:rgba(16,185,129,0.15); z-index:1;"></div>
              <span style="color:#10b981; z-index:2;">$${b.price.toFixed(1)}</span>
              <span style="color:#cbd5e1; z-index:2;">${b.size.toLocaleString()}</span>
            </div>
          `).join('')}
        </div>
        <div style="flex:1;">
          <div style="font-size:10px; color:#64748b; font-weight:700; margin-bottom:4px;">SELL DEPTH (ASKS)</div>
          ${asks.slice(0, 8).map(a => `
            <div style="display:flex; justify-content:space-between; position:relative; padding:2px 4px; font-size:11px; font-family:monospace; margin-bottom:2px;">
              <div style="position:absolute; left:0; top:0; bottom:0; width:${(a.size/maxSize)*100}%; background:rgba(239,68,68,0.15); z-index:1;"></div>
              <span style="color:#cbd5e1; z-index:2;">${a.size.toLocaleString()}</span>
              <span style="color:#ef4444; z-index:2;">$${a.price.toFixed(1)}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;
    container.innerHTML = html;
  }
}

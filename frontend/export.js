// Add the DOM heading to a rendered image snapshot without re-rendering the chart.
// Exporting must not lose its zoom, brush overlay, or completed progressive paint.
function titleText(title, context, width) {
  if (context.measureText(title).width <= width) return title;
  const letters = Array.from(title);
  let lo = 0, hi = letters.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (context.measureText(letters.slice(0, mid).join('') + '…').width <= width) lo = mid;
    else hi = mid - 1;
  }
  return letters.slice(0, lo).join('') + '…';
}

export async function withTitle(url, renderer, title, theme) {
  if (!title) return url;
  title = String(title);
  const context = document.createElement('canvas').getContext('2d');
  context.font = `600 14px ${theme.font}`;
  if (renderer === 'svg') {
    const prefix = url.slice(0, url.indexOf(','));
    const encoded = url.slice(url.indexOf(',') + 1);
    const source = prefix.includes(';base64')
      ? new TextDecoder().decode(Uint8Array.from(atob(encoded), c => c.charCodeAt(0)))
      : decodeURIComponent(encoded);
    const doc = new DOMParser().parseFromString(source, 'image/svg+xml');
    if (doc.querySelector('parsererror')) throw new Error('The chart SVG could not be exported.');
    const svg = doc.documentElement, ns = 'http://www.w3.org/2000/svg';
    const width = +svg.getAttribute('width'), height = +svg.getAttribute('height');
    const drawing = doc.createElementNS(ns, 'g'); drawing.setAttribute('transform', 'translate(0 32)');
    while (svg.firstChild) drawing.append(svg.firstChild);
    const bg = doc.createElementNS(ns, 'rect');
    bg.setAttribute('width', String(width)); bg.setAttribute('height', String(height + 32)); bg.setAttribute('fill', theme.surface);
    const fullTitle = doc.createElementNS(ns, 'title'); fullTitle.textContent = title;
    const text = doc.createElementNS(ns, 'text'); text.setAttribute('x', '12'); text.setAttribute('y', '21');
    text.setAttribute('font-family', theme.font); text.setAttribute('font-size', '14');
    text.setAttribute('font-weight', '600'); text.setAttribute('fill', theme.fg);
    text.textContent = titleText(title, context, Math.max(0, width - 24));
    svg.setAttribute('height', String(height + 32)); svg.setAttribute('viewBox', `0 0 ${width} ${height + 32}`);
    svg.append(fullTitle, bg, text, drawing);
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(new XMLSerializer().serializeToString(svg));
  }
  const image = new Image(); image.src = url; await image.decode();
  // getDataURL uses pixelRatio=2; scale the heading to match that image resolution.
  const scale = 2, header = 32 * scale;
  context.canvas.width = image.naturalWidth; context.canvas.height = image.naturalHeight + header;
  context.fillStyle = theme.surface; context.fillRect(0, 0, context.canvas.width, context.canvas.height);
  context.drawImage(image, 0, header);
  context.font = `600 ${14 * scale}px ${theme.font}`; context.fillStyle = theme.fg;
  context.fillText(titleText(title, context, Math.max(0, context.canvas.width - 24 * scale)), 12 * scale, 21 * scale);
  return context.canvas.toDataURL('image/png');
}

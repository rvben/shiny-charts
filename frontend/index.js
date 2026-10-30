import * as echarts from 'echarts/core';
import { LineChart, BarChart, ScatterChart, CustomChart, PieChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, DataZoomComponent, BrushComponent, MarkLineComponent, TitleComponent } from 'echarts/components';
import { LabelLayout } from 'echarts/features';
import { SVGRenderer, CanvasRenderer } from 'echarts/renderers';
import { withTitle } from './export.js';
import { applyUpdate } from './updates.js';
import { compile, colorFor, displayValue, displayedRecords, lineRows, lineSpec, groupsOf, pointEvent, palette, unpack } from './compile.js';

echarts.use([LineChart, BarChart, ScatterChart, CustomChart, PieChart, GridComponent, TooltipComponent, DataZoomComponent, BrushComponent, MarkLineComponent, TitleComponent, LabelLayout, SVGRenderer, CanvasRenderer]);

const charts = new Map();
const css = (style, name, fallback) => style.getPropertyValue(name).trim() || fallback;
function themeOf(el) {
  const style = getComputedStyle(el);
  const mode = el.closest('[data-bs-theme]')?.getAttribute('data-bs-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const dark = mode === 'dark';
  const colors = palette.map((color, i) => css(style, `--chart-color-${i + 1}`, color));
  return {
    font: css(style, '--chart-font', style.fontFamily),
    fg: css(style, '--chart-fg', css(style, '--bs-body-color', style.color)),
    muted: css(style, '--chart-muted', css(style, '--bs-secondary-color', dark ? '#afb8c8' : '#576273')),
    grid: css(style, '--chart-grid', css(style, '--bs-border-color', dark ? '#343c4a' : '#e0e5ec')),
    border: css(style, '--chart-border', css(style, '--bs-border-color', dark ? '#343c4a' : '#e0e5ec')),
    surface: css(style, '--chart-surface', css(style, '--bs-body-bg', dark ? '#18212e' : '#ffffff')),
    palette: colors,
  };
}

function send(state, suffix, payload) {
  if (payload) window.Shiny?.setInputValue(`${state.el.id}_${suffix}`, { ...payload, revision: state.spec.view.revision }, { priority: 'event' });
}
function clearInputs(el) {
  for (const suffix of ['click', 'selection', 'legend', 'view']) {
    window.Shiny?.setInputValue(`${el.id}_${suffix}`, null, { priority: 'event' });
  }
}
function toolIcon(button) {
  const paths = {
    'View data': ['M3 4h18v16H3z', 'M3 9h18M9 4v16'],
    'Download CSV': ['M12 3v12m-4-4 4 4 4-4', 'M4 17v4h16v-4'],
    'Save image': ['M3 4h18v16H3z', 'm3 16 5-5 4 4 3-3 6 6', 'M16 8h.01'],
    'Reset view': ['M4 11a8 8 0 1 1 2 7', 'M4 4v7h7'],
    'Select region': ['M4 4h16v16H4z'],
    'Clear selection': ['m6 6 12 12M6 18 18 6'],
  };
  const label = button.textContent;
  if (!paths[label]) return;
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.7'); svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  for (const d of paths[label]) { const path = document.createElementNS(ns, 'path'); path.setAttribute('d', d); svg.append(path); }
  const span = document.createElement('span'); span.className = 'sc-tool-label'; span.textContent = label;
  button.replaceChildren(svg, span); button.setAttribute('aria-label', label); button.title = label;
}
function button(text, action, className = '') {
  const el = document.createElement('button');
  el.type = 'button'; el.textContent = text; el.className = className; el.addEventListener('click', action);
  return el;
}
async function download(state, type) {
  let url, filename;
  if (type === 'csv' || type === 'line-csv') {
    const quote = value => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const data = type === 'line-csv' ? lineSpec(state.spec) : state.spec;
    const text = [data.columns, ...data.rows].map(row => row.map(quote).join(',')).join('\r\n');
    url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    filename = `${state.el.id}${type === 'line-csv' ? '-line' : ''}.csv`;
  } else {
    const theme = themeOf(state.el);
    if (state.spec.renderer === 'svg') {
      // Serialize the actual SVG DOM: the renderer's string exporter does not
      // escape quoted host font families inside style attributes.
      const svg = state.plot.querySelector('svg').cloneNode(true);
      svg.removeAttribute('style');
      const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bg.setAttribute('width', String(state.engine.getWidth())); bg.setAttribute('height', String(state.engine.getHeight()));
      bg.setAttribute('fill', theme.surface); svg.prepend(bg);
      url = 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(new XMLSerializer().serializeToString(svg));
    } else {
      url = state.engine.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: theme.surface });
    }
    url = await withTitle(url, state.spec.renderer, state.spec.labels.title, theme);
    filename = `${state.el.id}.${state.spec.renderer === 'svg' ? 'svg' : 'png'}`;
  }
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  if (type === 'csv' || type === 'line-csv') setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function buildTable(state) {
  const dialog = document.createElement('dialog'); dialog.className = 'sc-data-dialog';
  const heading = document.createElement('h2'); heading.textContent = state.spec.labels.title || 'Chart data';
  heading.id = `${state.el.id}-table-title`; dialog.setAttribute('aria-labelledby', heading.id);
  const table = document.createElement('table'), caption = document.createElement('caption');
  caption.textContent = `Showing ${Math.min(250, state.spec.rows.length)} of ${state.spec.rows.length} displayed records. Download CSV includes every displayed record.`;
  table.append(caption);
  const thead = document.createElement('thead'), tr = document.createElement('tr');
  const visibleColumns = state.spec.columns.map((name, index) => ({ name, index }))
    .filter(column => !state.spec.data_table?.hide.includes(column.name));
  for (const { name: column } of visibleColumns) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = column; tr.append(th); }
  if (state.spec.selection.click) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = 'Select'; tr.append(th); }
  thead.append(tr); table.append(thead);
  const tbody = document.createElement('tbody');
  for (const [index, row] of state.spec.rows.slice(0, 250).entries()) {
    const tr = document.createElement('tr');
    for (const { name, index: i } of visibleColumns) { const td = document.createElement('td'); td.textContent = displayValue(state.spec, name, row[i]); tr.append(td); }
    if (state.spec.selection.click) {
      const td = document.createElement('td');
      td.append(button('Select', () => {
        const event = pointEvent(state.spec, 0, index);
        send(state, 'click', event); send(state, 'selection', event); dialog.close();
      })); tr.append(td);
    }
    tbody.append(tr);
  }
  table.append(tbody);
  const close = button('Close', () => dialog.close());
  dialog.append(heading, close, table);
  if (state.spec.line) {
    const spec = lineSpec(state.spec), table = document.createElement('table');
    const caption = document.createElement('caption');
    caption.textContent = `${spec.label}: showing ${Math.min(250,spec.rows.length)} of ${spec.rows.length} supplied line records.`;
    table.append(caption);
    const thead = document.createElement('thead'), header = document.createElement('tr');
    const visible = spec.columns.map((name,index)=>({name,index})).filter(c=>!spec.data_table?.hide.includes(c.name));
    for (const {name} of visible) { const th=document.createElement('th');th.scope='col';th.textContent=name;header.append(th); }
    thead.append(header);table.append(thead);
    const tbody=document.createElement('tbody');
    for (const row of spec.rows.slice(0,250)) { const tr=document.createElement('tr');
      for (const {name,index} of visible) {const td=document.createElement('td');td.textContent=displayValue(spec,name,row[index]);tr.append(td);}
      tbody.append(tr);
    }
    table.append(tbody);dialog.append(table,button('Download line CSV',()=>download(state,'line-csv')));
  }
  state.el.append(dialog);
  dialog.addEventListener('close', () => { dialog.remove(); state.dataButton.focus(); });
  dialog.showModal(); close.focus();
}

function redraw(state) {
  if (!state.spec || !state.engine || charts.get(state.el) !== state) return;
  const start = performance.now();
  state.legend.classList.toggle('sc-legend-scroll', state.spec.legend?.layout === 'scroll');
  state.el.insertBefore(state.legend, state.spec.legend?.placement === 'bottom' ? state.tools : state.plot);
  state.title.textContent = state.spec.labels.title || '';
  state.title.hidden = !state.spec.labels.title;
  const theme = themeOf(state.el);
  state.themeKey = JSON.stringify(theme);
  state.lastSize = [state.plot.clientWidth, state.plot.clientHeight];
  // Resize only when the output actually changed size. An unconditional resize
  // rebuilds a second render pipeline and interrupts progressive scatter work.
  if (state.engine.getWidth() !== state.lastSize[0] || state.engine.getHeight() !== state.lastSize[1]) {
    state.engine.resize({ width: state.lastSize[0], height: state.lastSize[1] });
  }
  const option = compile(state.spec, theme, state.plot.clientWidth, state.hidden, state.plot.clientHeight);
  // The DOM title precedes the keyboard legend. Image export adds the same title
  // to the already-rendered snapshot, preserving zoom, brushes and complete paint.
  if (option.title) {
    option.title.show = false;
    option.grid.top = Math.max(option.grid.top - 30, state.spec.value_labels?.show || state.spec.value_labels?.totals ? 32 : 22);
  }
  if (state.zoom && option.dataZoom.length) option.dataZoom = option.dataZoom.map(z => ({ ...z, ...state.zoom }));
  const hasLine = lineRows(state.spec).some(({row}) => row[state.spec.line.columns.indexOf(state.spec.line.encoding.y)] != null);
  const hasPoints = hasLine || (state.spec.kind === 'pie' ? state.spec.rows.some(row => row[state.spec.columns.indexOf(state.spec.encoding.y)] > 0) : state.spec.rows.some(row => row[state.spec.columns.indexOf(state.spec.encoding.y)] != null && (state.spec.kind !== 'scatter' || row[state.spec.columns.indexOf(state.spec.encoding.x)] != null)));
  if (hasPoints) state.engine.setOption(option, { notMerge: true, lazyUpdate: false });
  else state.engine.clear();
  state.empty.hidden = hasPoints;
  state.tools.hidden = state.spec.rows.length === 0;
  state.el.dataset.renderMs = String(performance.now() - start);
  state.el.dataset.renderCount = String(+(state.el.dataset.renderCount || 0) + 1);
  state.el.dataset.themeColor = theme.fg;
  state.el.dataset.font = theme.font;
  const focusedGroup = state.legend.contains(document.activeElement) ? document.activeElement.dataset.group : null;
  state.legend.replaceChildren();
  for (const group of groupsOf(state.spec)) {
    const el = button(group, () => {
      if (state.hidden.has(group)) state.hidden.delete(group); else state.hidden.add(group);
      redraw(state); send(state, 'legend', { hidden: [...state.hidden] });
    }, 'sc-legend-item');
    el.setAttribute('aria-pressed', String(!state.hidden.has(group)));
    el.dataset.group = group;
    const swatch = document.createElement('span'); swatch.className = `sc-swatch sc-swatch-${group === state.spec.line?.label ? 'line' : state.spec.kind}`; swatch.style.backgroundColor = colorFor(group, theme.palette, state.spec.palette);
    el.prepend(swatch); state.legend.append(el);
  }
  if (focusedGroup != null) [...state.legend.children].find(el => el.dataset.group === focusedGroup)?.focus();
  state.legend.hidden = !hasPoints || groupsOf(state.spec).length < 2;
  state.summary.textContent = `${state.spec.labels.title || state.spec.labels.y}. ${displayedRecords(state.spec, state.hidden)} displayed records.${state.spec.line ? ` ${lineRows(state.spec).filter(({row}) => !state.hidden.has(state.spec.line.label) && row[state.spec.line.columns.indexOf(state.spec.line.encoding.y)] != null).length} line points.` : ''} Use View data for a table or Download CSV.`;
  state.reset.hidden = !state.spec.view.zoom;
  state.brush.hidden = !state.spec.selection.brush;
  state.clear.hidden = !state.spec.selection.click && !state.spec.selection.brush;
  state.el.dispatchEvent(new CustomEvent('shiny-charts:rendered', { bubbles: true }));
}

function create(el, spec) {
  el.replaceChildren();
  const title = document.createElement('p'); title.className = 'sc-title';
  title.textContent = spec.labels.title || ''; title.hidden = !spec.labels.title;
  const plot = document.createElement('div'); plot.className = 'sc-plot';
  plot.setAttribute('role', 'img'); plot.setAttribute('aria-label', 'Interactive chart. Data table available below.');
  const summary = document.createElement('p'); summary.className = 'sc-summary';
  summary.id = `${el.id}-description`; plot.setAttribute('aria-describedby', summary.id);
  const legend = document.createElement('div'); legend.className = 'sc-legend'; legend.setAttribute('aria-label', 'Chart series');
  const tools = document.createElement('div'); tools.className = 'sc-tools';
  const empty = document.createElement('div'); empty.className = 'sc-empty'; empty.setAttribute('role', 'status'); empty.textContent = el.dataset.emptyMessage; empty.hidden = true;
  const progress = document.createElement('div'); progress.className = 'sc-progress';
  progress.setAttribute('role', 'status'); progress.textContent = 'Updating chart…';
  progress.hidden = el.getAttribute('aria-busy') !== 'true';
  el.append(title, progress, legend, plot, empty, tools, summary);
  const engine = echarts.init(plot, null, { renderer: spec.renderer });
  const state = { el, title, plot, engine, legend, summary, empty, tools, spec, hidden: new Set(), zoom: null };
  state.reset = button('Reset view', () => { state.zoom = null; redraw(state); send(state, 'view', { reset: true }); });
  state.brush = button('Select region', () => {
    state.brushing = !state.brushing;
    state.brush.setAttribute('aria-pressed', String(state.brushing));
    engine.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: state.brushing ? 'rect' : false } });
  });
  state.brush.setAttribute('aria-pressed', 'false');
  state.keydown = event => {
    if (event.key === 'Escape' && state.brushing && !event.target.closest('dialog')) {
      state.brushing = false; state.brush.setAttribute('aria-pressed', 'false');
      engine.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: false } });
      state.brush.focus(); event.preventDefault();
    }
  };
  el.addEventListener('keydown', state.keydown);
  state.clear = button('Clear selection', () => { engine.dispatchAction({ type: 'brush', areas: [] }); send(state, 'selection', { kind: 'clear', keys: [] }); });
  state.dataButton = button('View data', () => buildTable(state));
  tools.append(state.reset, state.brush, state.clear, state.dataButton, button('Download CSV', () => download(state, 'csv')), button('Save image', () => download(state, 'image')));
  for (const control of tools.children) toolIcon(control);
  engine.on('click', p => {
    if (!state.spec.selection.click || p.data?.overlay || p.data?.row === undefined) return;
    const event = pointEvent(state.spec, p.seriesIndex, p.data.row);
    send(state, 'click', event); send(state, 'selection', event);
  });
  engine.on('datazoom', () => {
    const z = engine.getOption().dataZoom?.[0];
    if (z) { state.zoom = { startValue: z.startValue, endValue: z.endValue }; send(state, 'view', state.zoom); }
  });
  engine.on('brushEnd', p => {
    if (!state.spec.selection.brush) return;
    const area = p.areas?.[0];
    if (!area) return;
    const bounds = area.coordRange;
    if (!bounds || !Array.isArray(bounds[0])) return;
    const [xr, yr] = bounds;
    const xi = state.spec.columns.indexOf(state.spec.encoding.x), yi = state.spec.columns.indexOf(state.spec.encoding.y), ki = state.spec.columns.indexOf(state.spec.encoding.key);
    const keys = [];
    let count = 0;
    for (const row of state.spec.rows) {
      const ci = state.spec.columns.indexOf(state.spec.encoding.color);
      const group = ci < 0 ? state.spec.labels.y : String(row[ci] ?? 'Missing');
      if (state.hidden.has(group)) continue;
      if (row[xi] != null && row[yi] != null && row[xi] >= xr[0] && row[xi] <= xr[1] && row[yi] >= yr[0] && row[yi] <= yr[1]) {
        count++; if (ki >= 0 && keys.length < 10000) keys.push(row[ki]);
      }
    }
    send(state, 'selection', { kind: 'range', range: { x: xr, y: yr }, count, keys, truncated: ki >= 0 && count > keys.length });
  });
  let pending = false;
  state.observer = new ResizeObserver(() => {
    const current = [plot.clientWidth, plot.clientHeight];
    if (state.lastSize?.[0] === current[0] && state.lastSize?.[1] === current[1]) return;
    if (!pending) { pending = true; state.resizeFrame = requestAnimationFrame(() => { pending = false; state.resizeFrame = null; if (el.isConnected) redraw(state); }); }
  });
  state.observer.observe(plot);
  charts.set(el, state);
  return state;
}
function dispose(el) {
  const state = charts.get(el);
  if (state) {
    state.observer.disconnect();
    el.removeEventListener('keydown', state.keydown);
    if (state.resizeFrame != null) cancelAnimationFrame(state.resizeFrame);
    state.engine.dispose(); state.engine = null; charts.delete(el);
  }
}
function render(el, value) {
  if (!value) {
    el.querySelector('dialog')?.close(); dispose(el); clearInputs(el); el.replaceChildren();
    const empty = document.createElement('div'); empty.className = 'sc-empty sc-empty-none';
    empty.setAttribute('role', 'status'); empty.textContent = el.dataset.emptyMessage;
    el.append(empty); return;
  }
  const spec = unpack(value.spec_json === undefined ? value.spec : JSON.parse(value.spec_json));
  el.querySelector('dialog')?.close();
  if (spec.version !== 1) throw new Error('Unsupported shiny-charts spec version');
  if (value.height) { el.style.height = value.height; el.classList.remove('html-fill-item'); }
  let state = charts.get(el);
  const reset = !!state && (state.spec.view.revision !== spec.view.revision || state.spec.renderer !== spec.renderer);
  if (state && state.spec.renderer !== spec.renderer) { dispose(el); state = null; }
  if (!state) state = create(el, spec);
  state.spec = spec;
  if (reset) {
    state.zoom = null; state.hidden.clear(); state.brushing = false;
    state.brush.setAttribute('aria-pressed', 'false');
    state.engine.dispatchAction({ type: 'brush', areas: [] });
    state.engine.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: false } });
    send(state, 'selection', { kind: 'clear', keys: [] });
    send(state, 'legend', { hidden: [] });
    send(state, 'view', { reset: true });
    window.Shiny?.setInputValue(`${el.id}_click`, null, { priority: 'event' });
  }
  state.stream = value.stream;
  redraw(state);
}

function update(message) {
  const el = document.getElementById(message.id), state = charts.get(el);
  if (!state) {
    window.Shiny?.setInputValue(`${message.id}_update`, { status: 'ignored', reason: 'unbound', token: message.token, sequence: message.sequence }, { priority: 'event' });
    return;
  }
  let next;
  try { next = applyUpdate(state.spec, state.stream, message); }
  catch (error) {
    send(state, 'update', { status: 'ignored', reason: error.message, token: message.token, sequence: message.sequence });
    return;
  }
  state.el.querySelector('dialog')?.close();
  state.spec = next.spec; state.stream = next.stream;
  redraw(state);
  send(state, 'update', { status: 'applied', token: message.token, sequence: message.sequence, rows: state.spec.rows.length });
}

let refreshQueued = false;
const mutation = new MutationObserver(records => {
  for (const [el] of charts) if (!el.isConnected) dispose(el);
  if (records.some(r => r.type === 'attributes' && [...charts.keys()].some(el => r.target.contains(el))) && !refreshQueued) {
    refreshQueued = true;
    requestAnimationFrame(() => {
      refreshQueued = false;
      for (const state of charts.values()) {
        if (state.themeKey !== JSON.stringify(themeOf(state.el))) redraw(state);
      }
    });
  }
});
// Only ancestor changes schedule redraws; engine-generated styles inside a chart don't.
mutation.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-bs-theme', 'style', 'class'] });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { for (const state of charts.values()) redraw(state); });
document.fonts?.ready.then(() => { for (const state of charts.values()) redraw(state); });
function register() {
  if (!window.Shiny?.OutputBinding) return false;
  const binding = new window.Shiny.OutputBinding();
  binding.find = scope => window.jQuery(scope).find('.shiny-charts-output');
  binding.renderValue = render;
  binding.showProgress = (el, show) => {
    el.classList.toggle('recalculating', show);
    el.setAttribute('aria-busy', String(show));
    let progress = el.querySelector('.sc-progress');
    if (!progress && show && !el.querySelector('.sc-loading')) {
      progress = document.createElement('div'); progress.className = 'sc-progress';
      progress.setAttribute('role', 'status'); progress.textContent = 'Updating chart…'; el.prepend(progress);
    }
    if (progress) progress.hidden = !show;
  };
  binding.renderError = function (el, error) {
    this.clearError(el); el.querySelector('dialog')?.close(); dispose(el); clearInputs(el); el.replaceChildren(); el.classList.add('shiny-output-error');
    const message = document.createElement('div'); message.className = 'sc-error'; message.setAttribute('role', 'alert');
    message.textContent = error.message || 'Chart could not be rendered. Check the data or try again.'; el.append(message);
  };
  window.Shiny.outputBindings.register(binding, 'shiny-charts.output');
  window.Shiny.addCustomMessageHandler('shiny-charts:update', update);
  return true;
}
window.shinyCharts = { get: id => charts.get(document.getElementById(id)), themeOf, refresh: () => { for (const state of charts.values()) redraw(state); } };
if (!register()) document.addEventListener('DOMContentLoaded', register);

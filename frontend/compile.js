import { parse as parseColor } from 'zrender/lib/tool/color.js';
import { getWidth } from 'zrender/lib/contain/text.js';

// The public wire format describes chart semantics; this adapter owns ECharts options.
export const palette = ['#087eac', '#a45ac4', '#bd6500', '#118570', '#ce5069', '#5c74ca', '#7f7324', '#a14d31', '#47728a', '#9b4f87', '#476c3e', '#645a9e'];

export function unpack(spec) {
  if (!spec.dictionaries) return spec;
  const dictionaries = spec.columns.map(name => spec.dictionaries[name]);
  return { ...spec, rows: spec.rows.map(row => row.map((value, i) => dictionaries[i] ? dictionaries[i][value] : value)) };
}

export function colorFor(name, colors = palette, slots = {}) {
  if (Object.prototype.hasOwnProperty.call(slots, name)) return colors[slots[name] - 1];
  let hash = 2166136261;
  for (const c of String(name)) hash = Math.imul(hash ^ c.charCodeAt(0), 16777619);
  return colors[(hash >>> 0) % Math.min(6, colors.length)];
}

export function formatter(format = 'number') {
  const [kind, arg, precision] = format.split(':');
  const options = kind === 'currency'
    ? { style: 'currency', currency: arg, minimumFractionDigits: +(precision ?? 2), maximumFractionDigits: +(precision ?? 2) }
    : { style: kind === 'percent' ? 'percent' : 'decimal', minimumFractionDigits: arg == null ? 0 : +arg, maximumFractionDigits: +(arg ?? 2) };
  const number = new Intl.NumberFormat('en-US', options);
  return value => value == null ? 'Missing' : number.format(value);
}

// Tables and tooltips display the same encoded units; exports retain raw values.
export function displayValue(spec, column, value) {
  if (value == null) return 'Missing';
  if (column === spec.encoding.y) return formatter(spec.formats.y)(value);
  if (column === spec.encoding.x) {
    if (spec.x_type === 'value') return formatter(spec.formats.x)(value);
    if (spec.x_type === 'time') {
      const date = new Date(value);
      if (!Number.isNaN(date.getTime())) return new Intl.DateTimeFormat('en-US', {
        year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
        second: '2-digit', hourCycle: 'h23', timeZone: 'UTC',
      }).format(date) + ' UTC';
    }
  }
  return String(value);
}

const escapeHtml = value => String(value).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function tooltipFormatter(spec) {
  const formats = spec.hover?.formats || {};
  const value = (row, field, format) => {
    const raw = row[spec.columns.indexOf(field)];
    const fmt = format || (Object.prototype.hasOwnProperty.call(formats, field) ? formats[field] : null);
    return fmt ? formatter(fmt)(raw) : displayValue(spec, field, raw);
  };
  return params => {
    const list = (Array.isArray(params) ? params : [params]).filter(p => p.data?.row !== undefined);
    return list.map(p => {
      const row = spec.rows[p.data.row];
      if (spec.hover?.tokens) {
        return spec.hover.tokens.map(token => escapeHtml(token.text ?? value(row, token.field, token.format)))
          .join('').replaceAll('\n', '<br>');
      }
      let x = value(row, spec.encoding.x);
      if (spec.kind === 'histogram') x = spec.intervals[p.data.row].map(formatter(spec.formats.x)).join(' – ');
      const extras = spec.tooltip.map(field => `<br>${escapeHtml(field)}: ${escapeHtml(value(row, field))}`).join('');
      const name = spec.kind === 'pie' ? p.data.group : p.seriesName;
      return `${escapeHtml(x)}<br><strong>${escapeHtml(name)}</strong>: ${escapeHtml(value(row, spec.encoding.y))}${extras}`;
    }).join('<br><br>');
  };
}

// The overlay is a separate small dataset; never reinterpret its rows as bar keys.
export function lineSpec(spec) {
  return spec.line ? { ...spec.line, kind: 'line', x_type: 'category', formats: spec.formats,
    labels: { x: spec.labels.x, y: spec.line.label }, data_table: spec.data_table } : null;
}
export function lineRows(spec) {
  const line = lineSpec(spec);
  if (!line) return [];
  const categories = new Set(spec.rows.map(row => row[spec.columns.indexOf(spec.encoding.x)]));
  const xi = line.columns.indexOf(line.encoding.x);
  return line.rows.map((row, index) => ({ row, index })).filter(item => categories.has(item.row[xi]));
}
export function displayedRecords(spec, hidden = new Set()) {
  if (spec.kind !== 'pie') return spec.rows.length;
  const yi = spec.columns.indexOf(spec.encoding.y), ci = spec.columns.indexOf(spec.encoding.color);
  return spec.rows.filter(row => row[yi] > 0 && !hidden.has(String(row[ci] ?? 'Missing'))).length;
}

export function groupsOf(spec) {
  const index = spec.columns.indexOf(spec.encoding.color);
  const rows = spec.kind === 'pie' ? spec.rows.filter(row => row[spec.columns.indexOf(spec.encoding.y)] != null) : spec.rows;
  const groups = [...new Set(rows.map(row => index < 0 ? spec.labels.y : String(row[index] ?? 'Missing')))];
  if (spec.line && lineRows(spec).some(({row}) => row[spec.line.columns.indexOf(spec.line.encoding.y)] != null)) groups.push(spec.line.label);
  const ordered = (spec.legend?.order || []).filter(name => groups.includes(name));
  return [...ordered, ...groups.filter(name => !ordered.includes(name))];
}

export function pointEvent(spec, seriesIndex, dataIndex) {
  const row = spec.rows[dataIndex];
  if (!row) return null;
  const { x, y, color, key } = spec.encoding;
  if (spec.kind === 'histogram') {
    const [min, max] = spec.intervals[dataIndex];
    return { kind: 'bin', range: { min, max, upper_inclusive: dataIndex === spec.rows.length - 1 }, count: row[spec.columns.indexOf(y)] };
  }
  return {
    kind: key ? 'records' : 'category',
    keys: key ? [row[spec.columns.indexOf(key)]] : [],
    x: row[spec.columns.indexOf(x)], y: row[spec.columns.indexOf(y)],
    group: color ? row[spec.columns.indexOf(color)] : null,
    row: dataIndex,
  };
}


function tickInterval(format = 'number') {
  const [kind, arg, precision] = format.split(':');
  const digits = +(kind === 'currency' ? (precision ?? 2) : (arg ?? 2));
  return 10 ** -digits / (kind === 'percent' ? 100 : 1);
}

function labelContrast(color) {
  // Host palettes usually supply hex or rgb colors; pick the stronger text contrast.
  const rgb = parseColor(color);
  if (!rgb) return '#ffffff';
  const [r, g, b] = rgb.map(v => { const s = v / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4; });
  return .2126 * r + .7152 * g + .0722 * b > .179 ? '#000000' : '#ffffff';
}

export function compile(spec, theme, width, hidden = new Set(), height = 340) {
  const { columns, rows, encoding: e } = spec;
  const xi = columns.indexOf(e.x), yi = columns.indexOf(e.y), ci = columns.indexOf(e.color);
  const compact = width < 480;
  const horizontal = spec.kind === 'bar' && spec.orientation === 'horizontal';
  const groups = groupsOf(spec);
  if (spec.kind === 'pie') {
    const data = groups.flatMap(group => rows.flatMap((row, index) =>
      String(row[xi] ?? 'Missing') === group && !hidden.has(group) && row[yi] != null
        ? [{ name: group, value: row[yi], row: index, group,
          itemStyle: { color: colorFor(group, theme.palette, spec.palette) } }] : []));
    return { animation: false, backgroundColor: 'transparent', dataZoom: [],
      tooltip: { trigger: 'item', confine: true, backgroundColor: theme.surface, borderColor: theme.border,
        textStyle: { color: theme.fg, fontFamily: theme.font, fontSize: 12 }, formatter: tooltipFormatter(spec) },
      series: [{ id: 'pie', name: spec.labels.y, type: 'pie', data, stillShowZeroSum: false,
        radius: ['0%', '78%'], center: ['50%', '50%'], label: { show: false },
        labelLine: { show: false }, emphasis: { scale: false }, animation: false }] };
  }
  const categories = [...new Set(rows.map(row => row[xi]))];
  const dates = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const categoryLabel = value => spec.x_temporal && value != null && Number.isFinite(Date.parse(value))
    ? dates.format(new Date(value)) : String(value ?? 'Missing');
  const labelWidth = Math.min(160, Math.max(36, ...categories.map(value => categoryLabel(value).length * 6.5 + 8)));
  const denseCategories = categories.length * labelWidth > width - 100;
  const rotation = spec.ticks?.x_rotation || 0;
  const labelMode = spec.ticks?.x_labels || 'auto';
  const slotWidth = Math.max(24, (width - 100) / Math.max(1, categories.length) - 8);
  const wrapCategories = !horizontal && spec.x_type === 'category' && !rotation &&
    (labelMode === 'wrap' || labelMode === 'auto' && denseCategories && categories.length <= 8 &&
      categories.some(value => /\s/.test(String(value ?? 'Missing'))));
  const wrapLabel = value => {
    const words = categoryLabel(value).split(/\s+/), lines = [''];
    for (const word of words) {
      const last = lines.length - 1;
      if (lines[last] && (lines[last].length + word.length + 1) * 6.5 > slotWidth) lines.push(word);
      else lines[last] += (lines[last] ? ' ' : '') + word;
    }
    return lines.join('\n');
  };
  const wrapDepth = wrapCategories ? Math.min(96, Math.max(1, ...categories.map(value => wrapLabel(value).split('\n').length)) * 14) : 36;
  const showEveryCategory = labelMode === 'all' || wrapCategories || !!rotation;
  const categoryColoredBars = spec.kind === 'bar' && categories.length === rows.length;
  const axisX = value => spec.x_type === 'category' ? categories.indexOf(value) : value;
  const yFormat = formatter(spec.formats.y), xFormat = formatter(spec.formats.x);
  const commonAxis = {
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: theme.muted, fontFamily: theme.font, fontSize: 11, hideOverlap: true },
    nameTextStyle: { color: theme.muted, fontFamily: theme.font, fontSize: 11 },
    nameLocation: 'middle', nameGap: 30,
  };
  const series = [];
  for (const group of groups.filter(group => group !== spec.line?.label)) {
    const points = rows.flatMap((row, index) => {
      const name = ci < 0 ? spec.labels.y : String(row[ci] ?? 'Missing');
      return name === group ? [{ value: horizontal ? [row[yi], axisX(row[xi])] : [axisX(row[xi]), row[yi]], row: index, group }] : [];
    });
    if (spec.x_type !== 'category' && ['line', 'area'].includes(spec.kind)) {
      const numericX = point => spec.x_type === 'time' ? Date.parse(point.value[0]) : point.value[0];
      points.sort((a, b) => numericX(a) - numericX(b));
    }
    const color = colorFor(group, theme.palette, spec.palette);
    if (spec.band) {
      const quads = [];
      for (let i = 0; i < points.length - 1; i++) {
        const a = points[i], b = points[i + 1];
        const [lo, hi] = spec.band.bounds[a.row], [nextLo, nextHi] = spec.band.bounds[b.row];
        if ([lo, hi, nextLo, nextHi, a.value[1], b.value[1]].some(v => v == null)) continue;
        quads.push([a.value[0], lo, hi, b.value[0], nextLo, nextHi]);
      }
      series.push({
        id: `band:${group}`, name: spec.band.label, type: 'custom', silent: true,
        encode: { x: [0, 3], y: [1, 2, 4, 5] }, clip: true,
        data: hidden.has(group) ? [] : quads,
        renderItem: (params, api) => ({
          type: 'polygon', shape: { points: [
            api.coord([api.value(0), api.value(1)]), api.coord([api.value(0), api.value(2)]),
            api.coord([api.value(3), api.value(5)]), api.coord([api.value(3), api.value(4)]),
          ] }, style: { fill: color, opacity: 0.12 },
        }),
        z: 0,
      });
    }
    const type = ['bar', 'histogram'].includes(spec.kind) ? 'bar' : spec.kind === 'scatter' ? 'scatter' : 'line';
    series.push({
      id: `series:${group}`, name: group, type,
      data: hidden.has(group) ? [] : points,
      encode: { x: 0, y: 1 },
      stack: spec.stacked ? 'total' : undefined,
      connectNulls: false, smooth: false, showSymbol: false, symbolSize: 7,
      // SVG does not benefit from repeated progressive DOM patches. Canvas
      // retains progressive drawing and every normal symbol's click identity.
      progressive: spec.renderer === 'svg' ? 0 : 4000,
      lineStyle: { width: 2, color }, itemStyle: { color, borderRadius: type === 'bar' ? (horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]) : 0 },
      areaStyle: spec.kind === 'area' ? { color, opacity: 0.12 } : undefined,
      barMaxWidth: spec.kind === 'histogram' ? undefined : 52,
      barGap: categoryColoredBars ? '-100%' : undefined,
      barWidth: spec.kind === 'histogram' ? '96%' : undefined,
      emphasis: { focus: 'series', itemStyle: { opacity: 1 } },
      markLine: spec.rules.length && group === groups.find(g => g !== spec.line?.label && !hidden.has(g)) ? {
        symbol: 'none', silent: true,
        lineStyle: { color: theme.muted, type: 'dashed', width: 1 },
        label: { color: theme.muted, fontFamily: theme.font, position: 'insideEndTop', formatter: p => p.name },
        data: spec.rules.filter(rule => !rule.x_between).filter(rule => rule.x === undefined || spec.x_type !== 'category' || categories.includes(rule.x))
          .map(rule => rule.x !== undefined
            ? { [horizontal ? 'yAxis' : 'xAxis']: axisX(rule.x), name: rule.label }
            : { [horizontal ? 'xAxis' : 'yAxis']: rule.y, name: rule.label }),
      } : undefined,
      label: {
        show: !!spec.value_labels?.show,
        position: spec.stacked ? 'inside' : horizontal ? 'right' : 'top',
        color: spec.stacked ? labelContrast(color) : theme.fg,
        fontFamily: theme.font, fontSize: 11,
        formatter: p => spec.stacked && (rows[p.data.row][yi] == null || rows[p.data.row][yi] === 0) ? '' : yFormat(rows[p.data.row][yi]),
        // Labels stay at readable size; a zero-width truncation hides text that
        // cannot fit within the actual laid-out segment, including horizontal bars.
        overflow: 'truncate', ellipsis: '',
      },
      labelLayout: spec.stacked ? params => {
        const fits = params.labelRect.width + 8 <= Math.abs(params.rect.width) &&
          params.labelRect.height + 8 <= Math.abs(params.rect.height);
        // Empty/truncated labels must not suppress visible totals in the global
        // collision pass: even a zero-sized rectangle can intersect another.
        return fits ? { hideOverlap: true } : { hideOverlap: false, width: 0, height: 0 };
      } : { hideOverlap: true },
      animation: false,
    });
  }
  if (spec.value_labels?.totals) {
    const totals = new Map();
    for (const row of rows) {
      const group = ci < 0 ? spec.labels.y : String(row[ci] ?? 'Missing');
      if (hidden.has(group) || row[yi] == null) continue;
      const values = totals.get(row[xi]) || [0, 0];
      values[row[yi] < 0 ? 1 : 0] += row[yi]; totals.set(row[xi], values);
    }
    for (const sign of [0, 1]) {
      const data = [...totals].filter(([, sums]) => sign === 0 ? sums[0] !== 0 || sums[1] === 0 : sums[1] !== 0)
        .map(([x, sums]) => ({ value: horizontal ? [sums[sign], axisX(x)] : [axisX(x), sums[sign]], total: sums[sign] }));
      series.push({
        id: `total:${sign}`, type: 'scatter', silent: true, symbolSize: 0,
        data, encode: { x: 0, y: 1 }, tooltip: { show: false },
        label: { show: true, position: horizontal ? (sign ? 'left' : 'right') : (sign ? 'bottom' : 'top'),
          color: theme.fg, fontFamily: theme.font, fontSize: 11, fontWeight: 600,
          formatter: p => yFormat(p.data.total) }, labelLayout: { hideOverlap: true }, animation: false,
      });
    }
  }
  const overlay = lineSpec(spec);
  const overlayRows = lineRows(spec);
  if (overlay) {
    const oxi = overlay.columns.indexOf(overlay.encoding.x), oyi = overlay.columns.indexOf(overlay.encoding.y);
    const lookup = new Map(overlayRows.map(item => [item.row[oxi], item]));
    const color = colorFor(overlay.label, theme.palette, spec.palette);
    series.push({ id: 'line-overlay', name: overlay.label, type: 'line', z: 5, silent: true,
      data: hidden.has(overlay.label) ? [] : categories.map((category, index) => {
        const item = lookup.get(category);
        return { value: [index, item?.row[oyi] ?? null], row: item?.index, overlay: true };
      }), encode: { x: 0, y: 1 }, connectNulls: false, showSymbol: true, symbolSize: 5,
      lineStyle: { color, width: 2 }, itemStyle: { color }, animation: false });
  }
  const extents = rows.reduce((extent, row) => { if (row[yi] != null) { extent[0] = Math.min(extent[0], row[yi]); extent[1] = Math.max(extent[1], row[yi]); } return extent; }, [Infinity, -Infinity]);
  // Axis space must include stack totals, semantic share endpoints and reference
  // bounds, rather than only the smaller individual segments.
  const axisValues = [...extents.filter(Number.isFinite), 0, ...(spec.domain?.y || []).filter(v => v != null),
    ...spec.rules.filter(r => r.y != null).map(r => r.y),
    ...(spec.annotations || []).filter(a => typeof a.y === 'number').map(a => a.y),
    ...(spec.band?.bounds || []).flat().filter(v => v != null)];
  if (spec.stacked) {
    const sums = new Map();
    for (const row of rows) {
      const group = ci < 0 ? spec.labels.y : String(row[ci] ?? 'Missing');
      if (row[yi] == null || hidden.has(group)) continue;
      const key = JSON.stringify([row[xi], row[yi] < 0]);
      sums.set(key, (sums.get(key) || 0) + row[yi]);
    }
    for (const sum of sums.values()) axisValues.push(sum);
  }
  if (overlay && !hidden.has(overlay.label)) for (const {row} of overlayRows) {
    const value = row[overlay.columns.indexOf(overlay.encoding.y)]; if (value != null) axisValues.push(value);
  }
  if (spec.formats.y.startsWith('percent')) axisValues.push(1);
  const yLength = axisValues.reduce((length, value) => Math.max(length, yFormat(value).length), 0);
  const valueLeft = Math.max(64, Math.min(width * 0.45, (spec.labels.y ? 40 : 20) + yLength * 7 + 8));
  const categoryWidth = Math.max(48, Math.min(compact ? 112 : 210, width * 0.34));
  const option = {
    title: spec.labels.title ? { text: spec.labels.title, left: 12, top: 4,
      textStyle: { color: theme.fg, fontFamily: theme.font, fontSize: 14, fontWeight: 600,
        width: Math.max(20, width - 24), overflow: 'truncate' } } : undefined,
    animation: false, useUTC: true, backgroundColor: 'transparent', textStyle: { fontFamily: theme.font },
    grid: { left: horizontal ? categoryWidth + 12 : valueLeft, right: spec.value_labels?.totals && horizontal ? 64 : 22, top: spec.labels.title ? 52 : spec.value_labels?.show || spec.value_labels?.totals ? 32 : 22, bottom: spec.x_type === 'category' ? 68 : 52, outerBoundsMode: 'none', containLabel: false },
    xAxis: {
      ...commonAxis, type: spec.x_type, data: spec.x_type === 'category' ? categories : undefined,
      name: spec.labels.x, boundaryGap: ['bar', 'histogram'].includes(spec.kind),
      nameGap: spec.x_type === 'category' ? 48 : 32,
      splitNumber: compact ? 3 : 6,
      minInterval: spec.x_type === 'value' ? tickInterval(spec.formats.x) : undefined,
      axisLabel: {
        ...commonAxis.axisLabel, hideOverlap: !showEveryCategory && (compact || denseCategories || spec.x_type !== 'category'),
        interval: spec.x_type === 'category' ? (!showEveryCategory && (compact || denseCategories) ? 'auto' : 0) : undefined,
        width: spec.x_type === 'category' ? (wrapCategories ? slotWidth : Math.min(labelWidth, Math.max(36, width - valueLeft - 22))) : undefined,
        overflow: spec.x_type === 'category' ? 'truncate' : undefined,
        rotate: rotation,
        height: spec.x_type === 'category' ? wrapDepth : undefined,
        formatter: spec.x_type === 'time' ? v => dates.format(new Date(v)) : spec.x_type === 'value' ? xFormat : wrapCategories ? wrapLabel : categoryLabel,
      },
      splitLine: { show: false },
    },
    yAxis: {
      ...commonAxis, type: 'value', name: spec.labels.y, nameGap: 18 + Math.min(yLength * 7, valueLeft - 40),
      scale: ['line', 'scatter'].includes(spec.kind), splitNumber: compact ? 3 : 5,
      minInterval: tickInterval(spec.formats.y),
      axisLabel: { ...commonAxis.axisLabel, formatter: yFormat, width: Math.max(12, valueLeft - (spec.labels.y ? 40 : 20)), overflow: 'truncate' },
      splitLine: { lineStyle: { color: theme.grid, width: 1 } },
    },
    tooltip: {
      trigger: spec.kind === 'scatter' || spec.kind === 'histogram' ? 'item' : 'axis',
      confine: true, appendToBody: false, backgroundColor: theme.surface, borderColor: theme.border,
      textStyle: { color: theme.fg, fontFamily: theme.font, fontSize: 12 }, padding: [10, 12],
      axisPointer: { type: spec.kind === 'bar' ? 'shadow' : 'line', lineStyle: { color: theme.muted } },
      formatter: params => (Array.isArray(params) ? params : [params]).map(p =>
        p.data?.overlay ? tooltipFormatter(overlay)(p) : tooltipFormatter(spec)(p)).filter(Boolean).join('<br><br>'),
    },
    dataZoom: spec.view.zoom && spec.x_type !== 'category' ? [{ type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false }] : [],
    brush: spec.selection.brush ? { toolbox: [], brushType: 'rect', xAxisIndex: 0, yAxisIndex: 0, brushMode: 'single', throttleType: 'debounce', throttleDelay: 100 } : undefined,
    series,
  };
  // A normalized share stack has a semantic 0–100% domain at every width.
  // Do not clamp oversubscribed/negative data, reference rules, or interval bounds.
  if (spec.stacked && ['bar', 'area'].includes(spec.kind) && spec.formats.y.startsWith('percent') && !spec.domain?.y) {
    const sums = new Map();
    let valid = rows.length > 0, positive = false;
    for (const row of rows) {
      if (row[yi] == null) continue;
      valid &&= row[yi] >= 0 && row[yi] <= 1;
      positive ||= row[yi] > 0;
      sums.set(row[xi], (sums.get(row[xi]) || 0) + row[yi]);
    }
    valid &&= [...sums.values()].every(v => v <= 1 + 1e-9);
    valid &&= spec.rules.every(rule => rule.y == null || rule.y >= 0 && rule.y <= 1);
    valid &&= !spec.annotations || spec.annotations.every(a => typeof a.y !== 'number' || a.y >= 0 && a.y <= 1);
    valid &&= !overlay || hidden.has(overlay.label) || overlayRows.every(({row}) => { const v = row[overlay.columns.indexOf(overlay.encoding.y)]; return v == null || v >= 0 && v <= 1; });
    valid &&= !spec.band || spec.band.bounds.every(pair => pair.every(v => v == null || v >= 0 && v <= 1));
    if (valid && positive) Object.assign(option.yAxis, { min: 0, max: 1, interval: compact ? .25 : .2 });
  }
  for (const axis of ['x', 'y']) {
    const bounds = spec.domain?.[axis];
    if (bounds) {
      if (bounds[0] != null) option[`${axis}Axis`].min = bounds[0];
      if (bounds[1] != null) option[`${axis}Axis`].max = bounds[1];
    }
  }
  // Explicit percent ranges use evenly spaced ticks too. The interval divides
  // the range exactly, so both endpoints remain available at compact widths.
  const yBounds = spec.domain?.y;
  if (spec.formats.y.startsWith('percent') && yBounds?.every(v => v != null)) {
    const span = yBounds[1] - yBounds[0];
    const divisions = Math.max(1, Math.min(compact ? 4 : 5,
      Math.floor(span / tickInterval(spec.formats.y) + 1e-9)));
    Object.assign(option.yAxis, { interval: span / divisions,
      axisLabel: { ...option.yAxis.axisLabel, showMinLabel: true, showMaxLabel: true } });
  }
  if (wrapCategories) {
    option.grid.bottom = 40 + wrapDepth;
    option.xAxis.nameGap = 20 + wrapDepth;
  }
  if (rotation && !horizontal) {
    const sine = Math.abs(Math.sin(rotation * Math.PI / 180));
    const cosine = Math.abs(Math.cos(rotation * Math.PI / 180));
    const top = spec.labels.title ? 22 : option.grid.top;
    // Bound the label budget by the actual plot element's height. Keep a useful
    // plotting area; short cards truncate long ticks rather than collapse axes.
    const minimumPlot = Math.min(96, height * .5);
    const bottomBudget = Math.max(30, height - top - minimumPlot);
    const titleSpace = spec.labels.x ? 24 : 8;
    const labelBudget = Math.max(12, bottomBudget - titleSpace - 10);
    const rotatedWidth = Math.max(12, Math.min(labelWidth, (labelBudget - cosine * 12) / sine));
    const depth = sine * rotatedWidth + cosine * 12;
    option.xAxis.axisLabel.width = rotatedWidth;
    option.xAxis.axisLabel.height = 14;
    option.xAxis.axisLabel.overflow = 'truncate';
    option.grid.bottom = Math.min(bottomBudget, depth + titleSpace + 10);
    option.xAxis.nameGap = depth + 14;
  }
  if (horizontal) {
    option.xAxis = { ...option.yAxis, name: spec.labels.y, nameGap: 32, splitNumber: compact ? 3 : 5 };
    option.yAxis = {
      ...commonAxis, type: 'category', data: categories, inverse: true, name: '',
      axisLabel: { ...commonAxis.axisLabel, interval: 0, width: categoryWidth, overflow: 'truncate', rotate: 0, formatter: categoryLabel },
      splitLine: { show: false },
    };
    option.yAxis.axisLabel.rotate = rotation;
    option.grid.bottom = 52;
  }
  const between = spec.rules.filter(rule => rule.x_between &&
    categories.includes(rule.x_between[0]) && categories.includes(rule.x_between[1]) &&
    Math.abs(categories.indexOf(rule.x_between[0]) - categories.indexOf(rule.x_between[1])) === 1);
  if (between.length) option.series.push({ id: 'between-rules', type: 'custom', silent: true,
    clip: true, data: between.map(() => [0]), encode: { x: -1, y: -1 }, tooltip: { show: false },
    animation: false, renderItem: (params, api) => {
      const rule = between[params.dataIndex], rect = params.coordSys;
      const points = rule.x_between.map(x => api.coord(horizontal ? [0, axisX(x)] : [axisX(x), 0]));
      const midpoint = (points[0][horizontal ? 1 : 0] + points[1][horizontal ? 1 : 0]) / 2;
      const rightSpace = rect.x + rect.width - midpoint - 10, leftSpace = midpoint - rect.x - 10;
      const labelLeft = !horizontal && getWidth(rule.label, `11px ${theme.font}`) > rightSpace && leftSpace > rightSpace;
      return { type: 'group', children: [
        { type: 'line', shape: horizontal ? { x1: rect.x, x2: rect.x + rect.width, y1: midpoint, y2: midpoint }
          : { x1: midpoint, x2: midpoint, y1: rect.y, y2: rect.y + rect.height },
          style: { stroke: theme.muted, lineWidth: 1, lineDash: [4, 4] } },
        { type: 'text', style: { x: horizontal ? rect.x + 8 : midpoint + (labelLeft ? -6 : 6),
          y: horizontal ? midpoint - 6 : rect.y + 8, text: rule.label, fill: theme.muted,
          fontFamily: theme.font, fontSize: 11, verticalAlign: horizontal ? 'bottom' : 'top',
          align: labelLeft ? 'right' : 'left', width: Math.max(0, horizontal ? rect.width - 16 : labelLeft ? leftSpace : rightSpace), overflow: 'truncate' } },
      ] };
    } });
  if (spec.annotations?.length) {
    const visible = spec.annotations.filter(a => spec.x_type !== 'category' || categories.includes(a.x));
    const annotations = visible.filter(a => typeof a.y === 'number');
    const edges = visible.filter(a => typeof a.y === 'string');
    if (edges.some(a => a.y === 'top') || annotations.some(a => a.position === 'top' || a.position === 'right' || a.position === 'left')) option.grid.top = Math.max(option.grid.top, 36 + (spec.labels.title ? 30 : 0));
    if (edges.some(a => a.y === 'bottom')) {
      option.grid.bottom += 24; option.xAxis.axisLabel.margin = 32; option.xAxis.nameGap += 24;
    }
    option.series.push({ id: 'annotations', type: 'custom', silent: true, clip: false, z: 10,
      data: annotations.map(a => horizontal ? [a.y, axisX(a.x)] : [axisX(a.x), a.y]),
      encode: { x: 0, y: 1 }, tooltip: { show: false }, animation: false,
      renderItem: (params, api) => {
        const a = annotations[params.dataIndex], point = api.coord([api.value(0), api.value(1)]);
        const rect = params.coordSys;
        if (point[0] < rect.x - .5 || point[0] > rect.x + rect.width + .5 || point[1] < rect.y - .5 || point[1] > rect.y + rect.height + .5) return;
        const positions = { top: [0, -8, 'center', 'bottom'], bottom: [0, 8, 'center', 'top'],
          left: [-8, 0, 'right', 'middle'], right: [8, 0, 'left', 'middle'], inside: [0, 0, 'center', 'middle'] };
        let [dx, dy, align, verticalAlign] = positions[a.position];
        const textWidth = Math.min(width - 40, a.text.length * 7);
        if (align === 'left' && point[0] + dx + textWidth > width - 4) { dx = -8; align = 'right'; }
        if (align === 'right' && point[0] + dx - textWidth < 4) { dx = 8; align = 'left'; }
        return { type: 'text', style: { x: point[0] + dx, y: point[1] + dy, text: a.text,
          fill: theme.fg, fontFamily: theme.font, fontSize: 12, align, verticalAlign,
          width: Math.max(24, width - 40), overflow: 'truncate' } };
      } });
    if (edges.length) option.series.push({ id: 'plot-annotations', type: 'custom', silent: true,
      clip: false, z: 10, data: edges.map(a => [axisX(a.x)]), encode: { x: 0, y: -1 },
      tooltip: { show: false }, animation: false, renderItem: (params, api) => {
        const a = edges[params.dataIndex], rect = params.coordSys;
        // Respect directional anchors. On a matching divider the text faces
        // away from its midpoint; otherwise it faces away from its category.
        const placed = [];
        for (const edge of edges) {
          let x = api.coord([axisX(edge.x), 0])[0];
          if (x < rect.x - .5 || x > rect.x + rect.width + .5) { placed.push(null); continue; }
          const directional = edge.position === 'left' || edge.position === 'right';
          const divider = directional && between.find(rule => {
            const indices = rule.x_between.map(axisX).sort((a,b)=>a-b);
            return axisX(edge.x) === indices[edge.position === 'left' ? 0 : 1];
          });
          if (divider) x = divider.x_between.map(v=>api.coord([axisX(v),0])[0]).reduce((a,b)=>a+b)/2;
          const align = edge.position === 'left' ? 'right' : edge.position === 'right' ? 'left' : 'center';
          x += align === 'right' ? -8 : align === 'left' ? 8 : 0;
          const room = align === 'right' ? x-rect.x : align === 'left' ? rect.x+rect.width-x
            : 2*Math.min(x-rect.x,rect.x+rect.width-x);
          const textWidth = Math.min(room, Math.max(...edge.text.split('\n').map(line=>getWidth(line,`12px ${theme.font}`))));
          const left = align === 'right' ? x-textWidth : align === 'left' ? x : x-textWidth/2;
          const right = left+textWidth;
          const overlap = placed.some(p=>p && p.edge===edge.y && left < p.right+4 && right > p.left-4);
          placed.push(room < 12 || overlap ? null : { x, align, room, left, right, edge: edge.y });
        }
        const placement = placed[params.dataIndex];
        if (!placement) return;
        return { type: 'text', style: { x: placement.x, y: a.y === 'top' ? rect.y - 8 : rect.y + rect.height + 8,
          text: a.text, fill: theme.fg, fontFamily: theme.font, fontSize: 12,
          align: placement.align, verticalAlign: a.y === 'top' ? 'bottom' : 'top',
          width: placement.room, overflow: 'truncate' } };
      } });
  }
  return option;
}


import { unpack } from './compile.js';

// Pure validation/assembly: a malformed or stale update never partly mutates data.
export function applyUpdate(spec, stream, message) {
  if (!stream || message.token !== stream.token) throw new Error('generation');
  if (message.base !== stream.sequence || message.sequence !== stream.sequence + 1) throw new Error('sequence');
  if (!['append', 'replace'].includes(message.operation) || spec.kind === 'histogram') throw new Error('operation');
  const data = message.data;
  if (!data || JSON.stringify(data.columns) !== JSON.stringify(spec.columns) || !Array.isArray(data.rows)) throw new Error('columns');
  const decoded = unpack(data);
  const scalar = value => value === null || typeof value === 'string' || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value));
  if (decoded.rows.some(row => !Array.isArray(row) || row.length !== spec.columns.length || row.some(v => !scalar(v)))) throw new Error('rows');
  const xi = spec.columns.indexOf(spec.encoding.x), yi = spec.columns.indexOf(spec.encoding.y);
  const numeric = v => v === null || (typeof v === 'number' && Number.isFinite(v));
  if (decoded.rows.some(row => !numeric(row[yi]) || ((spec.kind === 'scatter' || spec.x_type === 'value') && !numeric(row[xi])))) throw new Error('numeric');
  if (spec.kind === 'pie' && decoded.rows.some(row => row[yi] != null && row[yi] < 0)) throw new Error('negative');
  const formattedFields = new Set([...Object.keys(spec.hover?.formats || {}),
    ...(spec.hover?.tokens || []).filter(token => token.format).map(token => token.field)]);
  for (const field of formattedFields) {
    const index = spec.columns.indexOf(field);
    if (decoded.rows.some(row => !numeric(row[index]))) throw new Error('format');
  }
  const limit = message.max_rows;
  if (limit != null && (!Number.isSafeInteger(limit) || limit < 1)) throw new Error('limit');
  const appended = message.operation === 'append';
  let rows = appended ? [...spec.rows, ...decoded.rows] : decoded.rows;
  const ki = spec.columns.indexOf(spec.encoding.key);
  if (ki >= 0) {
    const keys = new Set();
    for (const row of rows) {
      const key = row[ki];
      if (key == null || typeof key === 'boolean' || keys.has(key)) throw new Error('keys');
      keys.add(key);
    }
  }
  if (spec.line) {
    const ci = spec.columns.indexOf(spec.encoding.color);
    if (ci < 0 ? spec.labels.y === spec.line.label : rows.some(row => String(row[ci] ?? 'Missing') === spec.line.label)) throw new Error('line label');
  }
  let band = spec.band;
  if (band) {
    if (!Array.isArray(data.bounds) || data.bounds.length !== decoded.rows.length || data.bounds.some(b => !Array.isArray(b) || b.length !== 2 || b.some(v => v !== null && (typeof v !== 'number' || !Number.isFinite(v))) || (b[0] != null && b[1] != null && b[0] > b[1]))) throw new Error('bounds');
    let bounds = appended ? [...band.bounds, ...data.bounds] : data.bounds;
    if (appended && limit != null) bounds = bounds.slice(-limit);
    band = { ...band, bounds };
  }
  if (appended && limit != null) rows = rows.slice(-limit);
  return { spec: { ...spec, rows, ...(band ? { band } : {}) }, stream: { ...stream, sequence: message.sequence } };
}

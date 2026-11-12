const problems = new Set(['404', 'rejected', 'external-unverified']);

export function assetInventory(summary, filter = {}) {
  const rows = (Array.isArray(summary) ? summary : []).filter(
    (row) => row && typeof row.ref === 'string' && typeof row.status === 'string' && typeof row.kind === 'string',
  );
  const status = filter.status || '';
  const kind = filter.kind || '';
  const query = String(filter.query || '').toLowerCase();
  const visible = rows.filter((row) => {
    if (status && row.status !== status) return false;
    if (kind && row.kind !== kind) return false;
    if (query && !`${row.ref} ${row.source || ''}`.toLowerCase().includes(query)) return false;
    return true;
  });
  const flagged = visible.filter((row) => problems.has(row.status));
  const rest = visible.filter((row) => !problems.has(row.status));
  const counts = {};
  for (const row of rows) counts[row.kind] = (counts[row.kind] || 0) + 1;
  return {
    rows: [...flagged, ...rest].map((row) => ({
      ref: row.ref,
      kind: row.kind,
      status: row.status,
      source: typeof row.source === 'string' ? row.source : '',
      digest: typeof row.digest === 'string' ? row.digest : '',
    })),
    counts,
    problems: rows.filter((row) => problems.has(row.status)).length,
    empty: rows.length === 0,
    ready: rows.length > 0 && rows.every((row) => !problems.has(row.status)),
  };
}

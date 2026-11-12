export function nativeSummaryView(summary) {
  const coverage = summary && summary.coverage;
  if (!summary || summary.schema !== 'figma-flow-native-read-summary-v1' || !coverage || coverage.profile !== 'summary' || coverage.complete !== false) {
    return {ready: false, read_only: true, rows: []};
  }
  const fields = Array.isArray(coverage.fields) ? coverage.fields : [];
  const rows = (Array.isArray(summary.nodes) ? summary.nodes : []).map((node) => ({
    id: node.id,
    values: fields.map((field) => ({field, value: node[field]})),
  }));
  return {
    ready: rows.length > 0,
    read_only: true,
    coverage: {
      profile: 'summary',
      nodeIds: Array.isArray(coverage.nodeIds) ? coverage.nodeIds : [],
      fields,
      complete: false,
      omitted: Array.isArray(coverage.omitted) ? coverage.omitted : [],
    },
    rows,
  };
}

/* Read-only diagnostic record for a developer or agent. Nothing here writes a document. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.FlowAuditLog = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  const SCHEMA = 'figma-flow-audit-log-v1';
  const SECRET_QUERY = /([?&](?:access_token|refresh_token|id_token|sync_token|local_sync_token|chat_token|token|api_key|apikey|key|secret|password|capability|bearer|auth)=)[^&#\s"'<>]*/gi;
  const HOME_PATH = /(?:\/Users\/[^/\s"'<>]+|\/home\/[^/\s"'<>]+|[A-Za-z]:\\Users\\[^\\/\s"'<>]+)/g;

  function redactText(value) {
    return String(value)
      .replace(/([a-z][a-z0-9+.-]*:\/\/)[^/\s"'<>]+@/gi, '$1')
      .replace(HOME_PATH, '[home]')
      .replace(SECRET_QUERY, '$1[redacted]')
      .replace(/Bearer\s+[A-Za-z0-9._~+/=-]{6,}/g, 'Bearer [redacted]');
  }

  function asObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function textOrNull(value) {
    return typeof value === 'string' && value ? redactText(value) : null;
  }

  function pairingView(value) {
    const source = asObject(value);
    const state = textOrNull(source.state || source.status);
    const freshness = textOrNull(source.freshness);
    return {state: state, freshness: freshness, observed: Boolean(state || freshness)};
  }

  function lifecycleView(value) {
    if (!Array.isArray(value)) return {events: [], observed: false};
    return {
      observed: true,
      events: value.filter((event) => event && typeof event === 'object').map((event) => ({
        phase: textOrNull(event.phase) || 'unknown',
        status: textOrNull(event.status) || 'unknown',
        error: event.error == null || event.error === '' ? null : redactText(event.error),
        time: textOrNull(event.time),
      })),
    };
  }

  function uncertaintyView(value, events) {
    const reasons = [];
    let observed = false;
    let blocked = null;
    const source = asObject(value);
    if (typeof source.blocked_write === 'boolean') {
      observed = true;
      blocked = source.blocked_write;
      if (Array.isArray(source.reasons)) {
        for (const reason of source.reasons) {
          const text = redactText(reason);
          if (text && !reasons.includes(text)) reasons.push(text);
        }
      }
    }
    for (const event of events) {
      if (event.error && (event.status === 'blocked' || event.phase === 'uncertain')) {
        if (!reasons.includes(event.error)) reasons.push(event.error);
        if (blocked == null) blocked = true;
        observed = true;
      }
    }
    return {blocked_write: blocked, reasons: reasons, observed: observed};
  }

  function rowsView(value, mapRow) {
    if (!Array.isArray(value)) return {rows: [], observed: false};
    return {rows: value.filter((row) => row && typeof row === 'object').map(mapRow), observed: true};
  }

  function nativeCoverage(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const coverage = value.coverage && typeof value.coverage === 'object' ? value.coverage : null;
    const nodes = Array.isArray(value.nodes) ? value.nodes : [];
    if (!coverage && !nodes.length) return null;
    const nodeIds = [];
    const addId = (id) => {
      if (typeof id === 'string' && id && !nodeIds.includes(id)) nodeIds.push(id);
    };
    const listed = coverage && (coverage.nodeIds || coverage.node_ids);
    if (Array.isArray(listed)) listed.forEach(addId);
    nodes.forEach((node) => addId(node && node.id));
    const fields = [];
    const addField = (field) => {
      if (typeof field === 'string' && field && field !== 'id' && !fields.includes(field)) fields.push(redactText(field));
    };
    if (coverage && Array.isArray(coverage.fields) && coverage.fields.length) coverage.fields.forEach(addField);
    else nodes.forEach((node) => node && typeof node === 'object' && Object.keys(node).forEach(addField));
    const omittedSource = coverage && Array.isArray(coverage.omitted) ? coverage.omitted : (Array.isArray(value.omitted) ? value.omitted : []);
    const omitted = omittedSource.map((item) => redactText(item));
    const profile = coverage && typeof coverage.profile === 'string' && coverage.profile
      ? coverage.profile
      : (value.schema === 'figma-flow-native-read-summary-v1' ? 'summary' : 'full');
    const complete = coverage && typeof coverage.complete === 'boolean' ? coverage.complete : profile !== 'summary';
    return {profile: profile, node_ids: nodeIds, fields: fields, omitted: omitted, complete: complete};
  }

  function buildAuditRecord(input) {
    const source = asObject(input);
    const pairing = pairingView(source.pairing);
    const lifecycle = lifecycleView(source.lifecycle);
    const uncertainty = uncertaintyView(source.uncertainty, lifecycle.events);
    const summary = rowsView(source.input_summary, (row) => ({
      ref: textOrNull(row.ref || row.path) || '',
      kind: textOrNull(row.kind) || 'file',
      status: textOrNull(row.status) || '',
      source: textOrNull(row.source) || '',
    }));
    const dependencies = rowsView(source.dependency_freshness, (row) => ({
      label: textOrNull(row.label || row.path || row.ref) || '',
      freshness: textOrNull(row.freshness || row.state) || '',
    }));
    const native = nativeCoverage(source.native_read);
    const page = asObject(source.page);
    const record = {
      schema: SCHEMA,
      plugin_version: textOrNull(source.plugin_version),
      file_key: textOrNull(source.file_key),
      page: {id: textOrNull(source.page_id) || textOrNull(page.id), name: textOrNull(source.page_name) || textOrNull(page.name)},
      task_key: textOrNull(source.task_key),
      revision: textOrNull(source.revision),
      operation_id: textOrNull(source.operation_id),
      pairing: {state: pairing.state, freshness: pairing.freshness},
      runtime_freshness: textOrNull(source.runtime_freshness),
      lifecycle: lifecycle.events,
      uncertainty: {blocked_write: uncertainty.blocked_write, reasons: uncertainty.reasons},
      input_summary: summary.rows,
      dependency_freshness: dependencies.rows,
      native_read: native,
      unobserved: [],
    };
    const gaps = [
      ['plugin-version', record.plugin_version, '플러그인 버전이 이 내보내기에 없다.'],
      ['file-key', record.file_key, '파일 키가 이 내보내기에 없다.'],
      ['page-id', record.page.id, '페이지 ID가 이 내보내기에 없다.'],
      ['page-name', record.page.name, '페이지 이름이 이 내보내기에 없다.'],
      ['task-key', record.task_key, '작업 키가 이 내보내기에 없다.'],
      ['revision', record.revision, '리비전이 이 내보내기에 없다.'],
      ['operation-id', record.operation_id, '작업 식별자가 이 내보내기에 없다.'],
      ['pairing', pairing.observed, '페어링 상태가 이 내보내기에 없다.'],
      ['runtime-freshness', record.runtime_freshness, '런타임 신선도가 이 내보내기에 없다.'],
      ['lifecycle', lifecycle.observed, '실행 단계가 이 내보내기에 없다.'],
      ['blocked-write', uncertainty.observed, '불확실 쓰기 차단 이유가 이 내보내기에 없다.'],
      ['input-summary', summary.observed, '입력 요약 행이 이 내보내기에 없다.'],
      ['dependency-freshness', dependencies.observed, '의존성 신선도 표시가 이 내보내기에 없다.'],
      ['native-read', native, '요약 또는 전체 네이티브 읽기가 이 내보내기에 없다.'],
    ];
    for (const [check, present, reason] of gaps) {
      if (!present) record.unobserved.push({check: check, reason: reason});
    }
    record.unobserved.push({check: 'live-figma-panel', reason: '이 내보내기를 만드는 동안 실제 Figma 패널은 관찰하지 않았다.'});
    return record;
  }

  function show(value) {
    return value == null || value === '' ? '없음' : String(value);
  }

  function renderMarkdown(record, json) {
    const lines = [
      '# Figma Flow 진단 기록',
      '',
      '이 기록은 문서를 바꾸지 않는 읽기 전용 내보내기입니다. 같은 사실은 아래 JSON에 있습니다.',
      '',
      '- 스키마: ' + record.schema,
      '- 플러그인 버전: ' + show(record.plugin_version),
      '- 파일 키: ' + show(record.file_key),
      '- 페이지 ID: ' + show(record.page.id),
      '- 페이지 이름: ' + show(record.page.name),
      '- 작업 키: ' + show(record.task_key),
      '- 리비전: ' + show(record.revision),
      '- 작업 식별자: ' + show(record.operation_id),
      '',
      '## 페어링과 신선도',
      '',
      '- 페어링: ' + show(record.pairing.state),
      '- 페어링 신선도: ' + show(record.pairing.freshness),
      '- 런타임 신선도: ' + show(record.runtime_freshness),
      '',
      '## 실행 단계',
      '',
    ];
    if (!record.lifecycle.length) lines.push('기록된 단계가 없습니다.');
    for (const event of record.lifecycle) {
      lines.push('- ' + event.phase + ' · ' + event.status + ' · ' + show(event.time));
      lines.push('  오류: ' + (event.error == null ? '없음' : event.error));
    }
    lines.push('', '## 불확실 쓰기', '', '- 쓰기 차단: ' + (record.uncertainty.blocked_write == null ? '알 수 없음' : record.uncertainty.blocked_write ? '예' : '아니오'));
    if (!record.uncertainty.reasons.length) lines.push('- 이유: 없음');
    for (const reason of record.uncertainty.reasons) lines.push('- 이유: ' + reason);
    lines.push('', '## 입력 요약', '');
    if (!record.input_summary.length) lines.push('요약 행이 없습니다.');
    for (const row of record.input_summary) lines.push('- ' + row.ref + ' · ' + row.kind + ' · ' + row.status + ' · ' + row.source);
    lines.push('', '## 의존성 신선도', '');
    if (!record.dependency_freshness.length) lines.push('표시할 의존성이 없습니다.');
    for (const row of record.dependency_freshness) lines.push('- ' + row.label + ': ' + row.freshness);
    lines.push('', '## 네이티브 읽기 범위', '');
    if (!record.native_read) lines.push('요약 또는 전체 읽기가 이 내보내기에 없습니다.');
    else {
      const read = record.native_read;
      lines.push('- 프로파일: ' + read.profile);
      lines.push('- 완료: ' + (read.complete ? '예' : '아니오'));
      lines.push('- 노드: ' + (read.node_ids.join(', ') || '없음'));
      lines.push('- 필드: ' + (read.fields.join(', ') || '없음'));
      lines.push('- 빠뜨린 닫힘: ' + (read.omitted.join(', ') || '없음'));
    }
    lines.push('', '## 관찰하지 않은 검사', '');
    for (const item of record.unobserved) lines.push('- ' + item.check + ': ' + item.reason);
    lines.push('', '## 같은 사실의 JSON', '', '```json', json, '```', '');
    return lines.join('\n');
  }

  function renderAuditExport(input) {
    const record = buildAuditRecord(input);
    const json = JSON.stringify(record, null, 2);
    const markdown = renderMarkdown(record, json);
    return {schema: SCHEMA, record: record, json: json, markdown: markdown, text: markdown};
  }

  return {SCHEMA: SCHEMA, buildAuditRecord: buildAuditRecord, renderAuditExport: renderAuditExport};
});

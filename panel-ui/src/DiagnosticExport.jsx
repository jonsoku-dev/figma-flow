import React, { useState } from 'react';
import { Download, FileText } from 'lucide-react';
import auditLog from '../../figma-bridge/audit_log.js';
import { Action, Section } from './components.jsx';

export default function DiagnosticExport({ model = {}, evidence, operation, t }) {
  const [open, setOpen] = useState(false);
  const raw = evidence || {};
  const view = auditLog.renderAuditExport({
    plugin_version: model.plugin_version,
    file_key: raw.file_key || raw.fileKey || model.file_key,
    page_id: raw.page_id || raw.pageId || model.page_id,
    page_name: raw.page_name,
    task_key: model.task_key,
    revision: model.revision,
    operation_id: raw.operation_id,
    pairing: raw.pairing,
    runtime_freshness: raw.runtime_freshness,
    lifecycle: raw.lifecycle,
    uncertainty: raw.uncertainty,
    input_summary: model.input_summary,
    dependency_freshness: model.dependency_freshness,
    native_read: evidence,
    operation,
  });
  function download() {
    const url = URL.createObjectURL(new Blob([view.json], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'figma-flow-diagnostic.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <Section title={t('graph.auditTitle')}>
      <p>{t('graph.auditBoundary')}</p>
      <Action variant="secondary" icon={FileText} aria-expanded={open} onClick={() => setOpen(!open)}>
        {t('graph.auditOpen')}
      </Action>
      {open && <div className="audit-export">
        <label>
          {t('graph.auditText')}
          <textarea readOnly value={view.text} rows={10} onFocus={event => event.target.select()} />
        </label>
        <Action variant="secondary" icon={Download} onClick={download}>{t('graph.auditDownload')}</Action>
      </div>}
    </Section>
  );
}

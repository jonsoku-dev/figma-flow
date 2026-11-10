import React, { useEffect, useRef, useState } from 'react';
import { Send, Copy, ExternalLink, Eye, MessageSquare, Layers } from 'lucide-react';
import { Action, Notice, Section, Disclosure, PreviewStrip } from './components.jsx';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function requestId(t) {
  const rng = globalThis.crypto;
  if (typeof rng?.randomUUID === 'function') {
    try {
      return rng.randomUUID();
    } catch (_) {}
  }
  if (typeof rng?.getRandomValues !== 'function') throw Error(t('chat.rng'));
  const bytes = rng.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join(
    '-',
  );
}
function selectedTypes(text) {
  try {
    const offset = text.lastIndexOf('\n\n{');
    if (offset < 0) return [];
    const data = JSON.parse(text.slice(offset + 2)),
      counts = {};
    for (const node of data.selection.nodes) counts[node.type] = (counts[node.type] || 0) + 1;
    return Object.entries(counts);
  } catch (_) {
    return [];
  }
}
function errorKey(raw) {
  return /불확실|접수 여부/.test(raw)
    ? 'uncertain'
    : /20개/.test(raw)
      ? 'limitError'
      : /이전 작업|만료/.test(raw)
        ? 'expired'
        : /이미 처리|중복/.test(raw)
          ? 'duplicate'
          : /파일|페이지/.test(raw)
            ? 'scopeError'
            : /요청을 적거나/.test(raw)
              ? 'inputError'
              : 'errorHelp';
}
export default function ChatPanel({ model = {}, locale, t, send, Shell }) {
  const [message, setMessage] = useState(''),
    [includeSelection, setIncludeSelection] = useState(true),
    [includeText, setIncludeText] = useState(false);
  const [prepared, setPrepared] = useState(null),
    [busy, setBusy] = useState(false),
    [submitted, setSubmitted] = useState(false);
  const [notice, setNotice] = useState({
    title: model.paired ? 'ready' : 'unpaired',
    body: model.paired ? '' : 'unpairedHelp',
  });
  const [diagnostic, setDiagnostic] = useState(''),
    [toolsOpen, setToolsOpen] = useState(false),
    [showFallback, setShowFallback] = useState(!model.paired);
  const pendingId = useRef(null),
    busyRef = useRef(false),
    submittedRef = useRef(false),
    previewRef = useRef(null),
    summaryRef = useRef(null);
  const validThread = UUID.test(model.threadId || '');
  useEffect(() => {
    const receive = (event) => {
      const reply = event.data?.pluginMessage;
      if (!reply || typeof reply !== 'object') return;
      if (reply.type === 'chat:preview') {
        if (reply.requestId !== pendingId.current) return;
        setPrepared({
          id: reply.requestId,
          text: reply.text,
          count: reply.count,
          types: selectedTypes(reply.text),
        });
        setDiagnostic('');
        setNotice({ title: 'reviewed', body: model.paired ? 'nextSend' : 'nextCopy' });
      } else if (reply.type === 'chat:result') {
        busyRef.current = false;
        setBusy(false);
        setToolsOpen(true);
        setNotice({
          title: reply.status === 'queued' ? 'queued' : 'opened',
          body: reply.status === 'queued' ? 'queuedHelp' : 'openedHelp',
        });
      } else if (reply.type === 'chat:error') {
        const raw = String(reply.message || '');
        busyRef.current = false;
        setBusy(false);
        setDiagnostic(raw);
        setToolsOpen(true);
        setShowFallback(true);
        setNotice({ title: 'error', body: errorKey(raw) });
      }
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [model.paired]);
  useEffect(() => {
    if (prepared) summaryRef.current?.focus();
  }, [prepared]);
  function invalidate() {
    pendingId.current = null;
    setPrepared(null);
  }
  function prepare() {
    if (busyRef.current || submittedRef.current) return;
    try {
      const id = requestId(t);
      pendingId.current = id;
      setPrepared(null);
      send({
        type: 'chat:prepare',
        requestId: id,
        message,
        includeSelection,
        includeText: includeSelection && includeText,
      });
    } catch (error) {
      setDiagnostic(error.message);
      setNotice({ title: 'prepareFailed', body: 'errorHelp' });
    }
  }
  function queue() {
    if (!prepared || busyRef.current || submittedRef.current || !model.paired) return;
    busyRef.current = true;
    submittedRef.current = true;
    setBusy(true);
    setSubmitted(true);
    setNotice({ title: 'queueing', body: '' });
    send({ type: 'chat:queue', requestId: prepared.id });
  }
  function openChat() {
    if (busyRef.current || !model.paired || !validThread) return;
    try {
      const id = requestId(t);
      busyRef.current = true;
      setBusy(true);
      send({ type: 'chat:open', requestId: id });
    } catch (error) {
      setDiagnostic(error.message);
      setNotice({ title: 'openFailed', body: 'errorHelp' });
    }
  }
  function copy() {
    if (!prepared || busyRef.current) return;
    previewRef.current?.focus();
    previewRef.current?.select();
    let copied = false;
    try {
      copied = document.execCommand('copy');
    } catch (_) {}
    setNotice({ title: copied ? 'copied' : 'copyManual', body: copied ? 'copiedHelp' : 'copyHelp' });
  }
  const state = busy
    ? 'busy'
    : notice.title === 'queued' || notice.title === 'copied'
      ? 'success'
      : diagnostic
        ? 'error'
        : 'ready';
  return (
    <Shell view="chat" title={t('chat.title')} description={model.title} busy={busy}>
      <p className="hint">
        {t('chat.destination')}
        <code className="chat-destination">{validThread ? model.threadId : t('chat.noThread')}</code>
      </p>
      <Section description={t('chat.intro')}>
        <label htmlFor="chat-request">{t('chat.request')}</label>
        <textarea
          id="chat-request"
          rows={3}
          maxLength={4000}
          placeholder={t('chat.placeholder')}
          value={message}
          onChange={(event) => {
            setMessage(event.target.value);
            invalidate();
          }}
        />
        <label className="choice">
          <input
            type="checkbox"
            checked={includeSelection}
            onChange={(event) => {
              setIncludeSelection(event.target.checked);
              invalidate();
            }}
          />
          <span>{t('chat.includeSelection')}</span>
        </label>
        <label className="choice">
          <input
            type="checkbox"
            checked={includeText}
            disabled={!includeSelection}
            onChange={(event) => {
              setIncludeText(event.target.checked);
              invalidate();
            }}
          />
          <span>{t('chat.includeText')}</span>
        </label>
        <p className="hint">{t('chat.privacy')}</p>
        <Action
          variant={prepared ? 'secondary' : 'primary'}
          icon={Eye}
          disabled={busy || submitted}
          onClick={prepare}
        >
          {t('chat.prepare')}
        </Action>
      </Section>
      {prepared && (
        <>
          <section
            className="selection-card"
            ref={summaryRef}
            tabIndex={-1}
            aria-labelledby="chat-selection-title"
            aria-live="polite"
            aria-atomic="true"
          >
            <h2 id="chat-selection-title">
              <Layers size={16} aria-hidden="true" />
              {t('chat.selectionTitle')}
            </h2>
            <strong className="chat-selection-count">
              {t(prepared.count ? 'chat.selectionCount' : 'chat.noNodes', { count: prepared.count })}
            </strong>
            <p>
              {prepared.types
                .map(([type, count]) => {
                  const label = t('chat.' + type);
                  return `${label === 'chat.' + type ? type : label} · ${count}`;
                })
                .join(' / ')}
            </p>
          </section>
          <label htmlFor="chat-preview">{t('chat.preview')}</label>
          <textarea
            id="chat-preview"
            ref={previewRef}
            rows={9}
            readOnly
            value={prepared.text}
            aria-describedby="chat-preview-help"
            className="chat-preview"
          />
          <p id="chat-preview-help" className="hint">
            {t('chat.previewHelp')}
          </p>
          <div className="actions">
            {model.paired && !submitted && (
              <Action variant="primary" icon={Send} disabled={busy} onClick={queue}>
                {t('chat.send')}
              </Action>
            )}
            <Action
              variant={model.paired ? 'secondary' : 'primary'}
              icon={Copy}
              disabled={busy}
              onClick={copy}
            >
              {t('chat.copy')}
            </Action>
          </div>
        </>
      )}
      <Disclosure
        title={t('chat.more')}
        open={toolsOpen}
        onToggle={(event) => setToolsOpen(event.currentTarget.open)}
      >
        <div className="actions">
          {model.paired && (
            <Action
              variant={submitted ? 'primary' : 'secondary'}
              icon={MessageSquare}
              disabled={busy || !validThread}
              onClick={openChat}
            >
              {t('chat.open')}
            </Action>
          )}
          {showFallback && (
            <Action
              variant="secondary"
              icon={ExternalLink}
              disabled={busy || !validThread}
              onClick={() => {
                if (!busyRef.current && validThread) send({ type: 'chat:open-fallback' });
              }}
            >
              {t('chat.openLink')}
            </Action>
          )}
        </div>
      </Disclosure>
      <Notice
        state={state}
        title={t('chat.' + notice.title)}
        body={notice.body ? t('chat.' + notice.body) : ''}
      />
      {diagnostic && (
        <Disclosure title={t('chat.diagnostic')}>
          <pre className="chat-diagnostics">{diagnostic}</pre>
        </Disclosure>
      )}
    </Shell>
  );
}

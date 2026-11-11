import React, { useEffect, useReducer, useRef } from 'react';
import { Download, Layers } from 'lucide-react';
import { Action, Disclosure, Notice, PreviewStrip, Section } from './components.jsx';

const initialState = {
  result: null,
  resultKind: null,
  nativeBusy: false,
  receipt: null,
  deliveryFailed: false,
  notice: { state: 'ready', title: 'readyTitle', body: 'readyBody', details: '' },
};

function readbackNotice(receipt, paired, details = '') {
  if (receipt === 'accepted' || receipt === 'rejected') {
    const accepted = receipt === 'accepted';
    return {
      state: accepted ? 'success' : 'error',
      title: accepted ? 'verifiedTitle' : 'rejectedTitle',
      body: accepted ? 'verifiedBody' : 'rejectedBody',
      details,
    };
  }
  return {
    state: paired ? 'busy' : 'success',
    title: paired ? 'sendingTitle' : 'readTitle',
    body: paired ? 'sendingBody' : 'readBody',
    details,
  };
}

function reducer(state, action) {
  switch (action.type) {
    case 'create':
      return {
        ...initialState,
        nativeBusy: true,
        notice: { state: 'busy', title: 'creatingTitle', body: 'creatingBody', details: '' },
      };
    case 'status': {
      const next = { ...state, nativeBusy: !!action.message.busy };
      if (state.resultKind === 'failure' || state.deliveryFailed) return next;
      const details = String(action.message.message || '');
      if (state.resultKind === 'readback' && ['accepted', 'rejected'].includes(state.receipt))
        return next;
      if (action.message.state === 'error') {
        next.notice = {
          state: 'error',
          title: state.resultKind === 'readback' ? 'rejectedTitle' : 'generationFailed',
          body: 'errorBody',
          details,
        };
      } else if (state.resultKind === 'readback') {
        next.notice = readbackNotice(state.receipt, action.paired);
      } else {
        next.notice = {
          state: action.message.busy ? 'busy' : 'ready',
          title: action.message.busy ? 'creatingTitle' : 'createdTitle',
          body: action.message.busy ? 'creatingBody' : 'readyBody',
          details,
        };
      }
      return next;
    }
    case 'geometry-failure':
      return {
        ...state,
        result: action.data,
        resultKind: 'failure',
        receipt: null,
        notice: {
          state: 'error',
          title: 'geometryTitle',
          body: 'geometryBody',
          details: JSON.stringify(action.data, null, 2),
        },
      };
    case 'readback':
      return {
        ...state,
        result: action.data,
        resultKind: 'readback',
        receipt: action.paired ? 'pending' : null,
        notice: readbackNotice(null, action.paired),
      };
    case 'receipt': {
      const receipt = action.passed ? 'accepted' : 'rejected';
      return { ...state, receipt, notice: readbackNotice(receipt, true, action.details) };
    }
    case 'delivery-failure':
      return {
        ...state,
        receipt: 'failed',
        deliveryFailed: true,
        notice: {
          state: 'error',
          title: 'deliveryTitle',
          body: 'deliveryBody',
          details: action.details,
        },
      };
    case 'send-failure':
      return {
        ...state,
        nativeBusy: false,
        notice: {
          state: 'error',
          title: 'generationFailed',
          body: 'errorBody',
          details: action.details,
        },
      };
    default:
      return state;
  }
}

const productionCopy = new Set([
  'heading', 'createStep', 'createBody', 'make', 'makeBusy', 'reviewPage', 'previewAlt',
  'readyTitle', 'readyBody', 'creatingTitle', 'creatingBody', 'createdTitle',
  'generationFailed', 'readTitle', 'readBody', 'verifiedTitle', 'verifiedBody',
  'boundary', 'mobilePreviews',
]);

export function reviewMessageKey(selectedProduction, key) {
  return 'review.' + (selectedProduction && productionCopy.has(key) ? 'production.' : '') + key;
}

export default function ReviewPanel({ model, locale, t, send, Shell }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const run = useRef({ id: 0, nativeBusy: false, pending: false, received: false, controller: null });
  const download = useRef({ busy: false, timer: null, url: null });
  const sendRef = useRef(send);
  useEffect(() => {
    sendRef.current = send;
  }, [send]);
  const paired = !!model.pair;
  const candidates = model.candidates || [];
  const selectedProduction = model.selectedProduction === true && model.scope === 'selected-production' && candidates.length === 1;
  const busy = state.nativeBusy || state.receipt === 'pending';
  const text = (key, params) => t(reviewMessageKey(selectedProduction, key), params);

  useEffect(() => {
    let mounted = true;
    const current = run.current;
    async function receive(event) {
      const message = event.data?.pluginMessage;
      if (!message || typeof message !== 'object') return;
      if (message.type === 'status') {
        current.nativeBusy = !!message.busy;
        dispatch({ type: 'status', message, paired });
        return;
      }
      if (message.type === 'geometry-failure') {
        const data = message.data;
        if (
          !data ||
          data.schema !== 'figma-flow-native-geometry-failure-v1' ||
          data.passed !== false ||
          current.received
        )
          return;
        current.received = true;
        dispatch({ type: 'geometry-failure', data });
        return;
      }
      if (
        message.type !== 'readback' ||
        !message.data ||
        typeof message.data !== 'object' ||
        current.received
      )
        return;
      current.received = true;
      current.pending = paired;
      dispatch({ type: 'readback', data: message.data, paired });
      if (!paired) return;
      const id = current.id;
      const controller = new AbortController();
      current.controller = controller;
      try {
        const response = await fetch(model.pair.url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer ' + model.pair.capability,
          },
          body: JSON.stringify(message.data),
          signal: controller.signal,
        });
        const receipt = await response.json();
        if (!mounted || current.id !== id) return;
        if (typeof receipt.passed !== 'boolean' || (!response.ok && receipt.passed !== false)) {
          throw Error(receipt.errors?.join('; ') || receipt.error || response.status);
        }
        const passed = response.ok && receipt.passed;
        current.pending = false;
        dispatch({ type: 'receipt', passed, details: passed ? '' : JSON.stringify(receipt, null, 2) });
        sendRef.current({ type: 'receipt', passed });
      } catch (error) {
        if (!mounted || current.id !== id || controller.signal.aborted) return;
        current.pending = false;
        dispatch({ type: 'delivery-failure', details: String(error) });
      } finally {
        if (current.controller === controller) current.controller = null;
      }
    }
    window.addEventListener('message', receive);
    return () => {
      mounted = false;
      window.removeEventListener('message', receive);
      current.controller?.abort();
    };
  }, [model.pair?.url, model.pair?.capability, paired]);

  useEffect(
    () => () => {
      const current = download.current;
      clearTimeout(current.timer);
      if (current.url) URL.revokeObjectURL(current.url);
    },
    [],
  );

  function createDrafts() {
    const current = run.current;
    if (current.nativeBusy || current.pending) return;
    current.controller?.abort();
    current.id += 1;
    current.nativeBusy = true;
    current.pending = false;
    current.received = false;
    dispatch({ type: 'create' });
    try {
      send({ type: 'draft-review' });
    } catch (error) {
      current.nativeBusy = false;
      dispatch({ type: 'send-failure', details: String(error) });
    }
  }

  function saveResult() {
    const current = download.current;
    if (!state.result || current.busy) return;
    current.busy = true;
    try {
      const anchor = document.createElement('a');
      current.url = URL.createObjectURL(
        new Blob([JSON.stringify(state.result, null, 2)], { type: 'application/json' }),
      );
      anchor.href = current.url;
      anchor.download =
        state.resultKind === 'failure'
          ? 'figma-direction-review-failure.json'
          : 'figma-direction-review-readback.json';
      anchor.click();
    } finally {
      current.timer = setTimeout(() => {
        if (current.url) URL.revokeObjectURL(current.url);
        current.url = null;
        current.busy = false;
      }, 250);
    }
  }

  const saveLabel = text(state.resultKind === 'failure' ? 'saveFailure' : 'save');
  return (
    <Shell
      view="review"
      title={text(candidates.length ? 'heading' : 'emptyHeading', { count: candidates.length })}
      description={
        candidates.length
          ? candidates.map((candidate) => candidate.title).join(' · ')
          : text('emptyNames')
      }
      busy={busy}
    >
      <PreviewStrip
        items={candidates.flatMap((candidate) => {
          const desktop = candidate.previews?.find((item) => item.viewport === 'desktop');
          return desktop
            ? [
                {
                  title: candidate.title,
                  src: desktop.src,
                  alt: text('previewAlt', { name: candidate.title, viewport: text('desktop') }),
                  caption: candidate.title,
                },
              ]
            : [];
        })}
      />
      <Section title={text('createStep')} description={text('createBody')}>
        <p className="metadata">
          {text(model.filePinned ? 'exactFile' : 'currentFile')} /{' '}
          {model.pageName ? (
            <>
              {text('pageLabel')}: <span>{model.pageName}</span>
            </>
          ) : (
            text('reviewPage')
          )}
        </p>
        <div className="actions">
          <Action
            id="make"
            variant={state.result ? 'secondary' : 'primary'}
            icon={Layers}
            disabled={busy}
            aria-label={text(busy ? 'makeBusy' : 'make')}
            onClick={createDrafts}
          >
            {text(busy ? 'makeBusy' : 'make')}
          </Action>
        </div>
      </Section>
      <Section title={text('readStep')}>
        <Notice
          id="status-panel"
          state={state.notice.state}
          title={text(state.notice.title)}
          body={text(state.notice.body)}
          aria-live="polite"
          aria-atomic="true"
          aria-busy={busy}
        >
          {state.notice.details && (
            <Disclosure id="status-details" title={text('details')}>
              <pre id="status">{state.notice.details}</pre>
            </Disclosure>
          )}
        </Notice>
      </Section>
      <Section
        title={text('saveStep')}
        description={text(paired ? 'saveBodyPaired' : 'saveBodyPortable')}
      >
        <div className="actions">
          <Action
            id="save"
            variant={state.result ? 'primary' : 'secondary'}
            icon={Download}
            disabled={!state.result}
            aria-label={saveLabel}
            onClick={saveResult}
          >
            {saveLabel}
          </Action>
        </div>
      </Section>
      {candidates.some((candidate) =>
        candidate.previews?.some((item) => item.viewport === 'mobile'),
      ) && (
        <Disclosure title={text('mobilePreviews')}>
          <PreviewStrip
            items={candidates.flatMap((candidate) => {
              const mobile = candidate.previews?.find((item) => item.viewport === 'mobile');
              return mobile
                ? [
                    {
                      title: candidate.title,
                      src: mobile.src,
                      alt: text('previewAlt', { name: candidate.title, viewport: text('mobile') }),
                    },
                  ]
                : [];
            })}
          />
        </Disclosure>
      )}
      <p className="metadata">{text('boundary')}</p>
    </Shell>
  );
}

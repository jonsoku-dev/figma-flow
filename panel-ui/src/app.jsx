import React, { useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Shell, PanelContext } from './components.jsx';
import { views } from './view-registry.generated.js';
import './styles/index.css';
const view = document.documentElement.dataset.flowView;
const model = JSON.parse(document.getElementById('flow-model').textContent);
const send = (payload) => parent.postMessage({ pluginMessage: payload }, '*');
function App() {
  const [locale, changeLocale] = useState(window.FlowUI.locale);
  const [hostBusy, setHostBusy] = useState(false);
  useEffect(() => {
    const language = () => changeLocale(window.FlowUI.locale);
    const busy = (e) => setHostBusy(Boolean(e.detail?.busy));
    window.addEventListener('flow:locale', language);
    window.addEventListener('flow:host-busy', busy);
    return () => {
      window.removeEventListener('flow:locale', language);
      window.removeEventListener('flow:host-busy', busy);
    };
  }, []);
  const setLocale = useCallback((code) => {
    if (window.FlowUI.setLocale(code)) changeLocale(window.FlowUI.locale);
  }, []);
  const t = useCallback((key, params) => window.FlowUI.t(key, params), [locale]);
  const View = views[view];
  if (!View) throw new Error(`Unknown Figma Flow panel view: ${view}`);
  return (
    <PanelContext.Provider value={{ locale, t, setLocale, hostBusy }}>
      <View {...{ model, locale, t, setLocale, send, Shell }} />
    </PanelContext.Provider>
  );
}
createRoot(document.getElementById('flow-root')).render(<App />);

/* Shared panel controls never insert native names or errors as markup. */
(() => {
  const nav = document.getElementById('workspace-tablist');
  const locale = document.getElementById('workspace-locale');
  const names = ['tasks', 'history', 'codex'];
  let settings = {mode: document.documentElement.dataset.flowWorkspace === 'true' ? 'workspace' : 'standalone', active: 'tasks', busy: false};
  function setState(update = {}) {
    settings = {...settings, ...update};
    if (nav) nav.hidden = settings.mode !== 'workspace';
    for (const name of names) {
      const button = document.getElementById('tab-' + name);
      if (!button) continue;
      button.disabled = Boolean(settings.busy);
      if (settings.active === name) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    }
    if (locale && globalThis.FlowUI) locale.value = FlowUI.locale;
  }
  function mount(options = {}) {
    setState(options);
    return globalThis.FlowPanel;
  }
  function status({region, title, body, state, titleText, bodyText = ''}) {
    const container = document.getElementById(region), heading = document.getElementById(title), content = document.getElementById(body);
    if (!container || !heading || !content) throw Error('Missing shared status component');
    container.hidden = false;
    container.dataset.state = state;
    container.setAttribute('aria-busy', String(state === 'busy'));
    for (const [element, value] of [[heading, titleText], [content, bodyText]]) {
      element.removeAttribute('data-i18n');
      element.textContent = value;
    }
    content.hidden = !bodyText;
  }
  for (const name of names) {
    document.getElementById('tab-' + name)?.addEventListener('click', () => {
      if (settings.mode === 'workspace' && !settings.busy) settings.onNavigate?.(name);
    });
  }
  locale?.addEventListener('change', () => {
    const value = locale.value;
    if (!['ko', 'en', 'ja'].includes(value)) return;
    if (settings.onLocale) settings.onLocale(value);
    else globalThis.FlowUI?.setLocale(value);
  });
  window.addEventListener('flow:locale', () => setState());
  globalThis.FlowPanel = Object.freeze({mount, setState, status});
  mount();
})();

(() => {
  const messages = __FLOW_MESSAGES__;
  const root = document.documentElement;
  const normalize = value => String(value || '').toLowerCase().split(/[-_]/)[0];
  const localeCodes = () => Object.keys(Object.values(messages).find(entry => entry && typeof entry === 'object') || {});
  const supported = value => localeCodes().includes(normalize(value));
  const preferences = [root?.dataset?.flowLocale, ...(globalThis.navigator?.languages || []), globalThis.navigator?.language];
  let locale = normalize(preferences.find(supported) || localeCodes()[0]);
  function t(key, params = {}) {
    const entry = messages[key];
    if (!entry) return key;
    return entry[locale].replace(/\{(\w+)\}/g, (literal, name) =>
      Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : literal);
  }
  function apply(container = document) {
    if (root) root.lang = locale;
    for (const [marker, attribute] of [['data-i18n', null], ['data-i18n-aria', 'aria-label'],
      ['data-i18n-title', 'title'], ['data-i18n-alt', 'alt'], ['data-i18n-placeholder', 'placeholder']]) {
      for (const element of container.querySelectorAll?.('[' + marker + ']') || []) {
        const params = element.dataset?.i18nParams ? JSON.parse(element.dataset.i18nParams) : {};
        const value = t(element.getAttribute(marker), params);
        if (attribute) element.setAttribute(attribute, value);
        else element.textContent = value;
      }
    }
  }
  globalThis.FlowUI = Object.freeze({
    get locale() { return locale; }, get locales() { return localeCodes(); }, t, apply,
    setLocale(value) {
      if (!supported(value)) return false;
      const next = normalize(value), changed = next !== locale;
      locale = next;
      apply();
      if (changed) window.dispatchEvent(new CustomEvent('flow:locale', {detail: {locale}}));
      return true;
    }
  });
  apply();
})();

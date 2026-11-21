/* Per-installation storage. File scope prevents a seat declared in one team
   being applied to another team's file when the API cannot identify the team. */
function createWorkspaceProfile(api, policy, runtime) {
  const defaults = { plan: 'unknown', seat: 'unknown' };
  let active = null;
  let pending = Promise.resolve();
  let initialIdentityChecked = false;

  function safely(fn) {
    try { return fn(); } catch (_) { return null; }
  }

  function observe(locale, fields = Object.keys(policy.contextFields)) {
    const readers = {
      user: () => api.currentUser, page: () => api.currentPage, document: () => api.root,
      plugin: () => api, runtime: () => runtime, ui: () => ({locale})
    };
    const sources = new Map();
    const context = {};
    for (const key of fields) {
      const [source, property] = policy.contextFields[key];
      if (!sources.has(source)) sources.set(source, safely(readers[source]));
      const value = safely(() => sources.get(source)[property]);
      context[key] = typeof value === 'string' && value ? value : null;
    }
    return context;
  }

  function sameScope(left, right) {
    return !!left && left.userId === right.userId && left.fileKey === right.fileKey;
  }

  function valid(value) {
    return value && policy.options.plans.includes(value.plan) && policy.options.seats.includes(value.seat);
  }

  function projection(state, context) {
    const declared = { ...state.declared };
    return {
      schemaVersion: policy.version, needsSetup: !state.confirmed, storage: state.storage,
      context, declared, options: policy.options,
      capabilities: evaluateProfileCapabilities(policy, context, declared, state.confirmed),
      source: {
        plan: declared.plan === 'unknown' ? 'unknown' : 'user',
        seat: declared.seat === 'unknown' ? 'unknown' : 'user'
      }
    };
  }

  function schedule(operation) {
    const result = pending.then(operation);
    pending = result.catch(() => {});
    return result;
  }

  async function resolve(context) {
    const stillCurrent = () => sameScope(context, observe(null, ['userId', 'fileKey']));
    if (!stillCurrent()) throw Error('The Figma profile scope changed.');
    const state = sameScope(active && active.context, context) ? active : {
      context, confirmed: false, declared: defaults, storage: 'session', observed: null
    };
    state.context = context;
    const storage = safely(() => api.clientStorage);
    state.storage = 'session';
    if (storage && context.userId && context.fileKey) {
      const key = 'figma-flow-profile-v' + policy.version + ':' +
        encodeURIComponent(context.userId) + ':' + encodeURIComponent(context.fileKey);
      state.key = key;
      try {
        const saved = await storage.getAsync(key + ':settings');
        if (!state.localFallback && saved && saved.version === policy.version && valid(saved)) {
          state.declared = { plan: saved.plan, seat: saved.seat };
          state.confirmed = true;
        } else if (!state.localFallback) {
          state.declared = defaults;
          state.confirmed = false;
        }
        const stamp = JSON.stringify(context);
        if (state.observed !== stamp && stillCurrent()) {
          await storage.setAsync(key + ':context', {
            version: policy.version, observedAt: new Date().toISOString(), context
          });
          state.observed = stamp;
        }
        state.storage = state.localFallback ? 'session' : 'local';
      } catch (_) {
        state.storage = 'session';
      }
    }
    if (!stillCurrent()) throw Error('The Figma profile scope changed.');
    active = state;
    return state;
  }

  function allowsOperation(operation) {
    const capability = policy.operations[operation];
    if (typeof capability !== 'string') return policy.passthrough.includes(operation);
    const context = observe(null, ['userId', 'fileKey', 'editorType', 'mode']);
    const current = active && sameScope(active.context, context) ? active : null;
    return !!capability && evaluateProfileCapabilities(policy, context,
      current ? current.declared : defaults, !!(current && current.confirmed))[capability] === true;
  }

  return {
    load(locale) {
      const context = observe(locale);
      return schedule(async () => {
        let current = context;
        // Desktop can expose the file before the current-user getter is ready.
        if (!initialIdentityChecked && !current.userId && typeof setTimeout === 'function') {
          for (const delay of [100, 250, 500]) {
            await new Promise(done => setTimeout(done, delay));
            current = observe(locale);
            if (current.fileKey !== context.fileKey || current.pageId !== context.pageId) {
              throw Error('The Figma profile scope changed.');
            }
            if (current.userId) break;
          }
        }
        initialIdentityChecked = true;
        return projection(await resolve(current), current);
      });
    },
    save(declared, locale, isCurrent = () => true) {
      const context = observe(locale);
      if (!valid(declared)) return Promise.reject(Error('Choose a listed plan and seat.'));
      if (!active || !sameScope(active.context, context)) {
        return Promise.reject(Error('Reopen settings for the current Figma user and file.'));
      }
      const choice = { plan: declared.plan, seat: declared.seat };
      return schedule(async () => {
        const state = await resolve(context);
        const latest = observe(null, ['userId', 'fileKey', 'pageId']);
        if (!sameScope(context, latest) || latest.pageId !== context.pageId || !isCurrent()) {
          throw Error('The Figma settings session changed before saving.');
        }
        const storage = safely(() => api.clientStorage);
        state.localFallback = true;
        state.storage = 'session';
        if (state.key && storage) {
          try {
            await storage.setAsync(state.key + ':settings', {
              version: policy.version, ...choice, confirmedAt: new Date().toISOString()
            });
            state.storage = 'local';
            state.localFallback = false;
          } catch (_) { /* Keep the confirmed choice in this session. */ }
        }
        if (!sameScope(context, observe(null, ['userId', 'fileKey']))) throw Error('The Figma profile scope changed.');
        state.declared = choice;
        state.confirmed = true;
        return projection(state, context);
      });
    },
    allowsOperation,
    async admitOperation(operation) {
      if (profileOperationNeedsAdmission(policy, operation)) {
        const context = observe(active && active.context.locale);
        await schedule(() => resolve(context));
      }
      return allowsOperation(operation);
    }
  };
}

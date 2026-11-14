/* Opt-in fresh-read measurement for `graph_sync.py discover --read-measure`.
   Appended after the discovery host only for measured tasks; default bundles never contain it. */
const NATIVE_READ_MEASUREMENT_SCHEMA = "figma-flow-native-read-measurement-v1";

function nativeReadCallCounter(figma, page, clock) {
  const counts = {node_property_gets: 0, node_property_has: 0, by_property: {}, api_calls: {}};
  const invoke = (name, fn, target, args) => {
    const row = counts.api_calls[name] || (counts.api_calls[name] = {calls: 0, elapsed_ms: 0});
    row.calls++;
    const started = clock();
    const settle = () => { row.elapsed_ms += clock() - started; };
    let value;
    try { value = fn.apply(target, args); }
    catch (error) { settle(); throw error; }
    if (!value || typeof value.then !== "function") { settle(); return value; }
    return value.then(result => { settle(); return result; }, error => { settle(); throw error; });
  };
  const api = (object, prefix) => new Proxy(object, {
    get(target, key) {
      const value = Reflect.get(target, key, target);
      if (typeof key !== "string" || key === "then") return value;
      if (key === "variables" && value && typeof value === "object") return api(value, prefix + ".variables");
      if (typeof value !== "function") return value;
      return (...args) => {
        const result = invoke(prefix + "." + key, value, target, args);
        return key === "getImageByHash" && result && typeof result === "object" ? api(result, "image") : result;
      };
    }
  });
  const nodes = new WeakMap();
  const node = raw => {
    if (!raw || typeof raw !== "object") return raw;
    if (nodes.has(raw)) return nodes.get(raw);
    const proxy = new Proxy(raw, {
      has(target, key) {
        if (typeof key === "string") counts.node_property_has++;
        return Reflect.has(target, key);
      },
      get(target, key) {
        if (typeof key !== "string" || key === "then") return Reflect.get(target, key, target);
        counts.node_property_gets++;
        counts.by_property[key] = (counts.by_property[key] || 0) + 1;
        const value = Reflect.get(target, key, target);
        if (key === "parent") return node(value);
        if (key === "children") return value ? Array.from(value, node) : value;
        if (typeof value !== "function") return value;
        return (...args) => {
          const result = invoke("node." + key, value, target, args);
          return key === "findAll" ? Array.from(result || [], node) : result;
        };
      }
    });
    nodes.set(raw, proxy);
    return proxy;
  };
  return {figma: api(figma, "figma"), page: node(page), counts};
}

async function measureNativeRead(reader, figma, page, mode, clock) {
  const pageId = page.id;
  if (mode === "timing") {
    const started = clock();
    const read = await reader(figma, page);
    return {read, row: {pageId, reader_elapsed_ms: clock() - started}};
  }
  if (mode !== "getter-counts") throw new Error("Unknown native read measurement mode");
  const counter = nativeReadCallCounter(figma, page, clock);
  const started = clock();
  const read = await reader(counter.figma, counter.page);
  const elapsed = clock() - started;
  return {read, row: {pageId, reader_elapsed_ms: elapsed, instrumented: true, reader_result_bytes: utf8JsonBytes(read), ...counter.counts}};
}

function installNativeReadMeasurement(mode) {
  const precise = typeof performance === "object" && performance && typeof performance.now === "function";
  const clock = precise ? () => performance.now() : () => Date.now();
  const productionRead = readNativeSemantics;
  const productionDiscovery = discoverGraphNative;
  let active = null;
  readNativeSemantics = async function(figma, page) {
    if (arguments[2] !== undefined || !active) return productionRead.apply(this, arguments);
    const {read, row} = await measureNativeRead(productionRead, figma, page, mode, clock);
    active.pages.push(row);
    return read;
  };
  discoverGraphNative = async function(figma, scope) {
    const measurement = {schema: NATIVE_READ_MEASUREMENT_SCHEMA, mode, clock: precise ? "performance.now" : "Date.now", pages: []};
    active = measurement;
    const started = clock();
    try {
      const result = await productionDiscovery(figma, scope);
      measurement.discovery_elapsed_ms = clock() - started;
      result.read_measurement = measurement;
      return result;
    } finally { active = null; }
  };
}

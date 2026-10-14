// All device-private material lives here. Never sent to the server.

window.OfflinePayStorage = (() => {
  const K = {
    user: "opay.user",
    role: "opay.role",
    deviceId: "opay.device_id",
    privateKey: "opay.device_priv",
    publicKey: "opay.device_pub",
    counter: "opay.counter",
    bankKey: "opay.bank_pub",
    cert: "opay.cert",
    queue: "opay.queue",
  };

  function get(key, fallback = null) {
    const v = localStorage.getItem(key);
    if (v === null) return fallback;
    try { return JSON.parse(v); } catch { return v; }
  }

  function set(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function remove(key) {
    localStorage.removeItem(key);
  }

  function clearAll() {
    Object.values(K).forEach(remove);
  }

  function nextCounter() {
    const c = (get(K.counter, 0) || 0) + 1;
    set(K.counter, c);
    return c;
  }

  function currentCounter() {
    return get(K.counter, 0) || 0;
  }

  function queue() {
    return get(K.queue, []) || [];
  }

  function queueAdd(entry) {
    const q = queue();
    q.unshift(entry);
    set(K.queue, q.slice(0, 100));
  }

  function queueUpdate(id, patch) {
    const q = queue().map(e => e.id === id ? { ...e, ...patch } : e);
    set(K.queue, q);
  }

  return {
    KEYS: K,
    get, set, remove, clearAll,
    nextCounter, currentCounter,
    queue, queueAdd, queueUpdate,
  };
})();
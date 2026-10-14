window.OfflinePayApi = (() => {
  function base() {
    return (window.OFFLINEPAY_API_BASE || "").replace(/\/+$/, "");
  }

  async function call(method, path, body, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    const user = window.OfflinePayStorage.get(window.OfflinePayStorage.KEYS.user);
    if (user && !opts.noAuth) headers["X-User"] = user;

    const res = await fetch(base() + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }

    if (!res.ok) {
      const err = new Error(
        (data && (data.detail || data.message)) || `HTTP ${res.status}`
      );
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  return {
    base,
    get: (p, o) => call("GET", p, null, o),
    post: (p, b, o) => call("POST", p, b, o),

    login: (username, password) => call("POST", "/api/login", { username, password }, { noAuth: true }),
    registerDevice: (publicKey) => call("POST", "/api/devices", { public_key: publicKey }),
    wallet: () => call("GET", "/api/wallet"),
    reserve: (amount) => call("POST", "/api/reserve", { amount }),
    issueCertificate: (reserveId, deviceId) =>
      call("POST", "/api/certificates", { reserve_id: reserveId, device_id: deviceId }),
    bankPublicKey: () => call("GET", "/api/bank-public-key", null, { noAuth: true }),
    syncToken: (token) => call("POST", "/api/sync/token", token),
    receipt: (tokenId) => call("GET", `/api/receipts/${tokenId}`),
    openDispute: (tokenId, reason) => call("POST", "/api/disputes", { token_id: tokenId, reason }),
    analystQueue: () => call("GET", "/api/analyst/queue"),
    analystDecision: (disputeId, decision) =>
      call("POST", "/api/analyst/decision", { dispute_id: disputeId, decision }),
  };
})();
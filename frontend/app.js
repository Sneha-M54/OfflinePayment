(() => {
  const S = window.OfflinePayStorage;
  const API = window.OfflinePayApi;
  const C = window.OfflinePayCrypto;

  const app = document.getElementById("app");
  const netDot = document.getElementById("net-indicator");
  const netLabel = document.getElementById("net-label");
  const logoutBtn = document.getElementById("logout-btn");

  // ----------------------------------------------------------------
  // network indicator
  // ----------------------------------------------------------------
  function setNet() {
    const on = navigator.onLine;
    netDot.className = "dot " + (on ? "online" : "offline");
    netLabel.textContent = on ? "online" : "offline";
  }
  window.addEventListener("online", setNet);
  window.addEventListener("offline", setNet);
  setNet();

  // ----------------------------------------------------------------
  // small UI helpers
  // ----------------------------------------------------------------
  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }
  function html(strings, ...values) {
    return strings.reduce((out, s, i) => out + s + (values[i] ?? ""), "");
  }
  function fmtAmount(n) { return Number(n || 0).toLocaleString(); }
  function fmtTime(unix) { return new Date(unix * 1000).toLocaleString(); }
  function banner(kind, msg) {
    const b = el(`<div class="banner ${kind}"></div>`);
    b.textContent = msg;
    return b;
  }
  function clearBanners() {
    document.querySelectorAll(".banner").forEach(n => n.remove());
  }

  function requireAuth() {
    const user = S.get(S.KEYS.user);
    const role = S.get(S.KEYS.role);
    if (!user) { renderLogin(); return null; }
    return { user, role };
  }

  // ----------------------------------------------------------------
  // login
  // ----------------------------------------------------------------
  function renderLogin() {
    logoutBtn.classList.add("hidden");
    app.innerHTML = "";
    const view = el(html`
      <div>
        <div class="card">
          <h1>Sign in</h1>
          <div class="row">
            <div>
              <label>Username</label>
              <input id="login-user" autocomplete="username" />
            </div>
            <div>
              <label>Password</label>
              <input id="login-pass" type="password" autocomplete="current-password" />
            </div>
          </div>
          <div style="margin-top:12px"><button id="login-go">Sign in</button></div>
        </div>

        <div class="card">
          <h3>Demo accounts</h3>
          <ul class="plain">
            <li><button class="ghost" data-fill="alice|alice123">alice / alice123 (customer)</button></li>
            <li><button class="ghost" data-fill="bob|bob123">bob / bob123 (customer)</button></li>
            <li><button class="ghost" data-fill="merchant|shop123">merchant / shop123 (merchant)</button></li>
            <li><button class="ghost" data-fill="analyst|analyst123">analyst / analyst123 (analyst)</button></li>
          </ul>
        </div>
      </div>
    `);
    app.appendChild(view);

    view.querySelectorAll("[data-fill]").forEach(b => {
      b.addEventListener("click", () => {
        const [u, p] = b.dataset.fill.split("|");
        view.querySelector("#login-user").value = u;
        view.querySelector("#login-pass").value = p;
      });
    });

    view.querySelector("#login-go").addEventListener("click", async () => {
      clearBanners();
      const u = view.querySelector("#login-user").value.trim();
      const p = view.querySelector("#login-pass").value;
      if (!u || !p) return app.prepend(banner("err", "Enter username and password"));
      try {
        const res = await API.login(u, p);
        S.set(S.KEYS.user, res.user_id);
        S.set(S.KEYS.role, res.role);
        await ensureDevice();
        await cacheBankKey();
        route();
      } catch (e) {
        app.prepend(banner("err", e.message));
      }
    });
  }

  // ----------------------------------------------------------------
  // device registration (once per browser)
  // ----------------------------------------------------------------
  async function ensureDevice() {
    if (S.get(S.KEYS.deviceId)) return S.get(S.KEYS.deviceId);
    const kp = await C.generateKeypair();
    const res = await API.registerDevice(kp.publicKeyB64);
    S.set(S.KEYS.deviceId, res.device_id);
    S.set(S.KEYS.privateKey, kp.privateKeyPkcs8B64);
    S.set(S.KEYS.publicKey, kp.publicKeyB64);
    return res.device_id;
  }

  async function cacheBankKey() {
    if (S.get(S.KEYS.bankKey)) return S.get(S.KEYS.bankKey);
    try {
      const res = await API.bankPublicKey();
      S.set(S.KEYS.bankKey, res.public_key);
      return res.public_key;
    } catch {
      return null;
    }
  }

  // ----------------------------------------------------------------
  // router
  // ----------------------------------------------------------------
  function route() {
    const auth = requireAuth();
    if (!auth) return;
    logoutBtn.classList.remove("hidden");
    logoutBtn.onclick = () => {
      S.clearAll();
      renderLogin();
    };

    if (auth.role === "analyst") return renderAnalyst();
    return renderUser();
  }

  // ----------------------------------------------------------------
  // user (customer / merchant) — tabs: wallet, pay, receive, queue
  // ----------------------------------------------------------------
  let activeTab = "wallet";

  function renderUser() {
    app.innerHTML = "";
    const tabs = el(html`
      <div class="tabs">
        <button data-tab="wallet">Wallet</button>
        <button data-tab="reserve">Reserve</button>
        <button data-tab="pay">Pay</button>
        <button data-tab="receive">Receive</button>
        <button data-tab="queue">Sync queue</button>
      </div>
    `);
    app.appendChild(tabs);
    const body = el(`<div id="tab-body"></div>`);
    app.appendChild(body);

    const render = () => {
      tabs.querySelectorAll("button").forEach(b =>
        b.classList.toggle("active", b.dataset.tab === activeTab)
      );
      body.innerHTML = "";
      if (activeTab === "wallet") return renderWallet(body);
      if (activeTab === "reserve") return renderReserve(body);
      if (activeTab === "pay") return renderPay(body);
      if (activeTab === "receive") return renderReceive(body);
      if (activeTab === "queue") return renderQueue(body);
    };
    tabs.querySelectorAll("button").forEach(b =>
      b.addEventListener("click", () => { activeTab = b.dataset.tab; render(); })
    );
    render();
  }

  // -------- wallet --------
  async function renderWallet(body) {
    const card = el(`<div class="card"><h1>Wallet</h1><div id="w"></div></div>`);
    body.appendChild(card);
    const w = card.querySelector("#w");
    w.textContent = "Loading…";
    try {
      const info = await API.wallet();
      w.innerHTML = html`
        <div class="kv"><span class="k">User</span><span class="v mono">${info.user_id}</span></div>
        <div class="kv"><span class="k">Tier</span><span class="v">${info.tier}</span></div>
        <div class="kv"><span class="k">Balance</span><span class="v">${fmtAmount(info.balance)}</span></div>
        <div class="kv"><span class="k">Reserved</span><span class="v">${fmtAmount(info.reserved)}</span></div>
        <div class="kv"><span class="k">Available</span><span class="v">${fmtAmount(info.available)}</span></div>
        <div class="kv"><span class="k">Per-payment limit</span><span class="v">${fmtAmount(info.per_payment_limit)}</span></div>
        <div class="kv"><span class="k">Max reserve</span><span class="v">${fmtAmount(info.max_reserve)}</span></div>
        ${info.certificate ? html`
          <div class="kv"><span class="k">Certificate</span><span class="v mono">${info.certificate.id}</span></div>
          <div class="kv"><span class="k">Certificate expires</span><span class="v">${fmtTime(info.certificate.expires_at)}</span></div>
        ` : `<div class="kv"><span class="k">Certificate</span><span class="v muted">none</span></div>`}
      `;
    } catch (e) {
      w.innerHTML = "";
      w.appendChild(banner("err", e.message));
    }
  }

  // -------- reserve --------
  function renderReserve(body) {
    const card = el(html`
      <div class="card">
        <h1>Add to reserve</h1>
        <label>Amount</label>
        <input id="res-amount" type="number" min="1" step="1" value="500" />
        <div style="margin-top:12px"><button id="res-go">Lock into reserve</button></div>
        <p class="muted" style="margin-top:10px">
          Locking moves funds out of your available balance into the offline reserve.
          Then issue a certificate so your device can pay offline.
        </p>
      </div>
    `);
    body.appendChild(card);
    card.querySelector("#res-go").addEventListener("click", async () => {
      clearBanners();
      const amount = parseInt(card.querySelector("#res-amount").value, 10);
      if (!amount || amount <= 0) return body.prepend(banner("err", "Enter a positive amount"));
      try {
        const r = await API.reserve(amount);
        const deviceId = S.get(S.KEYS.deviceId);
        const cert = await API.issueCertificate(r.reserve_id, deviceId);
        S.set(S.KEYS.cert, cert);
        body.prepend(banner("ok", `Reserved ${fmtAmount(amount)}. Certificate ${cert.certificate_id} issued.`));
      } catch (e) {
        body.prepend(banner("err", e.message));
      }
    });
  }

  // -------- pay --------
  function renderPay(body) {
    const card = el(html`
      <div class="card">
        <h1>Pay (offline)</h1>
        <div class="row">
          <div>
            <label>Payee user id</label>
            <input id="pay-payee" value="u_merchant" />
          </div>
          <div>
            <label>Amount</label>
            <input id="pay-amount" type="number" min="1" value="50" />
          </div>
        </div>
        <div style="margin-top:12px"><button id="pay-go">Create signed token</button></div>
        <div id="pay-out" style="margin-top:12px"></div>
      </div>
    `);
    body.appendChild(card);

    card.querySelector("#pay-go").addEventListener("click", async () => {
      clearBanners();
      const out = card.querySelector("#pay-out");
      out.innerHTML = "";
      try {
        const cert = S.get(S.KEYS.cert);
        const priv = S.get(S.KEYS.privateKey);
        const user = S.get(S.KEYS.user);
        if (!cert) throw new Error("No certificate yet. Add to reserve first.");
        if (!priv) throw new Error("No device key on this browser.");

        const payee = card.querySelector("#pay-payee").value.trim();
        const amount = parseInt(card.querySelector("#pay-amount").value, 10);
        if (!payee || !amount) throw new Error("Enter payee and amount");

        const now = Math.floor(Date.now() / 1000);
        const nonce = "n_" + Math.random().toString(36).slice(2) + "_" + Date.now();
        const counter = S.nextCounter();

        const payload = {
          certificate_id: cert.certificate_id,
          payer_id: user,
          payee_id: payee,
          amount,
          nonce,
          counter,
          issued_at: now,
          expires_at: now + 3600,
        };
        const signature = await C.sign(priv, payload);
        const token = { ...payload, signature };

        S.queueAdd({
          id: nonce,
          token,
          status: "pending",
          created_at: now,
          label: `Pay ${amount} → ${payee}`,
        });

        out.appendChild(banner("ok", "Signed token created. Copy and send to the payee."));
        const ta = el(`<textarea readonly></textarea>`);
        ta.value = JSON.stringify(token);
        out.appendChild(ta);
        const btn = el(`<button class="ghost" style="margin-top:8px">Copy</button>`);
        btn.onclick = () => { ta.select(); document.execCommand("copy"); };
        out.appendChild(btn);
      } catch (e) {
        out.appendChild(banner("err", e.message));
      }
    });
  }

  // -------- receive --------
  function renderReceive(body) {
    const card = el(html`
      <div class="card">
        <h1>Receive (offline verify)</h1>
        <label>Paste token JSON</label>
        <textarea id="recv-token" placeholder='{"certificate_id":"...", "signature":"..."}'></textarea>
        <div style="margin-top:12px"><button id="recv-go">Verify offline</button></div>
        <div id="recv-out" style="margin-top:12px"></div>
      </div>
    `);
    body.appendChild(card);

    card.querySelector("#recv-go").addEventListener("click", async () => {
      clearBanners();
      const out = card.querySelector("#recv-out");
      out.innerHTML = "";
      try {
        const raw = card.querySelector("#recv-token").value.trim();
        if (!raw) throw new Error("Paste a token first");
        const token = JSON.parse(raw);

        const cert = S.get(S.KEYS.cert);
        if (!cert) throw new Error("No certificate cached. Sign in online once first.");
        if (token.certificate_id !== cert.certificate_id)
          throw new Error("Token does not match the cached certificate");

        const bankPub = S.get(S.KEYS.bankKey);
        if (!bankPub) throw new Error("Bank public key not cached. Sign in online once first.");

        const certPayload = cert.payload;
        const certOk = await C.verify(bankPub, certPayload, cert.signature);
        if (!certOk) throw new Error("Bank signature on certificate failed");

        const now = Math.floor(Date.now() / 1000);
        if (certPayload.expires_at && now > certPayload.expires_at)
          throw new Error("Certificate expired");

        if (token.expires_at && now > token.expires_at)
          throw new Error("Token expired");

        if (token.amount > certPayload.per_payment_limit)
          throw new Error(`Amount ${token.amount} exceeds per-payment limit ${certPayload.per_payment_limit}`);

        const tokenPayload = {
          certificate_id: token.certificate_id,
          payer_id: token.payer_id,
          payee_id: token.payee_id,
          amount: token.amount,
          nonce: token.nonce,
          counter: token.counter,
          issued_at: token.issued_at,
          expires_at: token.expires_at,
        };
        const payerOk = await C.verify(certPayload.device_public_key, tokenPayload, token.signature);
        if (!payerOk) throw new Error("Payer device signature failed");

        out.appendChild(banner("ok", "Verified offline. Token is authentic."));
        const pre = el(`<pre class="mono"></pre>`);
        pre.textContent = JSON.stringify(token, null, 2);
        out.appendChild(pre);

        const syncBtn = el(`<button style="margin-top:8px">Sync & settle now</button>`);
        syncBtn.onclick = async () => {
          try {
            const res = await API.syncToken(token);
            S.queueAdd({
              id: token.nonce,
              token,
              status: res.status,
              created_at: Math.floor(Date.now() / 1000),
              label: `Received ${token.amount} from ${token.payer_id}`,
            });
            out.appendChild(banner(res.status === "settled" ? "ok" : "warn",
              `Server: ${res.status}${res.flag_reason ? " (" + res.flag_reason + ")" : ""}`));
          } catch (e) {
            out.appendChild(banner("err", "Sync failed: " + e.message));
          }
        };
        out.appendChild(syncBtn);
      } catch (e) {
        out.appendChild(banner("err", e.message));
      }
    });
  }

  // -------- queue --------
  async function renderQueue(body) {
    const card = el(`<div class="card"><h1>Sync queue</h1><div id="q"></div></div>`);
    body.appendChild(card);
    const q = card.querySelector("#q");
    const items = S.queue();
    if (!items.length) { q.innerHTML = `<p class="muted">No local tokens yet.</p>`; return; }

    const list = el(`<ul class="plain"></ul>`);
    q.appendChild(list);

    for (const item of items) {
      const li = el(html`
        <li>
          <div style="display:flex;justify-content:space-between;gap:8px">
            <span>${item.label || item.id}</span>
            <span class="badge ${item.status}">${item.status}</span>
          </div>
          <div class="muted mono" style="margin-top:4px">${item.id}</div>
        </li>
      `);
      const sync = el(`<button class="ghost" style="margin-top:6px">Sync</button>`);
      sync.onclick = async () => {
        try {
          const res = await API.syncToken(item.token);
          S.queueUpdate(item.id, { status: res.status });
          renderQueue(body.querySelector("#tab-body"));
        } catch (e) {
          alert("Sync failed: " + e.message);
        }
      };
      if (item.status === "pending") li.appendChild(sync);
      list.appendChild(li);
    }
  }

  // ----------------------------------------------------------------
  // analyst
  // ----------------------------------------------------------------
  async function renderAnalyst() {
    app.innerHTML = "";
    const card = el(`<div class="card"><h1>Analyst</h1><div id="a">Loading…</div></div>`);
    app.appendChild(card);
    const a = card.querySelector("#a");
    try {
      const data = await API.analystQueue();
      a.innerHTML = "";

      const flagged = el(html`
        <h3>Flag queue (${data.flagged.length})</h3>
        <ul class="plain" id="flags"></ul>
      `);
      a.appendChild(flagged);
      const flagsUl = flagged.querySelector("#flags");
      if (!data.flagged.length) flagsUl.innerHTML = `<li class="muted">None</li>`;
      for (const f of data.flagged) {
        flagsUl.appendChild(el(html`
          <li>
            <div><b>${f.payer_id}</b> → ${f.payee_id} · ${fmtAmount(f.amount)}</div>
            <div class="muted mono">counter=${f.counter} · ${f.flag_reason || ""}</div>
          </li>
        `));
      }

      const disputes = el(html`
        <h3 style="margin-top:16px">Disputes (${data.disputes.length})</h3>
        <ul class="plain" id="disp"></ul>
      `);
      a.appendChild(disputes);
      const dispUl = disputes.querySelector("#disp");
      if (!data.disputes.length) dispUl.innerHTML = `<li class="muted">None</li>`;
      for (const d of data.disputes) {
        const li = el(html`
          <li>
            <div style="display:flex;justify-content:space-between">
              <span><b>${d.id}</b></span>
              <span class="badge ${d.status}">${d.status}</span>
            </div>
            <div class="muted" style="margin-top:4px">${d.reason}</div>
            <div class="muted mono" style="margin-top:4px">token=${d.token_id}</div>
          </li>
        `);
        if (d.status !== "decided") {
          const btn = el(`<button class="ghost" style="margin-top:6px">Record decision</button>`);
          btn.onclick = async () => {
            const decision = prompt("Decision (e.g. upheld / rejected / escalated):");
            if (!decision) return;
            try {
              await API.analystDecision(d.id, decision);
              renderAnalyst();
            } catch (e) { alert(e.message); }
          };
          li.appendChild(btn);
        }
        dispUl.appendChild(li);
      }
    } catch (e) {
      a.innerHTML = "";
      a.appendChild(banner("err", e.message));
    }
  }

  // ----------------------------------------------------------------
  // boot
  // ----------------------------------------------------------------
  (async () => {
    await cacheBankKey();
    route();
  })();
})();
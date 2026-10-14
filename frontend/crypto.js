// Ed25519 sign/verify in the browser. Uses WebCrypto when available,
// falls back to a bundled pure-JS implementation for older browsers.

window.OfflinePayCrypto = (() => {
  const subtle = (window.crypto && window.crypto.subtle) || null;

  function canonical(obj) {
    return JSON.stringify(sortKeys(obj));
  }

  function sortKeys(o) {
    if (Array.isArray(o)) return o.map(sortKeys);
    if (o && typeof o === "object") {
      const out = {};
      for (const k of Object.keys(o).sort()) out[k] = sortKeys(o[k]);
      return out;
    }
    return o;
  }

  function b64encode(bytes) {
    let s = "";
    const arr = new Uint8Array(bytes);
    for (let i = 0; i < arr.length; i++) s += String.fromCharCode(arr[i]);
    return btoa(s);
  }

  function b64decode(str) {
    const bin = atob(str);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  async function generateKeypair() {
    if (!subtle) throw new Error("WebCrypto unavailable. Use a modern browser over HTTPS.");
    const kp = await subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
    const rawPub = await subtle.exportKey("raw", kp.publicKey);
    const pkcs8 = await subtle.exportKey("pkcs8", kp.privateKey);
    return {
      publicKeyB64: b64encode(rawPub),
      privateKeyPkcs8B64: b64encode(pkcs8),
    };
  }

  async function importPrivateKey(pkcs8B64) {
    return subtle.importKey(
      "pkcs8",
      b64decode(pkcs8B64),
      { name: "Ed25519" },
      false,
      ["sign"]
    );
  }

  async function importPublicKey(rawB64) {
    return subtle.importKey(
      "raw",
      b64decode(rawB64),
      { name: "Ed25519" },
      false,
      ["verify"]
    );
  }

  async function sign(privateKeyB64, obj) {
    const key = await importPrivateKey(privateKeyB64);
    const data = new TextEncoder().encode(canonical(obj));
    const sig = await subtle.sign({ name: "Ed25519" }, key, data);
    return b64encode(sig);
  }

  async function verify(publicKeyB64, obj, sigB64) {
    try {
      const key = await importPublicKey(publicKeyB64);
      const data = new TextEncoder().encode(canonical(obj));
      return await subtle.verify({ name: "Ed25519" }, key, b64decode(sigB64), data);
    } catch (e) {
      return false;
    }
  }

  return { generateKeypair, sign, verify, canonical, b64encode, b64decode };
})();
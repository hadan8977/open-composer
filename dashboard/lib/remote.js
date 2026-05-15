import crypto from "node:crypto";

const COOKIE_NAME = "oc_dashboard_session";
const DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;
const MAX_BODY_BYTES = 1_000_000;

export function jsonResponse(res, status, payload, headers = {}) {
  const body = JSON.stringify(payload);
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  for (const [key, value] of Object.entries(headers)) {
    res.setHeader(key, value);
  }
  res.end(body);
}

export async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      throw new Error("request body is too large");
    }
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw.trim() ? JSON.parse(raw) : {};
}

export function verifyPassword(password) {
  const configured = process.env.OC_DASHBOARD_PASSWORD_HASH || "";
  if (!configured) {
    return false;
  }
  if (configured.startsWith("sha256:")) {
    const expected = configured.slice("sha256:".length);
    const actual = crypto.createHash("sha256").update(password, "utf8").digest("hex");
    return timingSafeEqual(actual, expected);
  }
  if (configured.startsWith("pbkdf2-sha256:")) {
    const [, iterationsText, salt, expected] = configured.split(":");
    const iterations = Number.parseInt(iterationsText, 10);
    if (!iterations || !salt || !expected) {
      return false;
    }
    const actual = crypto.pbkdf2Sync(password, salt, iterations, 32, "sha256").toString("hex");
    return timingSafeEqual(actual, expected);
  }
  return false;
}

export function createSessionCookie(owner) {
  const ttl = sessionTtlSeconds();
  const csrf = crypto.randomBytes(24).toString("base64url");
  const payload = {
    owner,
    csrf,
    exp: Math.floor(Date.now() / 1000) + ttl,
  };
  const encoded = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  const signature = sessionSignature(encoded);
  return {
    csrf,
    header: `${COOKIE_NAME}=${encoded}.${signature}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${ttl}`,
  };
}

export function clearSessionCookie() {
  return `${COOKIE_NAME}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`;
}

export function requireSession(req, res, { csrf = false } = {}) {
  const session = readSession(req);
  if (!session) {
    jsonResponse(res, 401, { error: "Dashboard login required.", remote: true });
    return null;
  }
  if (csrf) {
    const provided = String(req.headers["x-oc-csrf"] || "");
    if (!timingSafeEqual(provided, session.csrf)) {
      jsonResponse(res, 403, { error: "CSRF token rejected.", remote: true });
      return null;
    }
  }
  return session;
}

export function readSession(req) {
  const cookies = parseCookies(req.headers.cookie || "");
  const token = cookies[COOKIE_NAME];
  if (!token || !token.includes(".")) {
    return null;
  }
  const [encoded, signature] = token.split(".", 2);
  if (!timingSafeEqual(signature, sessionSignature(encoded))) {
    return null;
  }
  try {
    const payload = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
    if (!payload.exp || payload.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

export async function proxyRemote(req, res, remotePath, { csrf = false } = {}) {
  const session = requireSession(req, res, { csrf });
  if (!session) {
    return;
  }
  const bodyObject = req.method === "GET" ? null : await readJson(req);
  const body = bodyObject ? Buffer.from(JSON.stringify(bodyObject), "utf8") : Buffer.alloc(0);
  const response = await fetch(`${remoteBaseUrl()}${remotePath}`, {
    method: req.method,
    headers: {
      "Content-Type": "application/json",
      ...signedHeaders(req.method, remotePath, body, session.owner),
    },
    body: body.length ? body : undefined,
  });
  const text = await response.text();
  res.statusCode = response.status;
  res.setHeader("Content-Type", response.headers.get("content-type") || "application/json");
  res.setHeader("Cache-Control", "no-store");
  res.end(text);
}

function signedHeaders(method, path, body, actor) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = crypto.randomBytes(24).toString("base64url");
  const bodyHash = crypto.createHash("sha256").update(body).digest("hex");
  const canonical = [method.toUpperCase(), path, timestamp, nonce, actor, bodyHash].join("\n");
  const signature = crypto
    .createHmac("sha256", process.env.OC_REMOTE_SHARED_SECRET || "")
    .update(canonical)
    .digest("hex");
  return {
    "X-OC-Timestamp": timestamp,
    "X-OC-Nonce": nonce,
    "X-OC-Actor": actor,
    "X-OC-Body-SHA256": bodyHash,
    "X-OC-Signature": signature,
  };
}

function remoteBaseUrl() {
  const value = process.env.OC_REMOTE_BASE_URL || "";
  if (!value) {
    throw new Error("OC_REMOTE_BASE_URL is not configured");
  }
  return value.replace(/\/$/, "");
}

function sessionTtlSeconds() {
  const configured = Number.parseInt(process.env.OC_DASHBOARD_SESSION_TTL_SECONDS || "", 10);
  return configured > 0 ? configured : DEFAULT_SESSION_TTL_SECONDS;
}

function sessionSignature(encodedPayload) {
  return crypto
    .createHmac("sha256", process.env.OC_DASHBOARD_SESSION_SECRET || "")
    .update(encodedPayload)
    .digest("base64url");
}

function parseCookies(header) {
  const result = {};
  for (const part of header.split(";")) {
    const [rawKey, ...rawValue] = part.trim().split("=");
    if (rawKey) {
      result[rawKey] = rawValue.join("=");
    }
  }
  return result;
}

function timingSafeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left));
  const rightBuffer = Buffer.from(String(right));
  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }
  return crypto.timingSafeEqual(leftBuffer, rightBuffer);
}

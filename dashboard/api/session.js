import { jsonResponse, readSession } from "../lib/remote.js";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    jsonResponse(res, 405, { error: "Method not allowed.", remote: true });
    return;
  }
  const session = readSession(req);
  jsonResponse(res, 200, {
    authenticated: Boolean(session),
    remote: true,
    owner: session?.owner || null,
    csrf: session?.csrf || null,
  });
}

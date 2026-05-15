import { jsonResponse, proxyRemote } from "../lib/remote.js";

export default async function handler(req, res) {
  if (req.method === "GET") {
    await proxyRemote(req, res, "/agent-requests");
    return;
  }
  if (req.method === "POST") {
    await proxyRemote(req, res, "/agent-requests", { csrf: true });
    return;
  }
  jsonResponse(res, 405, { error: "Method not allowed.", remote: true });
}

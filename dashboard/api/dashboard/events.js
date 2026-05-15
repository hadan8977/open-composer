import { jsonResponse, proxyRemote } from "../../lib/remote.js";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    jsonResponse(res, 405, { error: "Method not allowed.", remote: true });
    return;
  }
  await proxyRemote(req, res, "/dashboard/events");
}

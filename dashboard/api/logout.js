import { clearSessionCookie, jsonResponse } from "../lib/remote.js";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    jsonResponse(res, 405, { error: "Method not allowed.", remote: true });
    return;
  }
  jsonResponse(
    res,
    200,
    { authenticated: false, remote: true },
    { "Set-Cookie": clearSessionCookie() },
  );
}

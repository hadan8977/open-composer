import { createSessionCookie, jsonResponse, readJson, verifyPassword } from "../lib/remote.js";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    jsonResponse(res, 405, { error: "Method not allowed.", remote: true });
    return;
  }
  try {
    const payload = await readJson(req);
    const password = String(payload.password || "");
    if (!verifyPassword(password)) {
      jsonResponse(res, 401, { error: "Invalid dashboard password.", remote: true });
      return;
    }
    const owner = process.env.OC_DASHBOARD_OWNER || "owner";
    const session = createSessionCookie(owner);
    jsonResponse(
      res,
      200,
      { authenticated: true, remote: true, owner, csrf: session.csrf },
      { "Set-Cookie": session.header },
    );
  } catch (error) {
    jsonResponse(res, 400, { error: String(error.message || error), remote: true });
  }
}

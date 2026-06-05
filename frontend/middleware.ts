/**
 * Next.js Edge Middleware — HTTP Basic Auth gate for the web UI.
 *
 * Set BASIC_AUTH_USER + BASIC_AUTH_PASSWORD to enable.
 * If either env var is unset, all requests pass through (local dev).
 *
 * The frontend JS also includes the same credentials in every API call
 * to the backend via NEXT_PUBLIC_BASIC_AUTH (see lib/config.ts).
 */
import { NextRequest, NextResponse } from "next/server";

const USER = process.env.BASIC_AUTH_USER ?? "";
const PASS = process.env.BASIC_AUTH_PASSWORD ?? "";
const ENABLED = Boolean(USER && PASS);

export function middleware(req: NextRequest) {
  if (!ENABLED) return NextResponse.next();

  const auth = req.headers.get("authorization") ?? "";

  if (auth.toLowerCase().startsWith("basic ")) {
    const decoded = atob(auth.slice(6));
    const colon = decoded.indexOf(":");
    if (colon !== -1) {
      const u = decoded.slice(0, colon);
      const p = decoded.slice(colon + 1);
      if (u === USER && p === PASS) return NextResponse.next();
    }
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": `Basic realm="Context Graph"` },
  });
}

export const config = {
  // Protect all pages — skip Next.js internals and static files
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

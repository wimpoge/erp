import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Optimistic check only: no session cookie means straight to the login page. The POS API
// still validates the session on every request.
export function proxy(request: NextRequest) {
  const loggedIn = request.cookies.has("pos_session");
  const { pathname, search } = request.nextUrl;

  if (!loggedIn && pathname !== "/login") {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Pages only: not the API, Next.js internals or static files.
  matcher: ["/((?!api|_next|favicon.ico|.*\\.).*)"],
};

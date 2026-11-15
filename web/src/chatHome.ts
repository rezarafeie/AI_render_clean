/** Where the Home button of a chat's top bar leads: a chat goes home to its own app. */
export function chatHomePath(pathname: string): "/studio" | "/insta" | null {
  if (/^\/studio\/[^/]+/.test(pathname)) return "/studio";
  if (/^\/insta\/chat\/[^/]+/.test(pathname)) return "/insta";
  return null;
}

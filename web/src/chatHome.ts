/** Where the Home button of a chat's top bar leads: a chat goes home to its own app. */
export function chatHomePath(pathname: string): "/studio" | "/hermes" | null {
  if (/^\/studio\/[^/]+/.test(pathname)) return "/studio";
  if (/^\/hermes\/chat\/[^/]+/.test(pathname)) return "/hermes";
  return null;
}

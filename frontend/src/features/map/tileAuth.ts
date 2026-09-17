export interface MapRequest {
  url: string;
  headers?: Record<string, string>;
}

function isRibeiraDerivedProductTile(url: URL, apiUrl: URL): boolean {
  const segments = url.pathname.split("/").filter(Boolean);
  return (
    url.origin === apiUrl.origin &&
    segments.length === 9 &&
    segments[0] === "v1" &&
    segments[1] === "tenants" &&
    Boolean(segments[2]) &&
    segments[3] === "derived-products" &&
    Boolean(segments[4]) &&
    segments[5] === "tiles" &&
    segments.slice(6).every(Boolean)
  );
}

/** Adds the browser session only to the exact protected Ribeira XYZ route. */
export function transformMapRequest(
  url: string,
  apiBaseUrl: string,
  token: string,
): MapRequest {
  const requestUrl = new URL(url, window.location.origin);
  const apiUrl = new URL(apiBaseUrl, window.location.origin);
  if (!token || !isRibeiraDerivedProductTile(requestUrl, apiUrl)) {
    return { url };
  }
  return { url, headers: { Authorization: `Bearer ${token}` } };
}

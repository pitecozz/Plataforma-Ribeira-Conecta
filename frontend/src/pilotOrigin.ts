type PilotOriginEnvironment = {
  VITE_RIBEIRA_API_URL?: string;
  VITE_RIBEIRA_OIDC_REDIRECT_URI?: string;
  VITE_RIBEIRA_PUBLIC_ORIGIN?: string;
};

export function configuredPublicOrigin(value: string | undefined): string | undefined {
  if (!value) return undefined;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("public origin must be a URL");
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error("public origin must be an HTTPS origin without a path");
  }
  return parsed.origin;
}

export function apiUrlFromEnvironment(environment: PilotOriginEnvironment): string | undefined {
  const origin = configuredPublicOrigin(environment.VITE_RIBEIRA_PUBLIC_ORIGIN);
  return environment.VITE_RIBEIRA_API_URL ?? (origin ? `${origin}/api` : undefined);
}

export function redirectUriFromEnvironment(environment: PilotOriginEnvironment): string | undefined {
  const origin = configuredPublicOrigin(environment.VITE_RIBEIRA_PUBLIC_ORIGIN);
  return environment.VITE_RIBEIRA_OIDC_REDIRECT_URI ?? (origin ? `${origin}/` : undefined);
}

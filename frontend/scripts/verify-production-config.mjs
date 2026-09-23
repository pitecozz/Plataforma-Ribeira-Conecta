const required = [
  "VITE_RIBEIRA_PUBLIC_ORIGIN",
  "VITE_RIBEIRA_TENANT_ID",
  "VITE_RIBEIRA_AUTH_MODE",
  "VITE_RIBEIRA_OIDC_AUDIENCE",
  "VITE_RIBEIRA_OIDC_AUTHORIZATION_ENDPOINT",
  "VITE_RIBEIRA_OIDC_TOKEN_ENDPOINT",
  "VITE_RIBEIRA_OIDC_CLIENT_ID",
];

const missing = required.filter((name) => !process.env[name]?.trim());
for (const name of required) console.log(`${name}=${missing.includes(name) ? "MISSING" : "PRESENT"}`);
if (missing.length) process.exitCode = 1;

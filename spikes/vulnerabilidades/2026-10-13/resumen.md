# Dependencias: el resumen para el triaje (2026-10-13)

Generado por `spikes/vulnerabilidades_resumen.py` a partir de los JSON de esta carpeta;
las condiciones, en `condiciones.txt`. La casilla se rellena a mano: **arreglado**,
**aceptado** (con su motivo) o **no aplicable**.

## Python (pip-audit, OSV)

La gravedad es la de GitHub, del alias GHSA de cada aviso (`gravedades.json`).

- **lockfile**: 48 avisos en 12 paquetes (93 entradas en crudo)
- **fuera del lockfile**: 0 avisos en 0 paquetes (0 entradas en crudo)
- **imagen**: 56 avisos en 14 paquetes (109 entradas en crudo)
- por gravedad, todas las pasadas juntas: critical 3, high 17, moderate 28, low 8

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Casilla |
|---|---|---|---|---|---|---|---|---|
| critical | anyio | 4.12.1 | PYSEC-2026-4025 | CVE-2026-63374, GHSA-82r6-8w77-94w6 | AnyIO: TLSStream IDNA 2003 host name encoding enables potential TLS certificate spoofing | 4.14.2 | imagen, lockfile |  |
| critical | fastmcp | 3.1.0 | PYSEC-2026-338 | CVE-2026-32871, GHSA-vv7q-7jx5-f767 | FastMCP OpenAPI Provider has an SSRF & Path Traversal Vulnerability | 3.2.0 | imagen, lockfile |  |
| critical | pyjwt | 2.11.0 | PYSEC-2026-4145 | CVE-2026-102268, GHSA-ffc3-869f-jxw9 | PyJWT: Asymmetric-PEM detection bypass: whitespace/line-ending-mutated public keys skip t… | 2.14.0 | imagen, lockfile |  |
| high | cryptography | 46.0.5 | GHSA-537c-gmf6-5ccf | — | Vulnerable OpenSSL included in cryptography wheels | 48.0.1 | imagen, lockfile |  |
| high | cryptography | 46.0.5 | PYSEC-2026-3552 | CVE-2026-69247, GHSA-g6cj-pr64-35w5 | cryptography: PKCS#7 EnvelopedData decryption exposes a Bleichenbacher oracle through dis… | 50.0.0 | imagen, lockfile |  |
| high | cryptography | 46.0.5 | PYSEC-2026-3553 | CVE-2026-69249, GHSA-jwv3-5hgf-82ww | python-cryptography: Duplicate self-signed intermediates can cause exponential path-build… | 49.0.0 | imagen, lockfile |  |
| high | fastmcp | 3.1.0 | PYSEC-2026-2476 | CVE-2026-27124, GHSA-rww4-4w9c-7733 | FastMCP: Missing Consent Verification in OAuth Proxy Callback Facilitates Confused Deputy… | 3.2.0 | imagen, lockfile |  |
| high | fsspec | 2026.4.0 | CVE-2026-104851 | GHSA-27vj-qcqg-25rc | fsspec: Server-Side Template Injection in ReferenceFileSystem leads to Remote Code Execut… | 2026.6.0 | imagen, lockfile |  |
| high | mcp | 1.26.0 | PYSEC-2026-3481 | CVE-2026-52870, GHSA-hvrp-rf83-w775 | MCP Python SDK: Experimental task handlers allow any client to access and cancel other cl… | 1.27.2 | imagen, lockfile |  |
| high | mcp | 1.26.0 | PYSEC-2026-3482 | CVE-2026-52869, GHSA-jpw9-pfvf-9f58 | MCP Python SDK: HTTP transports serve session requests without verifying the authenticate… | 1.27.2 | imagen, lockfile |  |
| high | mcp | 1.26.0 | PYSEC-2026-3483 | CVE-2026-59950, GHSA-vj7q-gjh5-988w | MCP Python SDK: WebSocket server transport does not support Host/Origin validation | 1.28.1 | imagen, lockfile |  |
| high | pyjwt | 2.11.0 | PYSEC-2026-120 | CVE-2026-32597, GHSA-752w-5fwx-jx9f | PyJWT accepts unknown `crit` header extensions | 2.12.0 | imagen, lockfile |  |
| high | pyjwt | 2.11.0 | PYSEC-2026-179 | CVE-2026-48526, GHSA-xgmm-8j9v-c9wx | PyJWT: Public-key JWK accepted as HMAC secret enables forged HS256 tokens when mixed fami… | 2.13.0 | imagen, lockfile |  |
| high | pyjwt | 2.11.0 | PYSEC-2026-4144 | CVE-2026-102267, GHSA-9v7f-9g4p-ffgj | PyJWT: PyJWKClient follows redirects when fetching JWKS | 2.14.0 | imagen, lockfile |  |
| high | pyjwt | 2.11.0 | PYSEC-2026-4149 | CVE-2026-102271, GHSA-p4g4-x82p-q773 | PyJWT: Public keys in DER form are accepted as HMAC secrets, bypassing the CVE-2022-29217… | 2.14.0 | imagen, lockfile |  |
| high | python-multipart | 0.0.22 | PYSEC-2026-3036 | CVE-2026-53539, GHSA-5rvq-cxj2-64vf | python-multipart: Quadratic-time querystring parsing with semicolon separators causes CPU… | 0.0.30 | imagen, lockfile |  |
| high | python-multipart | 0.0.22 | PYSEC-2026-3039 | CVE-2026-42561, GHSA-pp6c-gr5w-3c5g | python-multipart has Denial of Service via unbounded multipart part headers | 0.0.27 | imagen, lockfile |  |
| high | setuptools | 78.1.0 | PYSEC-2025-49 | BIT-setuptools-2025-47273, CVE-2025-47273, GHSA-5rjg-fvgr-3xxf | setuptools has a path traversal vulnerability in PackageIndex.download that leads to Arbi… | 78.1.1 | imagen |  |
| high | starlette | 0.52.1 | PYSEC-2026-2281 | CVE-2026-48818, GHSA-wqp7-x3pw-xc5r | Starlette: SSRF and NTLM credential theft via UNC paths in StaticFiles on Windows | 1.1.0 | imagen, lockfile |  |
| high | starlette | 0.52.1 | PYSEC-2026-249 | CVE-2026-54283, GHSA-82w8-qh3p-5jfq | Starlette: request.form() limits silently ignored for application/x-www-form-urlencoded e… | 1.3.1 | imagen, lockfile |  |
| moderate | anyio | 4.12.1 | PYSEC-2026-4024 | CVE-2026-64847, GHSA-5p39-cfhj-2xmp | AnyIO process-pool workers can block indefinitely on undrained stderr | 4.14.2 | imagen, lockfile |  |
| moderate | authlib | 1.6.9 | PYSEC-2026-188 | CVE-2026-44681, GHSA-r95x-qfjj-fjj2 | Authlib OIDC Implicit/Hybrid Authorization Vulnerable to Open Redirect | 1.6.12 | imagen, lockfile |  |
| moderate | authlib | 1.6.9 | PYSEC-2026-2119 | CVE-2026-41479, GHSA-w8p2-r796-3vmq | Authlib OAuth 2.0 has Open Redirect in Authorization API that allows attacker-controlled … | 1.7.1 | imagen, lockfile |  |
| moderate | authlib | 1.6.9 | PYSEC-2026-25 | CVE-2026-41425, GHSA-jj8c-mmj3-mmgv | Authlib: Cross-site request forging when using cache | 1.6.11 | imagen, lockfile |  |
| moderate | cryptography | 46.0.5 | PYSEC-2026-3554 | CVE-2026-69248, GHSA-m2h6-j472-rp4c | python-cryptography verifier accepts wildcard DNS names allowing escape from permittedSub… | 49.0.0 | imagen, lockfile |  |
| moderate | cryptography | 46.0.5 | PYSEC-2026-36 | CVE-2026-39892, GHSA-p423-j2cm-9vmq | Cryptography vulnerable to buffer overflow if non-contiguous buffers were passed to APIs | 46.0.7 | imagen, lockfile |  |
| moderate | fastmcp | 3.1.0 | PYSEC-2026-2475 | CVE-2025-64340, GHSA-m8x7-r2rg-vh5g | FastMCP has a Command Injection vulnerability - Gemini CLI | 3.2.0 | imagen, lockfile |  |
| moderate | idna | 3.11 | PYSEC-2026-215 | CVE-2026-45409, GHSA-65pc-fj4g-8rjx | Internationalized Domain Names in Applications (IDNA): Specially crafted inputs to idna.e… | 3.15 | imagen, lockfile |  |
| moderate | pip | 25.0.1 | PYSEC-2026-1795 | CVE-2025-8869, GHSA-4xh5-x5gv-qwph | pip's fallback tar extraction doesn't check symbolic links point to extraction directory | 25.3 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-196 | CVE-2026-8643, GHSA-wf93-45jw-7689 | pip: Path traversal in console_scripts/gui_scripts entry point names allows installing sc… | 26.1.2 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-2875 | CVE-2026-3219, GHSA-58qw-9mgm-455v | pip has an interpretation conflict due to handling both concatenated tar and ZIP files as… | 26.1 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-2876 | CVE-2026-6357, GHSA-jp4c-xjxw-mgf9 | pip Vulnerable to Inclusion of Functionality from Untrusted Control Sphere | 26.1 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-3721 | CVE-2026-13346, GHSA-qwm4-qh6w-59xr | pip would incorrectly handle doubly-encoded package URLs from indexes | 26.2.0 | imagen |  |
| moderate | pydantic-settings | 2.13.1 | CVE-2026-58203 | GHSA-4xgf-cpjx-pc3j | pydantic-settings: NestedSecretsSettingsSource follows symlinks outside secrets_dir, enab… | 2.14.2 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-175 | CVE-2026-48522, GHSA-993g-76c3-p5m4 | PyJWKClient: missing scheme allowlist enables CVE-2024-21643-class SSRF + token forgery v… | 2.13.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-176 | CVE-2026-48523, GHSA-jq35-7prp-9v3f | PyJWT: Algorithm allow-list bypass when decoding with `PyJWK` / `PyJWKClient` keys | 2.13.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-178 | CVE-2026-48525, GHSA-w7vc-732c-9m39 | PyJWT: Unauthenticated DoS via unbounded Base64URL decoding of unused payload segment in … | 2.13.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-4140 | CVE-2026-101917, GHSA-2gx3-rcp4-g85q | PyJWT: PyJWKClient still amplifies unauthenticated JWKS fetches on unknown kid values (in… | 2.14.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-4141 | CVE-2026-101918, GHSA-42vr-xj54-vc7v | PyJWT: Unauthenticated RecursionError DoS in pre-verification payload parse (PyJWKClient.… | 2.15.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-4146 | CVE-2026-103001, GHSA-gvp8-978c-rx2q | PyJWT.decode() reintroduces options-dict mutation, enabling silent claim-verification byp… | — | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-4147 | CVE-2026-102269, GHSA-hxm8-2xgr-2p9m | PyJWT: Non-canonical signature segments enable raw-token revocation bypass | 2.14.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-4148 | CVE-2026-102270, GHSA-jwrc-g2q2-pq5p | PyJWT: ReDoS vulnerability when calling the `is_pem_format` function. | 2.14.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-4152 | CVE-2026-102274, GHSA-w6j9-cwv2-h6wq | PyJWT: Malformed RSA JWK aborts parsing of an entire JWK Set | 2.14.0 | imagen, lockfile |  |
| moderate | pyjwt | 2.11.0 | PYSEC-2026-4183 | CVE-2026-102275, GHSA-x33g-cr3x-6449 | PyJWT accepts inconsistent OKP x/d JWKs, causing public/private key identity confusion | 2.15.0 | imagen, lockfile |  |
| moderate | python-multipart | 0.0.22 | PYSEC-2026-3038 | CVE-2026-40347, GHSA-mj87-hwqh-73pj | python-multipart affected by Denial of Service via large multipart preamble or epilogue d… | 0.0.26 | imagen, lockfile |  |
| moderate | setuptools | 78.1.0 | PYSEC-2026-3447 | BIT-setuptools-2026-59890, CVE-2026-59890, GHSA-h35f-9h28-mq5c | setuptools: MANIFEST.in exclusion bypass in sdist via Unicode normalization collision (NF… | 83.0.0 | imagen |  |
| moderate | starlette | 0.52.1 | PYSEC-2026-161 | CVE-2026-48710, GHSA-86qp-5c8j-p5mr, X41-2026-002 | Starlette has missing Host header validation that poisons request.url.path, bypassing pat… | 1.0.1 | imagen, lockfile |  |
| moderate | starlette | 0.52.1 | PYSEC-2026-2280 | CVE-2026-48817, GHSA-x746-7m8f-x49c | Starlette: Arbitrary HTTP method dispatched to `HTTPEndpoint` attributes via `getattr` | 1.1.0 | imagen, lockfile |  |
| low | cryptography | 46.0.5 | PYSEC-2026-35 | CVE-2026-34073, GHSA-m959-cc7f-wv43 | cryptography has incomplete DNS name constraint enforcement on peer names | 46.0.6 | imagen, lockfile |  |
| low | pip | 25.0.1 | PYSEC-2026-1796 | CVE-2026-1703, GHSA-6vgw-5pg2-w6jp | pip Path Traversal vulnerability | 26.0 | imagen |  |
| low | pygments | 2.19.2 | PYSEC-2026-2987 | CVE-2026-4539, GHSA-5239-wwwm-4pmq | Pygments has Regular Expression Denial of Service (ReDoS) due to Inefficient Regex for GU… | 2.20.0 | imagen, lockfile |  |
| low | pyjwt | 2.11.0 | PYSEC-2026-177 | CVE-2026-48524, GHSA-fhv5-28vv-h8m8 | PyJWKClient unbounded JWKS endpoint requests via attacker-controlled kid values (DoS) | 2.13.0 | imagen, lockfile |  |
| low | python-multipart | 0.0.22 | PYSEC-2026-3037 | CVE-2026-53538, GHSA-6jv3-5f52-599m | python-multipart: Semicolon treated as querystring field separator enables parameter smug… | 0.0.30 | imagen, lockfile |  |
| low | python-multipart | 0.0.22 | PYSEC-2026-3040 | CVE-2026-53540, GHSA-v9pg-7xvm-68hf | python-multipart: Negative Content-Length in parse_form buffers the entire body in memory | 0.0.31 | imagen, lockfile |  |
| low | python-multipart | 0.0.22 | PYSEC-2026-3041 | CVE-2026-53537, GHSA-vffw-93wf-4j4q | python-multipart: Content-Disposition parameter smuggling via RFC 2231/5987 extended para… | 0.0.30 | imagen, lockfile |  |
| low | starlette | 0.52.1 | PYSEC-2026-248 | CVE-2026-54282, GHSA-jp82-jpqv-5vv3 | Starlette: Unvalidated request path concatenated into authority poisons request.url.hostn… | 1.3.0 | imagen, lockfile |  |

## npm (npm audit)

Versiones instaladas de `frontend/package-lock.json`, blob `2b29929a23631f3af2d0117a8cbbe9239673f5ec`.

- **todo**: 25 avisos en 11 paquetes (28 entradas en crudo)
- **servido**: 1 avisos en 1 paquetes (1 entradas en crudo)
- por gravedad, todas las pasadas juntas: critical 2, high 10, moderate 10, low 3

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Casilla |
|---|---|---|---|---|---|---|---|---|
| critical | piscina | 5.2.0 | GHSA-67c8-pqhq-4rmx | — | piscina: Prototype-pollution gadget in ThreadPool.options allows RCE via execArgv / loadB… | sí, en el rango | todo |  |
| critical | proxy-addr | 2.0.7 | GHSA-jqcg-44mw-7w3h | — | proxy-addr vulnerable to IP spoofing via IPv4-mapped IPv6 trust subnet | sí, en el rango | todo |  |
| high | @angular/router | 22.1.4 | GHSA-ff3f-86qr-9cv3 | — | Angular Server-Side Rendering (SSR): Denial of Service via Numeric URL Matrix Parameters | sí, en el rango | servido, todo |  |
| high | @modelcontextprotocol/sdk | 1.30.0 | GHSA-6qxp-vccf-f47h | — | MCP TypeScript SDK: OAuth client could send credentials to an authorization server chosen… | sí, en el rango | todo |  |
| high | brace-expansion | 2.1.4, 5.0.9 | GHSA-6j4f-fj2g-mc7p | — | brace-expansion: DoS via uncontrolled recursion in parseCommaParts causing stack exhausti… | sí, en el rango | todo |  |
| high | brace-expansion | 2.1.4, 5.0.9 | GHSA-qhr7-859c-m2p7 | — | brace-expansion: DoS via uncontrolled recursion on nested brace groups causing stack exha… | sí, en el rango | todo |  |
| high | fast-uri | 3.1.6 | GHSA-58mr-gqgx-xq4g | — | fast-uri vulnerable to host confusion via an unclosed bracket in the URI authority | sí, en el rango | todo |  |
| high | fast-uri | 3.1.6 | GHSA-qw65-cvwx-89v3 | — | fast-uri vulnerable to authority injection via an unvalidated port in serialize | sí, en el rango | todo |  |
| high | js-yaml | 4.3.1 | GHSA-2883-xcg3-v3hh | — | js-yaml: maxTotalMergeKeys does not limit CPU use for empty merge sources | sí, en el rango | todo |  |
| high | source-map-js | 1.2.1 | GHSA-68fv-2mgg-jv7q | — | source-map-js allows event-loop denial of service through indexed source-map section offs… | sí, en el rango | todo |  |
| high | undici | 7.29.0 | GHSA-rfgv-xxqx-mfg5 | — | undici vulnerable to Denial of Service via unrequested WebSocket subprotocol | sí, en el rango | todo |  |
| high | undici | 7.29.0 | GHSA-w293-vg96-wgc3 | — | undici vulnerable to TLS certificate validation bypass via dropped connect options in Bal… | sí, en el rango | todo |  |
| moderate | brace-expansion | 2.1.4, 5.0.9 | GHSA-q2hr-2g5m-vwhr | — | brace-expansion: Quadratic-time expansion of the `{a},b}` rewrite causes CPU denial of se… | sí, en el rango | todo |  |
| moderate | fast-uri | 3.1.6 | GHSA-hrr3-gc8f-f4qj | — | fast-uri vulnerable to inconsistent host case normalization via percent-encoded octets | sí, en el rango | todo |  |
| moderate | hono | 4.13.5 | GHSA-hxh3-vqpv-xpqv | — | hono/jsx renders plain strings unescaped in boundary components, leading to XSS | sí, en el rango | todo |  |
| moderate | ip-address | 10.7.0 | GHSA-h3mg-xc3c-68pw | — | ip-address: Address6 builds a parse diagnostic proportional to the input with no length b… | sí, en el rango | todo |  |
| moderate | ip-address | 10.7.0 | GHSA-j6r3-76f7-8jcv | — | ip-address: isInSubnet() and isHostInSubnet() compare addresses of different families as … | sí, en el rango | todo |  |
| moderate | undici | 7.29.0 | GHSA-2jfj-6hjv-fm6j | — | undici vulnerable to cross-user cookie disclosure via Set-Cookie caching in shared caches | sí, en el rango | todo |  |
| moderate | undici | 7.29.0 | GHSA-3wwx-pv8p-q78v | — | undici vulnerable to Denial of Service via unhandled error in WebSocket permessage-deflat… | sí, en el rango | todo |  |
| moderate | undici | 7.29.0 | GHSA-3xpg-4rpp-hhhm | — | undici vulnerable to Denial of Service via unbounded decompression of compressed responses | sí, en el rango | todo |  |
| moderate | undici | 7.29.0 | GHSA-pmjh-fq2x-6v4x | — | undici vulnerable to Denial of Service via orphaned RetryHandler response body | sí, en el rango | todo |  |
| moderate | undici | 7.29.0 | GHSA-rx4f-c7p8-82vq | — | undici vulnerable to Denial of Service via WebSocketStream unclean close | sí, en el rango | todo |  |
| low | undici | 7.29.0 | GHSA-2gqq-gqf2-x968 | — | undici vulnerable to response truncation via oversized chunked responses in the dump inte… | sí, en el rango | todo |  |
| low | undici | 7.29.0 | GHSA-8436-99hf-9mmv | — | undici vulnerable to caching and replay of unsafe HTTP method responses | sí, en el rango | todo |  |
| low | undici | 7.29.0 | GHSA-r53p-7pc4-xj5r | — | undici vulnerable to downstream response splitting via retry interceptor | sí, en el rango | todo |  |

Paquetes que sólo heredan el aviso de una dependencia suya (npm los cuenta aparte):

- @angular/build, por piscina
- @angular/cli, por @modelcontextprotocol/sdk
- @redocly/openapi-core, por js-yaml

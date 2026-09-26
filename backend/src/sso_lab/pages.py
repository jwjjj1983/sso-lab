"""Tiny server-rendered pages for the protocol actors (IdP screens, RP landing pages).

The playground UI itself is the React SPA; these pages are what the login popup shows.
"""

import html
import json
import secrets

from starlette.responses import HTMLResponse

_STYLE = """
:root { color-scheme: light dark; --fg:#1b1f24; --bg:#f7f7f5; --card:#fff; --muted:#5b6470;
        --accent:#3553d6; --border:#dfe1e5; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8eaed; --bg:#15171a; --card:#1e2125; --muted:#9aa3ad; --accent:#8ea2ff;
          --border:#33373d; }
}
* { box-sizing: border-box; }
body { margin:0; font:16px/1.5 system-ui, sans-serif; color:var(--fg); background:var(--bg);
       min-height:100vh; display:grid; place-items:center; padding:16px; }
main { width:100%; max-width:420px; background:var(--card); border:1px solid var(--border);
       border-radius:12px; padding:24px; }
.badge { display:inline-block; font-size:12px; font-weight:600; letter-spacing:.04em;
         text-transform:uppercase; color:var(--accent); margin-bottom:8px; }
h1 { font-size:20px; margin:0 0 8px; }
p { color:var(--muted); margin:0 0 12px; }
ul.scopes { margin:0 0 16px; padding-left:20px; color:var(--muted); }
form { display:grid; gap:12px; margin:0 0 16px; }
label { display:grid; gap:4px; font-size:14px; font-weight:600; }
input { font:inherit; padding:8px 10px; border:1px solid var(--border); border-radius:8px;
        background:var(--bg); color:var(--fg); }
button { font:inherit; font-weight:600; padding:9px 12px; border:0; border-radius:8px;
         background:var(--accent); color:#fff; cursor:pointer; }
@media (prefers-color-scheme: dark) { button { color:#0f1320; } }
a.button { display:inline-block; text-decoration:none; font-weight:600; padding:9px 12px;
           border-radius:8px; background:var(--accent); color:#fff; }
.hint { font-size:13px; color:var(--muted); border-top:1px solid var(--border); padding-top:12px; }
.hint div { margin-top:4px; }
.error { color:#cf222e; font-weight:600; }
.ok { color:#1a7f37; font-weight:600; }
code { font-family: ui-monospace, Menlo, monospace; font-size: 0.9em; }
dl { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; font-size:14px; margin:0 0 16px; }
dt { color:var(--muted); }
dd { margin:0; font-weight:600; }
"""


def page(
    *,
    badge: str,
    title: str,
    body_html: str,
    script: str | None = None,
    status_code: int = 200,
    form_action: str | None = None,
) -> HTMLResponse:
    """Render a page. ``body_html`` must already be escaped; ``script`` runs under a CSP nonce.

    ``form_action`` is the one other origin a form on this page may post to (the SAML POST
    binding posts to the app's ACS URL).
    """
    nonce = secrets.token_urlsafe(16)
    script_tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{_STYLE}</style></head>
<body><main><div class="badge">{html.escape(badge)}</div><h1>{html.escape(title)}</h1>
{body_html}</main>{script_tag}</body></html>"""
    response = HTMLResponse(content, status_code=status_code)
    if script or form_action:
        response.headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
            f"base-uri 'none'; form-action 'self' {form_action or ''}; frame-ancestors 'none'"
        )
    return response


def post_message_script(message: dict[str, object], target_origin: str) -> str:
    """Report back to the playground window that opened this popup, then close."""
    payload = json.dumps(message).replace("<", "\\u003c")
    origin = json.dumps(target_origin)
    return (
        f"if (window.opener) {{ window.opener.postMessage({payload}, {origin}); "
        "setTimeout(() => window.close(), 400); }"
    )

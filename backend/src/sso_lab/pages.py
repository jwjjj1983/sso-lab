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
"""


def page(
    *,
    badge: str,
    title: str,
    body_html: str,
    script: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a page. ``body_html`` must already be escaped; ``script`` runs under a CSP nonce."""
    nonce = secrets.token_urlsafe(16)
    script_tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{_STYLE}</style></head>
<body><main><div class="badge">{html.escape(badge)}</div><h1>{html.escape(title)}</h1>
{body_html}</main>{script_tag}</body></html>"""
    response = HTMLResponse(content, status_code=status_code)
    if script:
        response.headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
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

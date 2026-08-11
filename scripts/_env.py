"""
_env.py — Tiny .env.local loader used by scripts/ helpers.

Loads app/.env.local into os.environ if a matching key isn't already set.
No dependency on python-dotenv — this is a 15-line parser.
"""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = ROOT / "app" / ".env.local"


def load(env_file: Path = DEFAULT_ENV_FILE) -> dict[str, str]:
    if not env_file.exists():
        return {}
    parsed: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        parsed[key] = val
        os.environ.setdefault(key, val)
    return parsed


def neon_connect_kwargs(url: str) -> dict:
    """
    Return kwargs for psycopg.connect() that work reliably against Neon
    on Windows.

    Neon routes to individual projects via SNI on the pgTLS handshake.
    Windows builds of libpq occasionally don't emit SNI cleanly and the
    server closes the socket. Passing the endpoint id via the libpq
    `options` parameter is the documented Neon workaround and works
    regardless of TLS layer behaviour.
    """
    from urllib.parse import urlparse

    kwargs: dict = {"sslmode": "require"}
    host = urlparse(url).hostname or ""
    # Endpoint id is everything up to (and not including) `-pooler` or
    # the first `.` — e.g. `ep-example-endpoint-12345` from
    # `ep-example-endpoint-12345-pooler.<region>.aws.neon.tech`.
    head = host.split(".", 1)[0]
    if head.startswith("ep-"):
        endpoint = head.removesuffix("-pooler")
        kwargs["options"] = f"endpoint={endpoint}"
    return kwargs


if __name__ == "__main__":
    loaded = load()
    print(f"loaded {len(loaded)} keys from {DEFAULT_ENV_FILE}")
    for k in loaded:
        v = os.environ[k]
        # Redact secrets by default
        red = v[:8] + "…" if len(v) > 12 else "***"
        print(f"  {k} = {red}")

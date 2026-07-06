"""Network guard — SSRF protection for user/admin-supplied URLs.

Any URL the system will later FETCH (manual sources, scout leads) must pass
is_safe_url() first. Blocks: non-http(s) schemes, localhost, private and
link-local IP ranges, cloud metadata endpoints, and raw credentials in URLs.

Note: this validates the URL as given. For full DNS-rebinding protection the
fetcher should also validate the resolved address at connection time.
"""

import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "169.254.169.254",            # AWS/GCP/Azure metadata
    "metadata.google.internal",
    "metadata.azure.com",
}


def is_safe_url(url: str) -> tuple[bool, str]:
    """Returns (safe, reason). Only http/https to public hosts pass."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False, "unparseable URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"scheme '{parsed.scheme}' not allowed (http/https only)"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "no hostname"

    if parsed.username or parsed.password:
        return False, "credentials in URL not allowed"

    if host in BLOCKED_HOSTS or host.endswith(".internal") or host.endswith(".local"):
        return False, f"blocked host: {host}"

    # IP-literal hosts: reject anything non-global
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            return False, f"non-public IP: {host}"
    except ValueError:
        pass  # hostname, not an IP literal — fine

    return True, "ok"

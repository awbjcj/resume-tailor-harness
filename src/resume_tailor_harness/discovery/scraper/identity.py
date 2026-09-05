"""Conservative identities: distinct board paths and SPA routes stay distinct."""

from hashlib import sha256
from urllib.parse import unquote_plus, urlsplit, urlunsplit


def normalize_board_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("a public HTTP(S) URL without credentials is required")
    port = parsed.port
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    authority = f"[{host}]" if ":" in host else host
    if port is not None and (parsed.scheme.lower(), port) not in {
        ("http", 80),
        ("https", 443),
    }:
        authority += f":{port}"
    query = []
    for pair in parsed.query.split("&"):
        key = unquote_plus(pair.partition("=")[0]).lower()
        if (
            pair
            and not key.startswith("utm_")
            and key not in {"gclid", "fbclid", "msclkid"}
        ):
            query.append(pair)
    return urlunsplit(
        (
            parsed.scheme.lower(),
            authority,
            parsed.path or "/",
            "&".join(query),
            parsed.fragment,
        )
    )


def board_key(url: str) -> str:
    return sha256(normalize_board_url(url).encode()).hexdigest()


def observed_job_key(
    source_id: str, posting_id: str | None, canonical_url: str | None
) -> str | None:
    identity = f"id:{posting_id.strip()}" if posting_id and posting_id.strip() else None
    if identity is None and canonical_url:
        identity = f"url:{normalize_board_url(canonical_url)}"
    if identity is None:
        return None
    return sha256(f"{source_id}\n{identity}".encode()).hexdigest()

"""DeepSeek's standalone, read-only Search and Fetch APIs.

These are function tools, not Responses ``web_search`` declarations. Credentials
and endpoints are resolved together for every call, including subscription
routes; a gateway must implement the same tool endpoints to support them.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from resume_tailor_harness.config import Settings
from resume_tailor_harness.tenancy.costs import MeteredUsage
from resume_tailor_harness.tenancy.spend import SpendGate
from resume_tailor_harness.tenancy.usage import record_direct_usage


class DeepSeekSearchTools:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    def _request(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        model = f"deepseek-{operation}"
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            for attempt in range(3):
                # Recheck funding on retries too. Never send a gateway credential
                # to the direct provider, or silently fall back to paid API use.
                route = SpendGate(settings=self.settings).open(f"deepseek:{model}")
                if not route.api_key:
                    raise ValueError(
                        "DeepSeek Search and Fetch require a DeepSeek API key"
                    )
                origin = (route.base_url or "https://api.deepseek.com").rstrip("/")
                base = origin if origin.endswith("/v1") else f"{origin}/v1"
                try:
                    response = client.post(
                        f"{base}/tools/{operation}",
                        headers={"Authorization": f"Bearer {route.api_key}"},
                        json=payload,
                    )
                except (httpx.TimeoutException, httpx.TransportError):
                    if attempt == 2:
                        raise
                else:
                    if response.status_code == 200:
                        data = response.json()
                        if not isinstance(data, dict):
                            raise ValueError("Invalid DeepSeek tool response")
                        if operation == "search":
                            results = data.get("results")
                            if not isinstance(results, list):
                                raise ValueError(
                                    "DeepSeek search response is missing results"
                                )
                            billable = bool(results)
                        else:
                            content = data.get("content")
                            if not isinstance(content, str):
                                raise ValueError(
                                    "DeepSeek fetch response is missing content"
                                )
                            billable = bool(content.strip())
                        # Standalone calls cost $0.75 / 1,000 successful requests.
                        # The November 1 grace period applies to server-side tools,
                        # not these standalone endpoints. Empty results cost zero.
                        record_direct_usage(
                            MeteredUsage(
                                provider="deepseek",
                                model=model,
                                tool_units=int(billable),
                            )
                        )
                        return data
                    if (
                        response.status_code not in {408, 429}
                        and response.status_code < 500
                    ):
                        response.raise_for_status()
                        raise ValueError("DeepSeek tool API must return HTTP 200")
                    if attempt == 2:
                        response.raise_for_status()
                time.sleep(0.5 * 2**attempt)
        raise AssertionError("DeepSeek tool retry loop exhausted")

    def web_search(self, query: str, count: int = 5) -> str:
        """Search the web using DeepSeek and return sources with summaries.

        Args:
            query: Search query, 1 to 128 characters; supports site:, lang:,
                after:, before:, exclusions and exact quoted phrases.
            count: Number of results to return, from 1 to 50.
        """
        if not query.strip() or not 1 <= len(query) <= 128:
            raise ValueError("query must contain 1 to 128 characters and not be blank")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= 50
        ):
            raise ValueError("count must be an integer between 1 and 50")
        return json.dumps(
            self._request(
                "search", {"query": query, "count": count, "need_content": False}
            ),
            ensure_ascii=False,
        )

    def fetch_web(self, url: str) -> str:
        """Fetch a public web page through DeepSeek and return its Markdown.

        Args:
            url: HTTP or HTTPS page URL, without credentials, at most 8192 characters.
        """
        parsed = urlsplit(url)
        if (
            len(url) > 8192
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "url must be an HTTP(S) URL without credentials, at most 8192 characters"
            )
        # The URL is data sent to the fixed provider API. We never connect to
        # this user-supplied destination locally; DeepSeek enforces fetch policy.
        return json.dumps(self._request("fetch", {"url": url}), ensure_ascii=False)

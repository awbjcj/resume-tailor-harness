"""Optional adapter for a host-owned synchronous Playwright Page or Frame.

Playwright is deliberately not an SDK dependency. The host supplies its existing
page, permission model, and a runtime with tracing/argument logging disabled.
"""

from typing import Any

from .accounts import PasswordForm, _origin


def playwright_password_form(
    target: Any,
    *,
    username_selector: str,
    password_selector: str,
    confirmation_selector: str | None = None,
) -> PasswordForm:
    """Bind to one target frame; never launch or attach to a different browser."""
    expected_origin = _origin(target.url)

    def inspect(handle: Any) -> dict:
        return handle.evaluate("""element => ({
            origin: element.ownerDocument.location.origin,
            input: element.tagName === 'INPUT',
            type: element.type,
            connected: element.isConnected
        })""")

    def is_password(selector: str) -> bool:
        locator = target.locator(selector)
        if locator.count() != 1:
            return False
        handle = locator.element_handle(timeout=3000)
        try:
            state = inspect(handle)
            return bool(
                state["origin"] == expected_origin
                and state["input"]
                and state["connected"]
                and state["type"] == "password"
                and handle.is_visible()
                and handle.is_editable()
            )
        finally:
            handle.dispose()

    def fill(selector: str, value: str) -> None:
        # A handle deliberately pins this document. A locator could resolve on
        # a new origin while waiting for actionability after a navigation.
        handle = target.locator(selector).element_handle(timeout=3000)
        try:
            state = inspect(handle)
            secret_field = selector != username_selector
            if (
                not state["connected"]
                or not state["input"]
                or state["origin"] != expected_origin
            ):
                raise ValueError("The account field changed")
            if secret_field and state["type"] != "password":
                raise ValueError("The password field changed")
            if not secret_field and state["type"] not in {"email", "text"}:
                raise ValueError("Use an email or text username field")
            if not handle.is_visible() or not handle.is_editable():
                raise ValueError("The account field is not editable")
            handle.fill(value, timeout=3000)
        finally:
            handle.dispose()

    return PasswordForm(
        current_url=lambda: target.url,
        is_password=is_password,
        fill=fill,
        username_selector=username_selector,
        password_selector=password_selector,
        confirmation_selector=confirmation_selector,
    )

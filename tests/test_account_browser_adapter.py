"""No browser required for ordinary CI; real-browser acceptance is opt-in."""

import os

import pytest
from pydantic import SecretStr

from resume_harness_sdk import PasswordForm, playwright_password_form
from resume_harness_sdk.accounts import ApplicationAccount


ACCOUNT: ApplicationAccount = {
    "id": "one",
    "company": "Example",
    "origin": "https://careers.example.com",
    "username": "applicant@example.com",
    "status": "pending",
    "revision": 1,
    "createdAt": "now",
    "updatedAt": "now",
    "lastUsedAt": None,
}


def test_navigation_during_fill_never_receives_the_password():
    url = ACCOUNT["origin"]
    writes = []

    def fill(selector, value):
        nonlocal url
        writes.append(selector)
        url = "https://phishing.example.com"

    form = PasswordForm(
        current_url=lambda: url,
        is_password=lambda _: True,
        fill=fill,
        username_selector="email",
        password_selector="password",
    )
    with pytest.raises(RuntimeError, match="Account fill stopped"):
        form.apply(ACCOUNT, SecretStr("private-password"))
    assert writes == ["email"]


def test_plaintext_field_or_duplicate_locator_is_rejected():
    writes = []
    for is_password, username in [(False, "email"), (True, "password")]:
        form = PasswordForm(
            current_url=lambda: ACCOUNT["origin"],
            is_password=lambda _: is_password,
            fill=lambda *args: writes.append(args),
            username_selector=username,
            password_selector="password",
        )
        with pytest.raises(ValueError):
            form.check(ACCOUNT["origin"])
    assert not writes


def test_browser_error_never_surfaces_fill_arguments():
    def broken_fill(_, value):
        if _ == "password":
            raise RuntimeError(f"Browser failed filling {value}")

    form = PasswordForm(
        current_url=lambda: ACCOUNT["origin"],
        is_password=lambda _: True,
        fill=broken_fill,
        username_selector="email",
        password_selector="password",
    )
    with pytest.raises(RuntimeError) as error:
        form.apply(ACCOUNT, SecretStr("private-password"))
    assert "private-password" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNT_BROWSER_TESTS") != "1",
    reason="Opt-in local Chromium integration",
)
def test_real_browser_registration_login_and_redirect_guard():
    from playwright.sync_api import sync_playwright

    html = '<input id="email" type="email"><input id="password" type="password"><input id="confirm" type="password"><button id="submit">Create account</button>'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route(
            "**/*", lambda route: route.fulfill(body=html, content_type="text/html")
        )
        page.goto(ACCOUNT["origin"] + "/register")
        form = playwright_password_form(
            page,
            username_selector="#email",
            password_selector="#password",
            confirmation_selector="#confirm",
        )
        form.apply(ACCOUNT, SecretStr("test-only-secret-1!"))
        assert page.locator("#email").input_value() == ACCOUNT["username"]
        assert page.locator("#password").input_value() == "test-only-secret-1!"
        assert page.locator("#confirm").input_value() == "test-only-secret-1!"
        page.goto(ACCOUNT["origin"] + "/login")
        login = playwright_password_form(
            page, username_selector="#email", password_selector="#password"
        )
        login.apply(ACCOUNT, SecretStr("test-only-secret-1!"))
        assert page.locator("#password").input_value() == "test-only-secret-1!"
        assert page.locator("#confirm").input_value() == ""
        page.goto("https://phishing.example.com/login")
        with pytest.raises(RuntimeError, match="Account fill stopped"):
            login.apply(ACCOUNT, SecretStr("test-only-secret-1!"))
        assert page.locator("#password").input_value() == ""
        browser.close()

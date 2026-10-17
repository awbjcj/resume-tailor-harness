from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    subject: str
    body: str


def _links(base_url: str, *paths: tuple[str, str]) -> str:
    if not base_url:
        return ""
    root = base_url.rstrip("/")
    return "".join(f"\n{label}: {root}{path}\n" for path, label in paths)


def verification_code(code: str, language: str = "en") -> Message:
    if language == "zh-CN":
        return Message(
            "Résumé Tailor Harness 邮箱验证码",
            f"邮箱验证码：{code}\n\n15 分钟内有效，仅可使用一次。\n",
        )
    return Message(
        "Your Résumé Tailor Harness verification code",
        f"Your verification code is {code}\n\nIt expires in 15 minutes and can be used once.\n",
    )


def reset_code(code: str, language: str = "en") -> Message:
    if language == "zh-CN":
        return Message(
            "Résumé Tailor Harness 密码重置验证码",
            f"重置密码的验证码：{code}\n\n15 分钟内有效，仅可使用一次。\n",
        )
    return Message(
        "Your Résumé Tailor Harness password reset code",
        f"Your password reset code is {code}\n\nIt expires in 15 minutes and can be used once.\n",
    )


def password_changed(base_url: str) -> Message:
    return Message(
        "Your Résumé Tailor Harness password was changed",
        "Your password was changed and other sessions were revoked."
        + _links(base_url, (("/forgot-password", "Reset your password"))),
    )


def google_linked(base_url: str) -> Message:
    return Message(
        "A Google account was linked to your Résumé Tailor Harness account",
        "Google sign-in was linked to your account."
        + _links(base_url, (("/forgot-password", "Secure your account"))),
    )


def google_unlinked(base_url: str) -> Message:
    return Message(
        "Google sign-in was removed from your Résumé Tailor Harness account",
        "Google sign-in was removed from your account."
        + _links(base_url, (("/login", "Review your account"))),
    )


def signup_on_existing(base_url: str, language: str = "en") -> Message:
    if language == "zh-CN":
        return Message(
            "有人尝试使用你的邮箱注册",
            "此邮箱已注册账户，本次未创建新账户。"
            + _links(base_url, ("/login", "登录"), ("/forgot-password", "重置密码")),
        )
    return Message(
        "Someone tried to sign up with your email",
        "An account already exists for this address; no new account was created."
        + _links(
            base_url,
            ("/login", "Sign in"),
            ("/forgot-password", "Reset your password"),
        ),
    )

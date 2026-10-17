"""Authored email translations; user names, job titles and free text stay verbatim."""

from __future__ import annotations

import re


def normalize_language(language: str | None) -> str:
    return "zh-CN" if (language or "").lower().startswith("zh") else "en"


ZH = {
    "Your job-search digest": "求职进展摘要",
    "digest": "摘要",
    "Daily": "每日",
    "Weekly": "每周",
    "Every 30 days": "每 30 天",
    "Daily digest": "每日摘要",
    "Weekly digest": "每周摘要",
    "Digest every 30 days": "每 30 天一期",
    "jobs awaiting review": "个待审核职位",
    "Unknown company": "公司名称不详",
    "Untitled job": "职位名称不详",
    "Review your shortlist": "查看候选清单",
    "Workspace statistics": "求职统计",
    "active jobs": "个活跃职位",
    "applications submitted": "份已提交申请",
    "applications in interview": "份进入面试的申请",
    "offers": "份录用通知",
    "View statistics": "查看统计",
    "Reminders": "待办提醒",
    "No upcoming events or follow-ups due.": "近期没有面试、截止日期或待跟进的申请。",
    "Open applications": "查看申请",
    "You opted in to these emails.": "你已开启求职摘要邮件。",
    "Manage preferences": "修改通知设置",
    "Unsubscribe": "关闭求职摘要邮件",
    "unsubscribe": "关闭求职摘要邮件",
    "or": "或",
    "Offer deadline": "录用回复截止时间",
    "Interview / assessment": "面试／测评",
    "Follow up after {days} days without activity": "已有 {days} 天未更新，建议跟进",
    "Verify your notification email": "验证接收通知的邮箱",
    "Enter this code in Settings > Email notifications": "请在“设置 > 邮件通知”中输入验证码",
    "Enter this code in Settings → Email notifications to confirm this address.": "请在“设置 → 邮件通知”中输入以下验证码，完成邮箱验证。",
    "The code expires in 15 minutes. Digests start only after verification and opt-in.": "验证码 15 分钟内有效。验证通过并开启求职摘要邮件后，系统才会按设置发送摘要。",
    "If you did not request this, ignore this email.": "如果这不是你的操作，请忽略这封邮件。",
    "Hello": "你好",
    "Operation recorded at": "操作时间：",
    "Review your account": "查看账户",
    "If you did not expect this change, contact your administrator.": "如果你对这次变更有疑问，请联系管理员。",
    "This account notice was sent to your registered email address. Account and security notices are independent of optional job-search digests.": "此邮件发送至你的注册邮箱。账户和安全通知不受求职摘要邮件设置影响。",
    "Your account was created": "账户已创建",
    "Your account is ready to use.": "你的账户已创建，可以开始使用了。",
    "Your account was deleted": "账户已删除",
    "An administrator deleted your account and workspace.": "管理员已删除你的账户和工作区。",
    "Your account was updated": "账户设置已更新",
    "An administrator changed your account settings.": "管理员修改了你的账户设置，变更内容如下。",
    "Your password was reset by an administrator": "管理员已重置你的密码",
    "Your password was reset and your existing sessions were revoked.": "你的密码已重置，其他登录会话已失效。",
    "Your password was changed": "密码已修改",
    "Your password was changed and your previous sign-in sessions were revoked.": "你的密码已修改，其他登录会话已失效。",
    "Google sign-in was linked to your account": "已绑定 Google 登录",
    "A Google identity was linked to your account.": "你的账户已绑定 Google 登录。",
    "Google sign-in was removed from your account": "已解除 Google 登录绑定",
    "The linked Google identity was removed from your account.": "你的账户已解除 Google 登录绑定。",
    "Your sessions were revoked": "其他登录会话已失效",
    "Your previous sign-in sessions were revoked.": "此前的登录会话已失效，其他会话需要重新登录。",
    "An access token was created": "已创建访问令牌",
    "A personal access token was created for your account.": "你的账户新增了一个个人访问令牌。",
    "An access token was revoked": "已撤销访问令牌",
    "A personal access token was revoked for your account.": "一个个人访问令牌已撤销，无法再用于访问你的账户。",
    "Your account email was changed": "注册邮箱已更改",
    "The registered email address for your account was updated.": "你的注册邮箱已更改。",
    "Your quota period was renewed": "新周期额度已发放",
    "Your recurring allowance has reset for a new quota period.": "新的额度周期已开始，本周期额度已发放。",
    "Your quota was reset": "使用额度已重置",
    "Your usage in the current quota period was reset. Durable credits spent in this period were restored.": "本周期的使用量已清零，本周期扣除的余额也已退回。",
    "Your credit balance was increased": "账户余额已增加",
    "Credits were added to your account.": "你的账户余额已增加。",
    "Your credit balance was decreased": "账户余额已减少",
    "Credits were removed from your account.": "你的账户余额已扣减。",
    "Your credit purchase was applied": "充值已到账",
    "Your payment was confirmed and credits were added to your account.": "付款已确认，充值金额已计入账户余额。",
    "Your credit purchase was refunded": "充值退款已处理",
    "A refund was applied to your credit purchase.": "你的充值订单已退款。",
    "Your shared-key access was suspended": "共享密钥权限已暂停",
    "A payment dispute suspended shared-key access. Contact your administrator to review your account.": "由于付款争议，你的共享密钥权限已暂停。请联系管理员核查。",
    "Your subscription was activated": "订阅已开通",
    "Your subscription is now active.": "你的订阅已生效。",
    "Your subscription was renewed": "订阅已续订",
    "Your subscription term was extended.": "你的订阅有效期已延长。",
    "Your subscription was revoked": "订阅已撤销",
    "Your subscription was revoked and your account returned to the Free tier. Your durable credits remain available.": "你的订阅已撤销，账户已恢复为免费档位。长期余额仍可使用。",
    "Your subscription expired": "订阅已到期",
    "Your subscription expired and your account returned to the Free tier. Your durable credits remain available.": "你的订阅已到期，账户已恢复为免费档位。长期余额仍可使用。",
    "Your subscription cancellation was updated": "订阅取消设置已更新",
    "The scheduled cancellation of your subscription was changed.": "你的订阅取消设置已变更，详情如下。",
    "Your quota tier was changed": "额度档位已更改",
    "Your account was assigned a new quota tier.": "你的账户已调整到新的额度档位。",
    "Your tier allowance was changed": "套餐额度已更改",
    "An administrator changed the allowance for your quota tier.": "管理员修改了你所在档位的周期额度。",
    "Your quota allowance was changed": "个人额度已更改",
    "An administrator changed your individual quota allowance.": "管理员修改了你的个人可用额度。",
    "Your quota tier settings were changed": "额度档位设置已更改",
    "An administrator updated the settings for your quota tier.": "管理员修改了你所在额度档位的设置。",
    "Quota tier": "额度档位",
    "Credit balance": "账户余额",
    "Recurring allowance": "周期额度",
    "Period ends (UTC)": "本周期结束时间（UTC）",
    "Adjustment": "调整金额",
    "Credits removed": "扣除的余额",
    "Reason": "原因",
    "Subscription tier": "订阅套餐",
    "Subscription status": "订阅状态",
    "Term ends (UTC)": "订阅到期时间（UTC）",
    "Shared-key access": "共享密钥权限",
    "Role": "账户角色",
    "Account access": "账户状态",
    "Active job limit": "活跃职位数上限",
    "Concurrent run limit": "并发运行数上限",
    "Token name": "令牌名称",
    "Notification email": "接收摘要的邮箱",
    "Access token": "访问令牌",
    "Plan": "套餐",
    "Cancellation scheduled": "已安排取消订阅",
    "Allowance override": "个人额度设置",
    "Cancel at period end": "本期结束后取消订阅",
    "Cancel at end of term": "到期后取消订阅",
    "New registered email": "新的注册邮箱",
    "Registered email": "注册邮箱",
    "Renewal cycle": "额度发放周期",
    "Available for new assignments": "可继续分配",
    "Tier": "档位",
    "Name": "名称",
    "Granted": "已授权",
    "Revoked": "已撤销",
    "Administrator": "管理员",
    "Member": "成员",
    "Disabled": "已停用",
    "Enabled": "已启用",
    "Unlimited": "不限额",
    "Default": "使用默认值",
    "System default": "系统默认值",
    "Yes": "是",
    "No": "否",
    "FREE": "免费档位",
    "SUBSCRIBER": "订阅套餐",
    "True": "是",
    "False": "否",
    "ACTIVE": "生效中",
    "EXPIRED": "已到期",
    "REVOKED": "已撤销",
    "Unsubscribe from email notifications?": "关闭求职摘要邮件？",
    "Account security emails will continue.": "关闭后，你仍会在注册邮箱中收到账户和安全通知。",
    "You are unsubscribed": "求职摘要邮件已关闭",
    "Email notifications are off. You can opt in again in Settings → Email notifications.": "你可以随时在“设置 → 邮件通知”中重新开启。",
}


def translate(text: str, language: str) -> str:
    return ZH.get(text, text) if normalize_language(language) == "zh-CN" else text


def detail_value(label: str, value: str, language: str) -> str:
    # Never translate user-provided reasons, names, addresses or token labels.
    if label == "Renewal cycle" and normalize_language(language) == "zh-CN":
        cycle = re.fullmatch(r"(\d+) (week|month)", value)
        if cycle:
            count, unit = cycle.groups()
            if count == "1":
                return "每周" if unit == "week" else "每月"
            return f"每 {count} 周" if unit == "week" else f"每 {count} 个月"
    if (
        label in {"Active job limit", "Concurrent run limit"}
        and normalize_language(language) == "zh-CN"
    ):
        return " → ".join(
            "不限制" if part in {"0", "Unlimited"} else translate(part, language)
            for part in value.split(" → ")
        )
    if label not in {
        "Role",
        "Account access",
        "Shared-key access",
        "Subscription status",
        "Cancel at period end",
        "Cancel at end of term",
        "Available for new assignments",
        "Quota tier",
        "Subscription tier",
        "Allowance override",
        "Active job limit",
        "Concurrent run limit",
        "Recurring allowance",
    }:
        return value
    return " → ".join(translate(part, language) for part in value.split(" → "))

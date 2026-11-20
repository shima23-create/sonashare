from django import template

from ..models import Notification

register = template.Library()

MENU_LIMIT = 5


@register.simple_tag
def unread_notification_count(user):
    """未読の通知の数"""
    if not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()


@register.inclusion_tag("bichiku/_notification_menu.html", takes_context=True)
def notification_menu(context):
    """ヘッダーのベル。押すと、最新の通知がプルダウンで開く"""
    user = getattr(context.get("request"), "user", None)
    if not getattr(user, "is_authenticated", False):
        return {"show": False}
    return {
        "show": True,
        "unread": Notification.objects.filter(user=user, is_read=False).count(),
        "notifications": Notification.objects.filter(user=user).order_by("-created_at", "-id")[:MENU_LIMIT],
    }
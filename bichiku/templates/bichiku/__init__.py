from django import template

from ..models import Notification

register = template.Library()


@register.simple_tag
def unread_notification_count(user):
    """ヘッダーのベルに出す、未読の通知の数"""
    if not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()
from bichiku.models import Notification


def notifications_context(request):
    """ログイン中ユーザーの未読通知件数をテンプレート全体へ提供"""
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()
        return {
            "unread_notifications_count": unread_count,
        }
    return {
        "unread_notifications_count": 0,
    }

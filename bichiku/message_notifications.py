"""メッセージを送ったとき、相手の組織のユーザー全員に通知を作る。"""

from django.contrib.auth import get_user_model

from .models import Notification


def notify_new_message(message):
    """送信者の反対側(企業なら団体、団体なら企業)のユーザーに、通知を作る。作った件数を返す"""
    reservation = message.conversation.reservation
    sender_profile = getattr(message.sender, "profile", None)
    sender_org = getattr(sender_profile, "organization", None)
    if sender_org is None:
        return 0

    if sender_org.pk == reservation.organization_id:
        target = reservation.offer.organization
    else:
        target = reservation.organization

    User = get_user_model()
    notifications = [
        Notification(
            user=user,
            title="新しいメッセージ",
            content=f"{sender_org.name}: {message.content}"[:255],
            type=Notification.Type.MESSAGE,
            related_reservation=reservation,
        )
        for user in User.objects.filter(profile__organization=target).exclude(pk=message.sender_id)
    ]
    Notification.objects.bulk_create(notifications)
    return len(notifications)
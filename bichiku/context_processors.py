from django.db.models import Q

from .models import Message, Profile


def unread_message_count(request):
    if not request.user.is_authenticated:
        return {"unread_message_count": 0}

    try:
        organization = Profile.objects.only("organization_id").get(
            user=request.user
        ).organization
    except Profile.DoesNotExist:
        return {"unread_message_count": 0}

    count = (
        Message.objects.filter(
            Q(conversation__reservation__organization=organization)
            | Q(conversation__reservation__offer__organization=organization),
            is_read=False,
        )
        .exclude(sender__profile__organization=organization)
        .count()
    )
    return {"unread_message_count": count}

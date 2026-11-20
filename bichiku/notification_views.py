from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification

LIST_LIMIT = 100


@login_required
def notification_list(request):
    notifications = (
        Notification.objects.filter(user=request.user)
        .select_related("related_reservation")
        .order_by("-created_at", "-id")[:LIST_LIMIT]
    )
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(
        request,
        "bichiku/notifications.html",
        {"notifications": notifications, "unread_count": unread_count},
    )


@require_POST
@login_required
def notification_open(request, pk):
    """通知を既読にして、関連する画面へ移動する(自分の通知だけ)"""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    if notification.related_reservation_id:
        return redirect("bichiku:reservation_list")
    return redirect("bichiku:notification_list")


@require_POST
@login_required
def notification_read_all(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("bichiku:notification_list")
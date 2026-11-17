"""予約を申し込む処理。

募集(Offer)の行をロックして、残り数量を確認してから予約・会話・通知を作ります。
同時に2人が申し込んでも、数量を超えないようにするためです。
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    Conversation,
    Message,
    Notification,
    Offer,
    Reservation,
)
from .offer_forms import reserved_quantity_of


class ReservationError(Exception):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def remaining_quantity(offer):
    """その募集で、あと何個まで予約できるか"""
    return max(offer.quantity - reserved_quantity_of(offer), 0)


def reservation_problems(offer, quantity, requested_pickup_at):
    problems = []
    today = timezone.localdate()
    lot = offer.lot

    if offer.status != Offer.Status.RECRUITING:
        problems.append("この募集は、受け付けを終了しています。")
    if offer.deadline is None or offer.deadline < today:
        problems.append("この募集は、締め切られています。")
    if lot.expiration_date < today:
        problems.append("消費期限が過ぎているため、予約できません。")

    remaining = remaining_quantity(offer)
    if quantity < 1:
        problems.append("数量は1以上にしてください。")
    elif quantity > remaining:
        problems.append(f"予約できる残りは {remaining}{lot.stock_item.unit} です。")

    if requested_pickup_at < timezone.now():
        problems.append("希望受け取り日時は、現在より後にしてください。")
    elif timezone.localtime(requested_pickup_at).date() > lot.expiration_date:
        problems.append("希望受け取り日は、消費期限以前にしてください。")
    return problems


@transaction.atomic
def reserve_offer(*, offer_id, organization, user, quantity, requested_pickup_at, message=""):
    """予約を申し込む。予約・会話・通知(提供側の全ユーザー宛)を作って、予約を返す"""
    if organization.is_company:
        raise ReservationError(["予約できるのは、活動団体のアカウントだけです。"])

    offer = (
        Offer.objects.select_for_update()
        .select_related("organization", "lot__stock_item")
        .get(pk=offer_id)
    )
    problems = reservation_problems(offer, quantity, requested_pickup_at)
    if problems:
        raise ReservationError(problems)

    message = (message or "").strip()
    reservation = Reservation.objects.create(
        offer=offer,
        organization=organization,
        reserved_quantity=quantity,
        requested_pickup_at=requested_pickup_at,
        status=Reservation.Status.PENDING,
        message=message,
    )
    conversation = Conversation.objects.create(reservation=reservation)
    if message:
        Message.objects.create(conversation=conversation, sender=user, content=message)

    unit = offer.lot.stock_item.unit
    User = get_user_model()
    Notification.objects.bulk_create(
        [
            Notification(
                user=provider_user,
                title="新しい予約が入りました",
                content=f"{organization.name} から「{offer.title}」に {quantity}{unit} の予約が入りました。",
                type=Notification.Type.RESERVATION,
                related_reservation=reservation,
            )
            for provider_user in User.objects.filter(
                profile__organization=offer.organization
            )
        ]
    )
    return reservation
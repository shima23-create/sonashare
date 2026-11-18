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
    PickupRecord,
    Reservation,
    StockLot,
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


# ---------------------------------------------------------
# 予約の承認・取り消し・受け取り完了
#
# 数量の考え方(offer_services.py と同じ)
#   - 募集を公開した時点で、その数量は StockLot.quantity から引いてある
#   - 予約は、その募集の数量の一部を押さえている(予約中・承認済み)
#   - 受け取りが終わった分は、募集の数量からも引く
# ---------------------------------------------------------
def _notify_organization(organization, *, title, content, reservation):
    User = get_user_model()
    Notification.objects.bulk_create(
        [
            Notification(
                user=user,
                title=title,
                content=content[:255],
                type=Notification.Type.RESERVATION,
                related_reservation=reservation,
            )
            for user in User.objects.filter(profile__organization=organization)
        ]
    )


def _lock(reservation_id):
    """予約 → 募集 → ロット の順にロックして返す(順番を固定して、行き詰まりを防ぐ)"""
    reservation = (
        Reservation.objects.select_for_update()
        .select_related("organization", "offer__organization", "offer__lot__stock_item")
        .get(pk=reservation_id)
    )
    offer = Offer.objects.select_for_update().get(pk=reservation.offer_id)
    lot = StockLot.objects.select_for_update().get(pk=offer.lot_id)
    return reservation, offer, lot


@transaction.atomic
def approve_reservation(reservation_id):
    reservation, offer, _lot = _lock(reservation_id)
    if reservation.status != Reservation.Status.PENDING:
        raise ReservationError(["予約中の予約だけ、承認できます。"])

    reservation.status = Reservation.Status.APPROVED
    reservation.save(update_fields=["status", "updated_at"])
    _notify_organization(
        reservation.organization,
        title="予約が承認されました",
        content=f"{reservation.offer.organization.name} が「{offer.title}」の予約を承認しました。",
        reservation=reservation,
    )
    return reservation


@transaction.atomic
def cancel_reservation(reservation_id, *, by_company):
    """予約を取り消す(団体のキャンセル、企業の却下・取り消し)"""
    reservation, offer, lot = _lock(reservation_id)
    if reservation.status not in Reservation.ACTIVE_STATUSES:
        raise ReservationError(["予約中・承認済みの予約だけ、取り消せます。"])

    was_pending = reservation.status == Reservation.Status.PENDING
    quantity = reservation.reserved_quantity
    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])

    # 終了済みの募集は、予約の分だけを残している。取り消されたら、備蓄品に戻す
    if offer.status == Offer.Status.CLOSED:
        lot.quantity += quantity
        lot.save(update_fields=["quantity", "updated_at"])
        offer.quantity = max(offer.quantity - quantity, 0)
        offer.save(update_fields=["quantity", "updated_at"])

    if by_company:
        verb = "却下" if was_pending else "取り消し"
        _notify_organization(
            reservation.organization,
            title=f"予約が{verb}されました",
            content=f"{offer.organization.name} が「{offer.title}」の予約を{verb}しました。",
            reservation=reservation,
        )
    else:
        _notify_organization(
            offer.organization,
            title="予約がキャンセルされました",
            content=f"{reservation.organization.name} が「{offer.title}」の予約をキャンセルしました。",
            reservation=reservation,
        )
    return reservation


@transaction.atomic
def complete_reservation(reservation_id, *, user, received_quantity):
    """受け取りの完了を記録する。渡した分を募集から引き、受け取りが少なければ差を備蓄品に戻す"""
    reservation, offer, lot = _lock(reservation_id)
    if reservation.status != Reservation.Status.APPROVED:
        raise ReservationError(["承認済みの予約だけ、受け取り完了にできます。"])
    reserved = reservation.reserved_quantity
    if not 1 <= received_quantity <= reserved:
        raise ReservationError([f"受け取った数量は、1〜{reserved} の間で入力してください。"])

    pickup_status = (
        PickupRecord.PickupStatus.COMPLETED
        if received_quantity == reserved
        else PickupRecord.PickupStatus.PARTIAL
    )
    PickupRecord.objects.create(
        reservation=reservation,
        user=user,
        received_quantity=received_quantity,
        picked_up_at=timezone.now(),
        pickup_status=pickup_status,
    )
    reservation.status = Reservation.Status.COMPLETED
    reservation.save(update_fields=["status", "updated_at"])

    # 予約した数量は、この募集から出ていく。受け取りが少なかった差は、備蓄品に戻す
    offer.quantity = max(offer.quantity - reserved, 0)
    if received_quantity < reserved:
        lot.quantity += reserved - received_quantity
        lot.save(update_fields=["quantity", "updated_at"])
    if offer.quantity == 0 and offer.status == Offer.Status.RECRUITING:
        offer.status = Offer.Status.CLOSED
    offer.save(update_fields=["quantity", "status", "updated_at"])

    unit = lot.stock_item.unit
    _notify_organization(
        reservation.organization,
        title="受け取りが完了しました",
        content=f"「{offer.title}」を {received_quantity}{unit} 受け取りました。",
        reservation=reservation,
    )
    return reservation
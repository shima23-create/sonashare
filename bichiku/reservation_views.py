"""予約の一覧と、承認・取り消し・受け取り完了(企業と団体の両方が使う)"""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import company_required, organization_required
from .models import Reservation
from .reservation_forms import CompleteForm
from .reservation_services import (
    ReservationError,
    approve_reservation,
    cancel_reservation,
    complete_reservation,
)


def _own_reservations(organization):
    """自分の組織の予約だけ。企業は「自社の募集への予約」、団体は「自分たちの予約」"""
    queryset = Reservation.objects.select_related(
        "organization", "offer__organization", "offer__lot__stock_item", "conversation"
    )
    if organization.is_company:
        return queryset.filter(offer__organization=organization)
    return queryset.filter(organization=organization)


def _fail(request, error):
    for problem in error.problems:
        messages.error(request, problem)


# チームの画面(reservations.html)の、?status= の値と、予約の状態の対応
STATUS_PARAMS = {
    "reserved": Reservation.Status.PENDING,
    "scheduled": Reservation.Status.APPROVED,
    "completed": Reservation.Status.COMPLETED,
    "cancelled": Reservation.Status.CANCELLED,
}


@organization_required
def reservation_list(request):
    organization = request.organization
    reservations = _own_reservations(organization)

    query = request.GET.get("q", "").strip()
    if query:
        # 企業は「予約した団体名」、団体は「提供企業名」でも探せる
        partner_name = (
            "organization__name__icontains"
            if organization.is_company
            else "offer__organization__name__icontains"
        )
        reservations = reservations.filter(
            Q(offer__lot__stock_item__name__icontains=query)
            | Q(offer__title__icontains=query)
            | Q(**{partner_name: query})
        )

    status = request.GET.get("status", "")
    if status in STATUS_PARAMS:
        reservations = reservations.filter(status=STATUS_PARAMS[status])
    else:
        status = ""

    return render(
        request,
        "bichiku/reservations.html",
        {
            "reservations": reservations.order_by("-created_at"),
            "current_status": status,
            "is_company": organization.is_company,
        },
    )


@require_POST
@company_required
def reservation_approve(request, pk):
    reservation = get_object_or_404(_own_reservations(request.organization), pk=pk)
    try:
        approve_reservation(reservation.pk)
    except ReservationError as error:
        _fail(request, error)
    else:
        messages.success(request, "予約を承認しました。")
    return redirect("bichiku:reservation_list")


@require_POST
@organization_required
def reservation_cancel(request, pk):
    """団体のキャンセル、企業の却下・取り消し(どちらも自分の予約だけ)"""
    reservation = get_object_or_404(_own_reservations(request.organization), pk=pk)
    try:
        cancel_reservation(reservation.pk, by_company=request.organization.is_company)
    except ReservationError as error:
        _fail(request, error)
    else:
        messages.success(request, "予約を取り消しました。")
    return redirect("bichiku:reservation_list")


@require_POST
@company_required
def reservation_complete(request, pk):
    reservation = get_object_or_404(_own_reservations(request.organization), pk=pk)
    form = CompleteForm(request.POST, reservation=reservation)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("bichiku:reservation_list")
    try:
        complete_reservation(
            reservation.pk,
            user=request.user,
            received_quantity=form.cleaned_data["received_quantity"],
        )
    except ReservationError as error:
        _fail(request, error)
    else:
        messages.success(request, "受け取り完了を記録しました。")
    return redirect("bichiku:reservation_list")
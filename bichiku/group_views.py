"""活動団体(利用者)の画面: 募集を探す・詳細・予約の申し込み"""

from datetime import timedelta

from django.contrib import messages
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .access import group_required
from .models import PREFECTURES, Offer, Reservation, StockItem
from .reservation_forms import ReservationForm
from .reservation_services import ReservationError, reserve_offer


def _open_offers():
    """いま予約できる募集だけ(募集中・締切前・期限内・残りあり)"""
    today = timezone.localdate()
    return (
        Offer.objects.filter(
            status=Offer.Status.RECRUITING,
            deadline__gte=today,
        )
        # 期限内のもの(消費期限がないものも含む)
        .filter(Q(lot__expiration_date__gte=today) | Q(lot__expiration_date__isnull=True))
        .select_related("organization", "lot__stock_item")
        .annotate(
            reserved_total=Coalesce(
                Sum(
                    "reservations__reserved_quantity",
                    filter=Q(reservations__status__in=Reservation.ACTIVE_STATUSES),
                ),
                0,
            )
        )
        .annotate(remaining=F("quantity") - F("reserved_total"))
        .filter(remaining__gt=0)
    )


EXPIRY_CHOICES = (("7", "7日以内"), ("14", "14日以内"), ("30", "30日以内"))
SORT_CHOICES = (
    ("deadline", "募集締切が近い順"),
    ("expiry", "消費期限が近い順"),
    ("new", "新しい順"),
)
SORT_ORDER = {
    "deadline": ("deadline", "pk"),
    "expiry": (F("lot__expiration_date").asc(nulls_last=True), "pk"),
    "new": ("-created_at", "-pk"),
}


@group_required
def offer_browse(request):
    offers = _open_offers()
    today = timezone.localdate()

    query = request.GET.get("q", "").strip()
    prefecture = request.GET.get("prefecture", "")
    # ジャンルは、複数選べる(?category=drink&category=staple)
    selected_categories = [
        c for c in request.GET.getlist("category") if c in StockItem.Category.values
    ]
    expiry = request.GET.get("expiry", "")
    sort = request.GET.get("sort", "deadline")

    if query:
        offers = offers.filter(
            Q(title__icontains=query)
            | Q(lot__stock_item__name__icontains=query)
            | Q(organization__name__icontains=query)
        )
    if prefecture in dict(PREFECTURES):
        offers = offers.filter(prefecture=prefecture)
    else:
        prefecture = ""
    if selected_categories:
        offers = offers.filter(lot__stock_item__category__in=selected_categories)
    if expiry in dict(EXPIRY_CHOICES):
        offers = offers.filter(
            lot__expiration_date__lte=today + timedelta(days=int(expiry))
        )
    else:
        expiry = ""

    if sort not in SORT_ORDER:
        sort = "deadline"
    offers = offers.order_by(*SORT_ORDER[sort])

    has_filter = bool(query or prefecture or selected_categories or expiry)
    return render(
        request,
        "bichiku/offer_browse.html",
        {
            "offers": offers,
            "offer_count": offers.count(),
            "prefectures": PREFECTURES,
            "categories": StockItem.Category.choices,
            "expiry_choices": EXPIRY_CHOICES,
            "sort_choices": SORT_CHOICES,
            "q": query,
            "prefecture": prefecture,
            "selected_categories": selected_categories,
            "expiry": expiry,
            "sort": sort,
            "has_filter": has_filter,
        },
    )


@group_required
def offer_detail(request, pk):
    offer = get_object_or_404(_open_offers(), pk=pk)

    if request.method == "POST":
        form = ReservationForm(request.POST, offer=offer)
        if form.is_valid():
            try:
                reserve_offer(
                    offer_id=offer.pk,
                    organization=request.organization,
                    user=request.user,
                    quantity=form.cleaned_data["quantity"],
                    requested_pickup_at=form.cleaned_data["requested_pickup_at"],
                    message=form.cleaned_data["message"],
                )
            except ReservationError as error:
                for problem in error.problems:
                    form.add_error(None, problem)
            else:
                messages.success(
                    request, "予約を申し込みました。提供元の承認をお待ちください。"
                )
                return redirect("bichiku:reservation_list")
    else:
        form = ReservationForm(offer=offer, initial={"quantity": 1})

    return render(
        request, "bichiku/offer_detail.html", {"offer": offer, "form": form}
    )
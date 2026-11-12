from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import company_required
from .models import EXPIRY_WARNING_DAYS, Offer, Reservation, StockLot
from .offer_forms import (
    OfferForm,
    default_offer_values,
    offerable_quantity,
    publish_problems,
)


def _offers_of(organization):
    return Offer.objects.filter(organization=organization).select_related(
        "lot__stock_item"
    )


@company_required
def offer_list(request):
    organization = request.organization
    status = request.GET.get("status", "")

    offers = _offers_of(organization).annotate(
        reserved_total=Coalesce(
            Sum(
                "reservations__reserved_quantity",
                filter=Q(reservations__status__in=Reservation.ACTIVE_STATUSES),
            ),
            0,
        )
    )
    if status in Offer.Status.values:
        offers = offers.filter(status=status)

    counts = {row["status"]: row["n"] for row in (
        Offer.objects.filter(organization=organization)
        .values("status")
        .annotate(n=Count("id"))
    )}
    counts["all"] = sum(counts.values())

    # 期限が近いのに、まだ下書きも募集もない、提供対象のロット
    today = timezone.localdate()
    suggestions = (
        StockLot.objects.filter(
            stock_item__organization=organization,
            availability=StockLot.Availability.AVAILABLE,
            quantity__gt=0,
            expiration_date__gte=today,
            expiration_date__lte=today + timedelta(days=EXPIRY_WARNING_DAYS),
        )
        .exclude(offers__status__in=[Offer.Status.DRAFT, Offer.Status.RECRUITING])
        .select_related("stock_item")
        .order_by("expiration_date")[:5]
    )

    return render(
        request,
        "bichiku/offer_list.html",
        {
            "offers": offers,
            "counts": counts,
            "current_status": status if status in Offer.Status.values else "",
            "suggestions": suggestions,
        },
    )


@company_required
def offer_create(request):
    organization = request.organization

    if request.method == "POST":
        form = OfferForm(request.POST, organization=organization)
        if form.is_valid():
            offer = form.save(commit=False)
            offer.organization = organization
            wants_publish = request.POST.get("action") == "publish"
            if wants_publish:
                for problem in publish_problems(offer):
                    form.add_error(None, problem)
            if not form.errors:
                offer.status = (
                    Offer.Status.RECRUITING if wants_publish else Offer.Status.DRAFT
                )
                offer.save()
                messages.success(
                    request,
                    "募集を公開しました。" if wants_publish else "下書きとして保存しました。",
                )
                return redirect("bichiku:offer_list")
    else:
        initial = {}
        lot_id = request.GET.get("lot", "")
        if lot_id.isdigit():
            lot = (
                StockLot.objects.filter(
                    pk=int(lot_id),
                    stock_item__organization=organization,
                    availability=StockLot.Availability.AVAILABLE,
                )
                .select_related("stock_item")
                .first()
            )
            if lot:
                initial = {"lot": lot, **default_offer_values(lot)}
        form = OfferForm(initial=initial, organization=organization)

    return render(request, "bichiku/offer_form.html", {"form": form, "offer": None})


@company_required
def offer_edit(request, pk):
    organization = request.organization
    offer = get_object_or_404(_offers_of(organization), pk=pk)

    if offer.status == Offer.Status.CLOSED:
        messages.error(request, "終了した募集は、編集できません。")
        return redirect("bichiku:offer_list")

    if request.method == "POST":
        form = OfferForm(request.POST, instance=offer, organization=organization)
        if form.is_valid():
            offer = form.save(commit=False)
            wants_publish = request.POST.get("action") == "publish"
            to_recruiting = wants_publish or offer.status == Offer.Status.RECRUITING
            if to_recruiting:
                for problem in publish_problems(offer):
                    form.add_error(None, problem)
            if not form.errors:
                was_draft = offer.status == Offer.Status.DRAFT
                offer.status = (
                    Offer.Status.RECRUITING if to_recruiting else Offer.Status.DRAFT
                )
                offer.save()
                if to_recruiting and was_draft:
                    messages.success(request, "募集を公開しました。")
                elif to_recruiting:
                    messages.success(request, "募集の内容を更新しました。")
                else:
                    messages.success(request, "下書きを保存しました。")
                return redirect("bichiku:offer_list")
    else:
        form = OfferForm(instance=offer, organization=organization)

    return render(request, "bichiku/offer_form.html", {"form": form, "offer": offer})


@require_POST
@company_required
def offer_publish(request, pk):
    offer = get_object_or_404(_offers_of(request.organization), pk=pk)
    if offer.status != Offer.Status.DRAFT:
        messages.error(request, "下書きの募集だけ、公開できます。")
        return redirect("bichiku:offer_list")

    problems = publish_problems(offer)
    if problems:
        for problem in problems:
            messages.error(request, problem)
        return redirect("bichiku:offer_edit", pk=offer.pk)

    offer.status = Offer.Status.RECRUITING
    offer.save()
    messages.success(request, f"「{offer.title}」を公開しました。")
    return redirect("bichiku:offer_list")


@require_POST
@company_required
def offer_close(request, pk):
    offer = get_object_or_404(_offers_of(request.organization), pk=pk)
    if offer.status != Offer.Status.RECRUITING:
        messages.error(request, "募集中の募集だけ、終了できます。")
        return redirect("bichiku:offer_list")

    offer.status = Offer.Status.CLOSED
    offer.save()
    messages.success(
        request,
        f"「{offer.title}」の募集を終了しました。すでに入っている予約は、そのまま有効です。",
    )
    return redirect("bichiku:offer_list")


@require_POST
@company_required
def offer_delete(request, pk):
    offer = get_object_or_404(_offers_of(request.organization), pk=pk)
    if offer.status != Offer.Status.DRAFT:
        messages.error(request, "削除できるのは、下書きの募集だけです。")
        return redirect("bichiku:offer_list")

    title = offer.title
    offer.delete()
    messages.success(request, f"下書き「{title}」を削除しました。")
    return redirect("bichiku:offer_list")


@require_POST
@company_required
def offer_draft_from_lot(request, lot_id):
    """期限が近い備蓄品から、募集の下書きをワンクリックで作る"""
    organization = request.organization
    lot = get_object_or_404(
        StockLot.objects.select_related("stock_item"),
        pk=lot_id,
        stock_item__organization=organization,
    )

    existing = lot.offers.filter(status=Offer.Status.DRAFT).first()
    if existing:
        messages.info(request, "このロットの下書きが、すでにあります。")
        return redirect("bichiku:offer_edit", pk=existing.pk)

    if lot.availability != StockLot.Availability.AVAILABLE:
        messages.error(request, "このロットは、提供対象になっていません。")
        return redirect("bichiku:offer_list")
    if lot.expiration_date < timezone.localdate():
        messages.error(request, "消費期限が過ぎているため、募集できません。")
        return redirect("bichiku:offer_list")
    if offerable_quantity(lot) <= 0:
        messages.error(request, "募集に出せる残りの数量がありません。")
        return redirect("bichiku:offer_list")

    offer = Offer.objects.create(
        lot=lot,
        organization=organization,
        status=Offer.Status.DRAFT,
        **default_offer_values(lot),
    )
    messages.success(request, "下書きを作成しました。内容を確認して、公開してください。")
    return redirect("bichiku:offer_edit", pk=offer.pk)

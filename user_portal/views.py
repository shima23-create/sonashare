import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from bichiku.access import group_required
from bichiku.models import Conversation, Notification, StockItem

from .forms import ContactForm
from .geo import (
    PREFECTURE_COORDINATES,
    PREFECTURE_LIST,
    extract_prefecture,
    get_coordinates_from_address,
)
from .selectors import offers_with_availability


@group_required
def dashboard(request):
    return redirect("bichiku:dashboard")


@group_required
def profile(request):
    return redirect("bichiku:my_page")


@group_required
def item_list(request):
    offers = offers_with_availability()
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    location = request.GET.get("location", "").strip()
    pref = request.GET.get("pref", "").strip()

    if query:
        offers = offers.filter(
            Q(title__icontains=query)
            | Q(lot__stock_item__name__icontains=query)
            | Q(organization__name__icontains=query)
        )
    if category in StockItem.Category.values:
        offers = offers.filter(lot__stock_item__category=category)
    if location:
        offers = offers.filter(
            Q(pickup_location__icontains=location)
        )
    if pref in PREFECTURE_COORDINATES:
        offers = offers.filter(prefecture=pref)
    else:
        pref = ""

    offers = list(
        offers.select_related("organization", "lot__stock_item").order_by(
            "lot__expiration_date", "title"
        )
    )
    spots = {}
    for offer in offers:
        address = " ".join(
            part
            for part in (
                offer.pickup_location,
                offer.prefecture,
            )
            if part
        )
        lat, lng = get_coordinates_from_address(address)
        location_key = (
            round(lat, 5),
            round(lng, 5),
            offer.pickup_location,
            offer.organization_id,
        )
        spot = spots.setdefault(
            location_key,
            {
                "name": offer.pickup_location or offer.organization.name,
                "org_name": offer.organization.name,
                "address": offer.pickup_location or offer.prefecture,
                "geocode_address": " ".join(
                    part
                    for part in (
                        offer.pickup_location,
                        offer.prefecture,
                        offer.organization.address,
                    )
                    if part
                ),
                "lat": lat,
                "lng": lng,
                "coordinates_known": False,
                "items": [],
            },
        )
        spot["items"].append(
            {
                "id": offer.pk,
                "title": offer.title,
                "category": offer.lot.stock_item.get_category_display(),
                "quantity": offer.remaining,
                "unit": offer.lot.stock_item.unit,
                "expiry": offer.lot.expiration_date.strftime("%Y年%m月%d日"),
                "detail_url": reverse("user_portal:item_detail", args=[offer.pk]),
            }
        )

    map_spots = list(spots.values())
    pref_coords = PREFECTURE_COORDINATES.get(pref) if pref else None
    return render(
        request,
        "user_portal/items.html",
        {
            "items": offers,
            "categories": StockItem.Category.choices,
            "prefectures": [(name, name) for name in PREFECTURE_LIST],
            "selected_pref": pref,
            "pref_coords_json": json.dumps(list(pref_coords) if pref_coords else None),
            "map_spots_json": json.dumps(map_spots, ensure_ascii=False),
            "query": query,
            "selected_category": category,
            "location": location,
        },
    )


@group_required
@require_GET
def map_inventory_search(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse(
            {"error": "住所または企業名を2文字以上で入力してください。"},
            status=400,
        )
    if len(query) > 120:
        return JsonResponse(
            {"error": "検索語は120文字以内で入力してください。"},
            status=400,
        )

    matching = Q(organization__name__icontains=query) | Q(
        pickup_location__icontains=query
    )
    prefecture = extract_prefecture(query)
    if prefecture:
        matching |= Q(prefecture=prefecture)

    matching_offers = offers_with_availability().filter(matching).values(
        "organization_id",
        "organization__name",
        "lot__stock_item__name",
        "lot__stock_item__category",
        "lot__stock_item__unit",
        "remaining",
    )
    rows = list(matching_offers[:501])
    if len(rows) > 500:
        return JsonResponse(
            {"error": "検索結果が多いため、住所をより詳しく入力してください。"},
            status=413,
        )

    organizations = {}
    category_labels = dict(StockItem.Category.choices)
    for row in rows:
        organization = organizations.setdefault(
            row["organization_id"],
            {"name": row["organization__name"], "items": {}},
        )
        item_key = (
            row["lot__stock_item__name"],
            row["lot__stock_item__category"],
            row["lot__stock_item__unit"],
        )
        item = organization["items"].setdefault(
            item_key,
            {
                "name": row["lot__stock_item__name"],
                "category": category_labels[row["lot__stock_item__category"]],
                "quantity": 0,
                "unit": row["lot__stock_item__unit"],
            },
        )
        item["quantity"] += row["remaining"]

    return JsonResponse(
        {
            "organizations": [
                {
                    "name": organization["name"],
                    "items": sorted(
                        organization["items"].values(),
                        key=lambda item: (item["name"], item["unit"]),
                    ),
                }
                for organization in organizations.values()
            ]
        }
    )


@group_required
def item_detail(request, pk):
    get_object_or_404(offers_with_availability(), pk=pk)
    return redirect("bichiku:offer_detail", pk=pk)


@group_required
def reservation_list(request):
    return redirect("bichiku:reservation_list")


@group_required
def contact_view(request):
    organization = request.organization
    initial = {
        "name": organization.name,
        "email": request.user.email,
    }
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.sender = request.user
            contact.save()
            messages.success(request, "お問い合わせを受け付けました。")
            return redirect("user_portal:contact_complete")
    else:
        form = ContactForm(initial=initial)
    return render(request, "user_portal/contact.html", {"form": form})


@group_required
def contact_complete(request):
    return render(request, "user_portal/contact_complete.html")


@login_required
def notification_redirect(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    if notification.related_reservation_id:
        if notification.type == Notification.Type.MESSAGE:
            conversation = Conversation.objects.filter(
                reservation_id=notification.related_reservation_id
            ).first()
            if conversation:
                return redirect(
                    "bichiku:conversation_detail", conversation_id=conversation.pk
                )
        return redirect("bichiku:reservation_list")
    return redirect("bichiku:notification_list")

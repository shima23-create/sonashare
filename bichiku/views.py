from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    AccountPasswordChangeForm,
    MessageForm,
    OrganizationProfileForm,
    StockLotForm,
)
from .models import (
    Conversation,
    EXPIRY_WARNING_DAYS,
    Message,
    Organization,
    PickupRecord,
    Profile,
    Reservation,
    StockItem,
    StockLot,
)


def _inventory_lots_for(user):
    return (
        StockLot.objects.select_related("stock_item")
        .filter(stock_item__organization__members__user=user)
        .order_by("expiration_date", "stock_item__name")
    )


def index(request):
    return render(request, "bichiku/index.html")


@login_required
def item_list(request):
    inventory_lots = _inventory_lots_for(request.user)
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    expiry = request.GET.get("expiry", "")
    status = request.GET.get("status", "")

    if query:
        inventory_lots = inventory_lots.filter(
            Q(stock_item__name__icontains=query)
            | Q(stock_item__notes__icontains=query)
            | Q(lot_number__icontains=query)
            | Q(storage_place__icontains=query)
        )
    if category in StockItem.Category.values:
        inventory_lots = inventory_lots.filter(stock_item__category=category)
    if status in StockLot.Availability.values:
        inventory_lots = inventory_lots.filter(availability=status)

    today = timezone.localdate()
    if expiry == "expired":
        inventory_lots = inventory_lots.filter(expiration_date__lt=today)
    elif expiry == "warning":
        inventory_lots = inventory_lots.filter(
            expiration_date__gte=today,
            expiration_date__lte=today + timedelta(days=EXPIRY_WARNING_DAYS),
        )
    elif expiry == "ok":
        inventory_lots = inventory_lots.filter(
            expiration_date__gt=today + timedelta(days=EXPIRY_WARNING_DAYS)
        )

    if request.method == "POST":
        form = StockLotForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                try:
                    organization = request.user.profile.organization
                except Profile.DoesNotExist:
                    organization = Organization.objects.create(
                        name=request.user.first_name or request.user.get_username(),
                        account_type=Organization.AccountType.COMPANY,
                    )
                    Profile.objects.create(
                        user=request.user,
                        organization=organization,
                    )

                stock_item = StockItem.objects.create(
                    organization=organization,
                    name=form.cleaned_data["name"],
                    category=form.cleaned_data["category"],
                    unit=form.cleaned_data["unit"],
                    notes=form.cleaned_data["notes"],
                )
                StockLot.objects.create(
                    stock_item=stock_item,
                    quantity=form.cleaned_data["quantity"],
                    expiration_date=form.cleaned_data["expiration_date"],
                    storage_place=form.cleaned_data["storage_place"],
                    availability=form.cleaned_data["availability"],
                )

            return redirect("bichiku:item_list")
        show_register_form = True
    else:
        form = StockLotForm()
        show_register_form = request.GET.get("register") == "1"

    return render(
        request,
        "bichiku/items.html",
        {
            "form": form,
            "show_register_form": show_register_form,
            "inventory_lots": inventory_lots,
        },
    )


@login_required
def item_detail(request, lot_id):
    lot = get_object_or_404(
        _inventory_lots_for(request.user).select_related("stock_item__organization"),
        pk=lot_id,
    )
    return render(
        request,
        "bichiku/items.html",
        {
            "form": StockLotForm(),
            "inventory_lots": _inventory_lots_for(request.user),
            "detail_lot": lot,
        },
    )


@login_required
def item_edit(request, lot_id):
    lot = get_object_or_404(
        _inventory_lots_for(request.user).select_related("stock_item"),
        pk=lot_id,
    )
    item = lot.stock_item
    initial = {
        "name": item.name,
        "category": item.category,
        "quantity": lot.quantity,
        "unit": item.unit,
        "expiration_date": lot.expiration_date,
        "storage_place": lot.storage_place,
        "availability": lot.availability,
        "notes": item.notes,
    }

    if request.method == "POST":
        form = StockLotForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                item.name = form.cleaned_data["name"]
                item.category = form.cleaned_data["category"]
                item.unit = form.cleaned_data["unit"]
                item.notes = form.cleaned_data["notes"]
                item.save()

                lot.quantity = form.cleaned_data["quantity"]
                lot.expiration_date = form.cleaned_data["expiration_date"]
                lot.storage_place = form.cleaned_data["storage_place"]
                lot.availability = form.cleaned_data["availability"]
                lot.save()

            return redirect("bichiku:item_list")
    else:
        form = StockLotForm(initial=initial)

    return render(
        request,
        "bichiku/items.html",
        {
            "form": form,
            "show_register_form": True,
            "is_edit": True,
            "edit_lot": lot,
            "inventory_lots": _inventory_lots_for(request.user),
        },
    )


@login_required
def item_delete(request, lot_id):
    if request.method != "POST":
        return redirect("bichiku:item_list")

    lot = get_object_or_404(
        _inventory_lots_for(request.user).select_related("stock_item"),
        pk=lot_id,
    )
    item = lot.stock_item

    try:
        with transaction.atomic():
            lot.delete()
            if not item.lots.exists():
                item.delete()
    except ProtectedError:
        messages.error(
            request,
            "提供募集や予約があるため削除できません。先に関連する募集・予約をご確認ください。",
        )

    return redirect("bichiku:item_list")


def dashboard(request):
    recent_conversations = []
    if request.user.is_authenticated:
        conversations, organization = _conversations_for(request.user)
        for conversation in conversations[:3]:
            conversation_messages = list(conversation.messages.all())
            if conversation.reservation.organization_id == organization.pk:
                other_organization = conversation.reservation.offer.organization
            else:
                other_organization = conversation.reservation.organization
            recent_conversations.append(
                {
                    "conversation": conversation,
                    "other_organization": other_organization,
                    "last_message": (
                        conversation_messages[-1] if conversation_messages else None
                    ),
                }
            )
    return render(
        request,
        "bichiku/dashboard.html",
        {"recent_conversations": recent_conversations},
    )


@login_required
def reservation_list(request):
    return render(request, "bichiku/reservations.html")


@login_required
def performance_analysis(request):
    try:
        organization = request.user.profile.organization
    except Profile.DoesNotExist:
        return render(
            request,
            "bichiku/performance_analysis.html",
            {"has_organization": False},
        )

    today = timezone.localdate()
    current_month_index = today.year * 12 + today.month - 1
    month_starts = []
    for offset in range(11, -1, -1):
        year, month_index = divmod(current_month_index - offset, 12)
        month_starts.append(today.replace(year=year, month=month_index + 1, day=1))
    period_start = month_starts[0]

    organization_reservations = Reservation.objects.filter(
        Q(organization=organization) | Q(offer__organization=organization)
    )
    successful_pickups = PickupRecord.objects.filter(
        Q(reservation__organization=organization)
        | Q(reservation__offer__organization=organization),
        pickup_status__in=(
            PickupRecord.PickupStatus.COMPLETED,
            PickupRecord.PickupStatus.PARTIAL,
        ),
        received_quantity__gt=0,
        picked_up_at__date__gte=period_start,
        picked_up_at__date__lte=today,
    )

    monthly_counts = {
        (row["month"].year, row["month"].month): row["count"]
        for row in successful_pickups.annotate(
            month=TruncMonth("picked_up_at")
        ).values("month").annotate(count=Count("pk"))
    }
    monthly_activity = [
        {
            "month": month,
            "count": monthly_counts.get((month.year, month.month), 0),
        }
        for month in month_starts
    ]
    max_monthly_count = max((row["count"] for row in monthly_activity), default=0)
    for row in monthly_activity:
        row["bar_percent"] = (
            round(row["count"] / max_monthly_count * 100)
            if max_monthly_count
            else 0
        )

    category_labels = dict(StockItem.Category.choices)
    category_field = "reservation__offer__lot__stock_item__category"
    unit_field = "reservation__offer__lot__stock_item__unit"
    category_activity = []
    for row in (
        successful_pickups.values(category_field, unit_field)
        .annotate(
            quantity=Sum("received_quantity"),
            item_count=Count("reservation__offer__lot__stock_item", distinct=True),
        )
        .order_by(category_field)
    ):
        category_activity.append(
            {
                "category": category_labels[row[category_field]],
                "unit": row[unit_field],
                "quantity": row["quantity"],
                "item_count": row["item_count"],
            }
        )

    quantity_by_unit = list(
        successful_pickups.values(
            "reservation__offer__lot__stock_item__unit"
        )
        .annotate(quantity=Sum("received_quantity"))
        .order_by("reservation__offer__lot__stock_item__unit")
    )
    for row in quantity_by_unit:
        row["unit"] = row.pop("reservation__offer__lot__stock_item__unit")

    partner_organization_field = (
        "reservation__organization"
        if organization.is_company
        else "reservation__offer__organization"
    )
    partner_organization_count = (
        successful_pickups.values(partner_organization_field)
        .distinct()
        .count()
    )

    reservation_status_labels = dict(Reservation.Status.choices)
    reservation_status_activity = [
        {
            "label": reservation_status_labels[row["status"]],
            "count": row["count"],
        }
        for row in organization_reservations.filter(
            created_at__date__gte=period_start,
            created_at__date__lte=today,
        )
        .values("status")
        .annotate(count=Count("pk"))
        .order_by("status")
    ]
    total_pickup_count = successful_pickups.count()

    return render(
        request,
        "bichiku/performance_analysis.html",
        {
            "has_organization": True,
            "period_start": period_start,
            "today": today,
            "monthly_activity": monthly_activity,
            "category_activity": category_activity,
            "quantity_by_unit": quantity_by_unit,
            "total_pickup_count": total_pickup_count,
            "unique_item_count": sum(
                row["item_count"] for row in category_activity
            ),
            "partner_organization_count": partner_organization_count,
            "reservation_status_activity": reservation_status_activity,
        },
    )


def _conversations_for(user):
    try:
        organization = user.profile.organization
    except Profile.DoesNotExist:
        return Conversation.objects.none(), None

    conversations = (
        Conversation.objects.filter(
            Q(reservation__organization=organization)
            | Q(reservation__offer__organization=organization)
        )
        .select_related(
            "reservation__organization",
            "reservation__offer__organization",
        )
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__is_read=False)
                & ~Q(messages__sender__profile__organization=organization),
            )
        )
        .prefetch_related(
            Prefetch(
                "messages",
                queryset=Message.objects.select_related("sender").order_by(
                    "created_at"
                ),
            )
        )
        .distinct()
    )
    return conversations, organization


@login_required
def messages_view(request, conversation_id=None):
    conversations, organization = _conversations_for(request.user)
    conversation = None
    if conversation_id is not None:
        conversation = get_object_or_404(conversations, pk=conversation_id)

    form = MessageForm()
    if request.method == "POST":
        if conversation is None:
            return redirect("bichiku:messages")
        form = MessageForm(request.POST)
        if form.is_valid():
            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=form.cleaned_data["content"],
            )
            conversation.save(update_fields=["updated_at"])
            return redirect(
                "bichiku:conversation_detail", conversation_id=conversation.pk
            )

    if conversation is not None and request.method == "GET":
        conversation.messages.filter(is_read=False).exclude(
            sender=request.user
        ).update(is_read=True)

    conversation_rows = []
    for item in conversations:
        conversation_messages = list(item.messages.all())
        last_message = conversation_messages[-1] if conversation_messages else None
        other_organization = (
            item.reservation.offer.organization
            if item.reservation.organization_id == getattr(
                organization, "pk", None
            )
            else item.reservation.organization
        )
        conversation_rows.append(
            {
                "conversation": item,
                "other_organization": other_organization,
                "last_message": last_message,
                "unread_count": item.unread_count,
            }
        )

    active_row = next(
        (
            row
            for row in conversation_rows
            if conversation is not None
            and row["conversation"].pk == conversation.pk
        ),
        None,
    )
    return render(
        request,
        "bichiku/messages.html",
        {
            "conversation_rows": conversation_rows,
            "active_row": active_row,
            "form": form,
        },
    )


@login_required
def my_page(request):
    try:
        profile = Profile.objects.select_related("organization").get(
            user=request.user
        )
    except Profile.DoesNotExist:
        profile = None

    edit_mode = request.GET.get("edit") == "1"
    organization_form = (
        OrganizationProfileForm(instance=profile.organization)
        if profile
        else None
    )
    password_form = AccountPasswordChangeForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "organization" and profile:
            organization_form = OrganizationProfileForm(
                request.POST, instance=profile.organization
            )
            if organization_form.is_valid():
                organization_form.save()
                return redirect("bichiku:my_page")
            edit_mode = True
        elif action == "password":
            password_form = AccountPasswordChangeForm(
                user=request.user, data=request.POST
            )
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, request.user)
                return redirect("bichiku:my_page")

    return render(
        request,
        "bichiku/my_page.html",
        {
            "profile": profile,
            "organization_form": organization_form,
            "password_form": password_form,
            "edit_mode": edit_mode,
        },
    )
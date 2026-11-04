from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Conversation,
    Message,
    Notification,
    Offer,
    Organization,
    PickupRecord,
    Profile,
    Reservation,
    StockItem,
    StockLot,
)

User = get_user_model()


# ---- ユーザー画面に「所属組織」を一緒に入力できるようにする ----
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = "所属組織"


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ---- 各モデル ----
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "account_type", "phone_number", "contact_person_name", "created_at")
    list_filter = ("account_type",)
    search_fields = ("name", "contact_person_name")


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "unit", "organization")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(StockLot)
class StockLotAdmin(admin.ModelAdmin):
    list_display = ("stock_item", "quantity", "expiration_date", "storage_place", "availability")
    list_filter = ("availability",)
    search_fields = ("stock_item__name", "lot_number")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "quantity", "status", "created_at")
    list_filter = ("status",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("offer", "organization", "reserved_quantity", "requested_pickup_at", "status")
    list_filter = ("status",)


@admin.register(PickupRecord)
class PickupRecordAdmin(admin.ModelAdmin):
    list_display = ("reservation", "received_quantity", "picked_up_at", "pickup_status")
    list_filter = ("pickup_status",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "reservation", "created_at", "updated_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender", "is_read", "created_at")
    list_filter = ("is_read",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "type", "is_read", "created_at")
    list_filter = ("type", "is_read")
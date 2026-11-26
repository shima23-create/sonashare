from django.contrib import admin

from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "category", "status", "created_at")
    list_filter = ("category", "status", "created_at")
    search_fields = ("subject", "name", "email", "body")
    readonly_fields = ("created_at", "updated_at")

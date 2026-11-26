from django.urls import path

from . import views

app_name = "user_portal"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("items/", views.item_list, name="item_list"),
    path("items/map-inventory/", views.map_inventory_search, name="map_inventory_search"),
    path("items/<int:pk>/", views.item_detail, name="item_detail"),
    path("reservations/", views.reservation_list, name="reservations"),
    path("contact/", views.contact_view, name="contact"),
    path("contact/complete/", views.contact_complete, name="contact_complete"),
    path("notifications/<int:pk>/", views.notification_redirect, name="notification_redirect"),
]

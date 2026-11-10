from django.urls import path
from . import views

app_name = "bichiku"

urlpatterns = [
    path("", views.index, name="index"),
    path("items/", views.item_list, name="item_list"),
    path("items/<int:lot_id>/", views.item_detail, name="item_detail"),
    path("items/<int:lot_id>/edit/", views.item_edit, name="item_edit"),
    path("items/<int:lot_id>/delete/", views.item_delete, name="item_delete"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("reservations/", views.reservation_list, name="reservation_list"),
    path("performance/", views.performance_analysis, name="performance_analysis"),
    path("messages/", views.messages_view, name="messages"),
    path(
        "messages/<int:conversation_id>/",
        views.messages_view,
        name="conversation_detail",
    ),
    path("my-page/", views.my_page, name="my_page"),
]
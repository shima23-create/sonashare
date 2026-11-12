from django.urls import path
from . import views
from . import offer_views

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
        path("offers/", offer_views.offer_list, name="offer_list"),
    path("offers/new/", offer_views.offer_create, name="offer_create"),
    path("offers/<int:pk>/edit/", offer_views.offer_edit, name="offer_edit"),
    path("offers/<int:pk>/publish/", offer_views.offer_publish, name="offer_publish"),
    path("offers/<int:pk>/close/", offer_views.offer_close, name="offer_close"),
    path("offers/<int:pk>/delete/", offer_views.offer_delete, name="offer_delete"),
    path("lots/<int:lot_id>/draft-offer/", offer_views.offer_draft_from_lot, name="offer_draft_from_lot"),
]
from django.urls import path
from . import views

app_name = "bichiku"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("items/", views.item_list, name="item_list"),
]
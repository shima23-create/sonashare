from django.urls import path
from . import views

app_name = "bichiku"

urlpatterns = [
    path("", views.index, name="index"),
    path("items/", views.item_list, name="item_list"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
]
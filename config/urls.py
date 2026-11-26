from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("user/", include("user_portal.urls")),
    path("", include("bichiku.urls")),
]
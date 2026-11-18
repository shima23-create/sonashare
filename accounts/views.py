from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from bichiku.access import get_organization

from .forms import LoginForm, SignUpForm


def _home_url_name(user):
    """ログイン後に最初に開く画面。団体(利用者)は「募集を探す」、企業はダッシュボード"""
    organization = get_organization(user)
    if organization is not None and not organization.is_company:
        return "bichiku:offer_browse"
    return "bichiku:dashboard"


def _next_url(request):
    """ログイン後に戻る先。同じサイト内のURLだけを許可する"""
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return ""


def signup_view(request):
    if request.user.is_authenticated:
        return redirect(_home_url_name(request.user))

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            authenticated_user = authenticate(
                request=request,
                username=user.get_username(),
                password=form.cleaned_data["password"],
            )
            if authenticated_user is not None:
                login(request, authenticated_user)
            return redirect(_home_url_name(user))
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_next_url(request) or _home_url_name(request.user))

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data["user"]
            login(request, user)
            return redirect(_next_url(request) or _home_url_name(user))
    else:
        form = LoginForm()

    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": _next_url(request)},
    )


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")
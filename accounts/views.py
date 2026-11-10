from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render

from .forms import LoginForm, SignUpForm


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("bichiku:dashboard")

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
            return redirect("bichiku:dashboard")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("bichiku:dashboard")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data["user"]
            login(request, user)
            return redirect("bichiku:dashboard")
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")

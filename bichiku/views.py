from django.shortcuts import render

def index(request):
    return render(request, "bichiku/index.html")

def item_list(request):
    return render(request, "bichiku/items.html")

def dashboard(request):
    return render(request, "bichiku/dashboard.html")

def login_view(request):
    return render(request, "bichiku/login.html")
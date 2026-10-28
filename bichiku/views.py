from django.shortcuts import render

def dashboard(request):
    return render(request, "bichiku/dashboard.html")

def item_list(request):
    return render(request, "bichiku/items.html")
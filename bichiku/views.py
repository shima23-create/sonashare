from django.shortcuts import render
from .models import Item

def item_list(request):
    items = Item.objects.all()
    return render(request, 'bichiku/item_list.html', {'items': items})

from django.http import HttpResponse

def hello(request):
    return HttpResponse("こんにちは!Djangoで追加したページです")
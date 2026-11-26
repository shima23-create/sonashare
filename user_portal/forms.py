from django import forms

from .models import Contact


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ("name", "email", "category", "subject", "body")
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
            "category": forms.Select(attrs={"class": "select"}),
            "subject": forms.TextInput(attrs={"class": "input"}),
            "body": forms.Textarea(attrs={"class": "input", "rows": 6}),
        }

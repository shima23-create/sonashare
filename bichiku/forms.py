from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.utils import timezone

from .models import Organization, StockItem, StockLot


class OrganizationProfileForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = (
            "name",
            "account_type",
            "address",
            "postal_code",
            "phone_number",
            "website_url",
            "notes",
            "contact_person_name",
            "department_name",
            "contact_person_phone",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "account_type": forms.Select(attrs={"class": "select"}),
            "address": forms.TextInput(attrs={"class": "input"}),
            "postal_code": forms.TextInput(attrs={"class": "input"}),
            "phone_number": forms.TextInput(attrs={"class": "input"}),
            "website_url": forms.URLInput(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 4}),
            "contact_person_name": forms.TextInput(attrs={"class": "input"}),
            "department_name": forms.TextInput(attrs={"class": "input"}),
            "contact_person_phone": forms.TextInput(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in (
            "address",
            "postal_code",
            "phone_number",
            "contact_person_name",
        ):
            self.fields[name].required = True
        self.fields["name"].label = "団体名"
        self.fields["account_type"].label = "団体種別"
        self.fields["address"].label = "所在地"
        self.fields["postal_code"].label = "郵便番号"
        self.fields["phone_number"].label = "電話番号"
        self.fields["website_url"].label = "Webサイト"
        self.fields["notes"].label = "団体紹介・活動内容"
        self.fields["contact_person_name"].label = "担当者名"
        self.fields["department_name"].label = "部署名"
        self.fields["contact_person_phone"].label = "担当者の電話番号"


class AccountPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "old_password": "現在のパスワード",
            "new_password1": "新しいパスワード",
            "new_password2": "新しいパスワード（確認用）",
        }
        placeholders = {
            "old_password": "現在のパスワード",
            "new_password1": "新しいパスワード",
            "new_password2": "新しいパスワード（確認用）",
        }
        for name, field in self.fields.items():
            field.label = labels[name]
            field.widget.attrs.update(
                {"class": "input", "placeholder": placeholders[name]}
            )


class MessageForm(forms.Form):
    content = forms.CharField(
        max_length=2000,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "class": "message-compose-input",
                "rows": 1,
                "placeholder": "メッセージを入力...",
                "aria-label": "メッセージ",
            }
        ),
    )


class StockLotForm(forms.Form):
    name = forms.CharField(
        label="備蓄品名",
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "input", "placeholder": "例：保存水（500ml）"}
        ),
    )
    category = forms.ChoiceField(
        label="カテゴリ",
        choices=StockItem.Category.choices,
        initial=StockItem.Category.DRINK,
        widget=forms.Select(attrs={"class": "select"}),
    )
    quantity = forms.IntegerField(
        label="数量",
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "input", "min": "0"}),
    )
    unit = forms.ChoiceField(
        label="単位",
        choices=(
            ("本", "本"),
            ("食", "食"),
            ("個", "個"),
            ("箱", "箱"),
            ("袋", "袋"),
            ("缶", "缶"),
            ("ケース", "ケース"),
        ),
        initial="本",
        widget=forms.Select(attrs={"class": "select"}),
    )
    expiration_date = forms.DateField(
        label="消費期限",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
    )
    storage_place = forms.CharField(
        label="保管場所",
        max_length=50,
        widget=forms.TextInput(
            attrs={"class": "input", "placeholder": "例：第1倉庫 A棚"}
        ),
    )
    availability = forms.ChoiceField(
        label="提供状況",
        choices=StockLot.Availability.choices,
        initial=StockLot.Availability.AVAILABLE,
        widget=forms.Select(attrs={"class": "select"}),
    )
    notes = forms.CharField(
        label="備考",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 4,
                "placeholder": "補足情報があれば入力してください",
            }
        ),
    )

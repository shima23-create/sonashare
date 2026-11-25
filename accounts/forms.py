from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
import re

from bichiku.models import PREFECTURES, Organization, Profile

from bichiku.models import Organization, Profile
from bichiku.access import get_organization

User = get_user_model()


class LoginForm(forms.Form):
    user_type = forms.ChoiceField(
        choices=(("company", "企業"), ("user", "利用者")),
        initial="company",
        required=True,
        label="利用者種別",
        widget=forms.RadioSelect(attrs={"class": "user-type-radio"}),
    )
    company_name = forms.CharField(
        label="団体・企業名（任意）",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "例：サンプル企業"}
        ),
    )
    email = forms.EmailField(
        label="メールアドレス",
        max_length=50,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "example@email.com"}
        ),
    )
    password = forms.CharField(
        label="パスワード",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "••••••"}
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            user = authenticate(request=None, username=email, password=password)
            if user is None or not user.is_active:
                raise forms.ValidationError(
                    "メールアドレスまたはパスワードが正しくありません。"
                )
                        # 選んだ利用者種別と、アカウントの種別が違うときは、案内を出す
            organization = get_organization(user)
            if organization is not None:
                chose_company = cleaned_data.get("user_type") == "company"
                if chose_company != organization.is_company:
                    raise forms.ValidationError(
                        "選んだ利用者種別が、このアカウントの種別と違います。"
                    )
            cleaned_data["user"] = user

        return cleaned_data


class SignUpForm(forms.Form):
    user_type = forms.ChoiceField(
        choices=(("company", "企業"), ("user", "利用者")),
        initial="company",
        required=True,
        label="利用者種別",
        widget=forms.RadioSelect(attrs={"class": "user-type-radio"}),
    )
    company_name = forms.CharField(
        label="団体・企業名",
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "例：さくら子ども食堂"}
        ),
    )
    email = forms.EmailField(
        label="メールアドレス",
        max_length=50,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "example@email.com"}
        ),
    )
    password = forms.CharField(
        label="パスワード",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "••••••"}
        ),
    )
    postal_code = forms.CharField(
        label="郵便番号",
        max_length=8,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "123-4567"}),
    )
    prefecture = forms.ChoiceField(
        label="都道府県",
        choices=[("", "選択してください")] + list(PREFECTURES),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    address = forms.CharField(
        label="所在地",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "例：○○市△△1-2-3"}),
    )
    phone_number = forms.CharField(
        label="電話番号",
        max_length=15,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "03-1234-5678"}),
    )
    contact_person_name = forms.CharField(
        label="担当者名",
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    contact_person_phone = forms.CharField(
        label="担当者の電話番号",
        max_length=15,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "090-1234-5678"}),
    )
    department_name = forms.CharField(
        label="部署名（任意）",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    website_url = forms.URLField(
        label="ウェブサイト（任意）",
        required=False,
        widget=forms.URLInput(attrs={"class": "form-control", "placeholder": "https://"}),
    )

    def clean_postal_code(self):
        value = self.cleaned_data["postal_code"].strip()
        if not re.fullmatch(r"\d{3}-?\d{4}", value):
            raise forms.ValidationError("郵便番号は 123-4567 の形式で入力してください。")
        return value

    def _clean_phone(self, field):
        value = self.cleaned_data[field].strip()
        if not re.fullmatch(r"\d{2,4}-?\d{2,4}-?\d{3,4}", value):
            raise forms.ValidationError("電話番号は 03-1234-5678 の形式で入力してください。")
        return value

    def clean_phone_number(self):
        return self._clean_phone("phone_number")

    def clean_contact_person_phone(self):
        return self._clean_phone("contact_person_phone")

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")

        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("このメールアドレスはすでに登録されています。")

        return cleaned_data

    @transaction.atomic
    def save(self):
        email = self.cleaned_data["email"]
        user_name = self.cleaned_data.get("company_name") or email.split("@", 1)[0]
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=user_name,
            password=self.cleaned_data["password"],
        )
        account_type = (
            Organization.AccountType.COMPANY
            if self.cleaned_data["user_type"] == "company"
            else Organization.AccountType.GROUP
        )
        organization = Organization.objects.create(
            name=user_name,
            account_type=account_type,
            postal_code=self.cleaned_data["postal_code"],
            prefecture=self.cleaned_data["prefecture"],
            address=self.cleaned_data["address"],
            phone_number=self.cleaned_data["phone_number"],
            contact_person_name=self.cleaned_data["contact_person_name"],
            contact_person_phone=self.cleaned_data["contact_person_phone"],
            department_name=self.cleaned_data["department_name"],
            website_url=self.cleaned_data["website_url"],
        )
        Profile.objects.create(user=user, organization=organization)
        return user
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction

from bichiku.models import Organization, Profile

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
        required=False,
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
        )
        Profile.objects.create(user=user, organization=organization)
        return user

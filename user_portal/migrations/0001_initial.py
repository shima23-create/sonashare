from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("bichiku", "0004_offer_prefecture_organization_prefecture"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Contact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, verbose_name="お名前")),
                ("email", models.EmailField(max_length=254, verbose_name="メールアドレス")),
                ("category", models.CharField(choices=[("general", "一般的なお問い合わせ"), ("reservation", "予約・受け渡しについて"), ("account", "アカウントについて"), ("bug", "不具合の報告"), ("other", "その他")], default="general", max_length=20, verbose_name="お問い合わせ種別")),
                ("subject", models.CharField(max_length=200, verbose_name="件名")),
                ("body", models.TextField(verbose_name="お問い合わせ内容")),
                ("status", models.CharField(choices=[("open", "未対応"), ("in_progress", "対応中"), ("closed", "対応済み")], default="open", max_length=20, verbose_name="対応状況")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="送信日時")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sender", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contacts", to=settings.AUTH_USER_MODEL, verbose_name="送信者")),
            ],
            options={
                "db_table": "user_portal_contact",
                "ordering": ["-created_at"],
                "verbose_name": "お問い合わせ",
                "verbose_name_plural": "お問い合わせ一覧",
            },
        ),
    ]

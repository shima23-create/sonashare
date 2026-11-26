from django.conf import settings
from django.db import models


class Contact(models.Model):
    class Category(models.TextChoices):
        GENERAL = "general", "一般的なお問い合わせ"
        RESERVATION = "reservation", "予約・受け渡しについて"
        ACCOUNT = "account", "アカウントについて"
        BUG = "bug", "不具合の報告"
        OTHER = "other", "その他"

    class Status(models.TextChoices):
        OPEN = "open", "未対応"
        IN_PROGRESS = "in_progress", "対応中"
        CLOSED = "closed", "対応済み"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="contacts",
        verbose_name="送信者",
        null=True,
        blank=True,
    )
    name = models.CharField("お名前", max_length=100)
    email = models.EmailField("メールアドレス", max_length=254)
    category = models.CharField(
        "お問い合わせ種別",
        max_length=20,
        choices=Category.choices,
        default=Category.GENERAL,
    )
    subject = models.CharField("件名", max_length=200)
    body = models.TextField("お問い合わせ内容")
    status = models.CharField(
        "対応状況",
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField("送信日時", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_portal_contact"
        ordering = ["-created_at"]
        verbose_name = "お問い合わせ"
        verbose_name_plural = "お問い合わせ一覧"

    def __str__(self):
        return self.subject

from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

# 消費期限が近いとみなす日数(画面の「期限間近」バッジの基準)
EXPIRY_WARNING_DAYS = 30

# 期限の状態 → (画面に出す文字, style.css のバッジのクラス名)
EXPIRY_STATUS_INFO = {
    "ok": ("正常", "badge-ok"),
    "warning": ("期限間近", "badge-warn"),
    "expired": ("期限切れ", "badge-danger"),
}


class TimeStampedModel(models.Model):
    """登録日時・更新日時を自動で持つ共通の親クラス(テーブルは作られません)"""

    created_at = models.DateTimeField("登録日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        abstract = True


# =========================================================
# ユーザーまわり
#   ログイン情報 … Django標準の User(メール・パスワード・有効状態など)
#   組織情報     … Organization(企業・活動団体)
#   つなぎ役     … Profile(1つの組織に、複数のユーザーが所属できる)
# =========================================================
class Organization(TimeStampedModel):
    """組織情報(企業・活動団体)。テーブル名: organizations"""

    class AccountType(models.IntegerChoices):
        COMPANY = 1, "企業"
        GROUP = 2, "活動団体"

    name = models.CharField("企業・団体名", max_length=100)
    account_type = models.IntegerField("アカウント種別", choices=AccountType.choices)
    postal_code = models.CharField("郵便番号", max_length=8, blank=True)
    address = models.CharField("所在地", max_length=200, blank=True)
    phone_number = models.CharField("電話番号", max_length=15, blank=True)
    website_url = models.URLField("ウェブサイト", max_length=200, blank=True)
    notes = models.TextField("企業紹介・備考", blank=True)
    contact_person_name = models.CharField("担当者名", max_length=50, blank=True)
    department_name = models.CharField("部署名", max_length=50, blank=True)
    contact_person_phone = models.CharField("担当者の電話番号", max_length=15, blank=True)

    class Meta:
        db_table = "organizations"
        verbose_name = "組織"
        verbose_name_plural = "組織"

    def __str__(self):
        return f"{self.name}({self.get_account_type_display()})"

    @property
    def is_company(self):
        return self.account_type == self.AccountType.COMPANY


class Profile(TimeStampedModel):
    """ユーザーと組織をつなぐ。1ユーザー = 1組織、1組織 = 複数ユーザー"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="ユーザー",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="members",
        verbose_name="所属組織",
    )

    class Meta:
        db_table = "profiles"
        verbose_name = "プロフィール"
        verbose_name_plural = "プロフィール"

    def __str__(self):
        return f"{self.user} @ {self.organization.name}"

    @property
    def account_type(self):
        return self.organization.account_type


# =========================================================
# 備蓄品
#   StockItem … 品名・カテゴリなど、共通の情報(1回だけ書く)
#   StockLot  … 入荷ごとに変わる情報(消費期限・数量・保管場所)
# =========================================================
class StockItem(TimeStampedModel):
    """備蓄品。テーブル名: stock_items"""

    class Category(models.TextChoices):
        STAPLE = "staple", "主食"
        DRINK = "drink", "飲料"
        CANNED = "canned", "缶詰"
        RETORT = "retort", "レトルト食品"
        OTHER = "other", "その他"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="stock_items",
        verbose_name="所有組織",
    )
    name = models.CharField("備蓄品名", max_length=100)
    category = models.CharField("カテゴリ", max_length=20, choices=Category.choices)
    unit = models.CharField("単位", max_length=10)
    notes = models.TextField("備考", blank=True)

    class Meta:
        db_table = "stock_items"
        verbose_name = "備蓄品"
        verbose_name_plural = "備蓄品"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockLot(TimeStampedModel):
    """備蓄品ロット。テーブル名: stock_lots"""

    class Availability(models.TextChoices):
        AVAILABLE = "available", "提供可能"
        RESERVED = "reserved", "予約中"
        PROVIDED = "provided", "提供済み"

    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.CASCADE,
        related_name="lots",
        verbose_name="備蓄品",
    )
    lot_number = models.CharField("ロット番号", max_length=50, blank=True)
    quantity = models.PositiveIntegerField("数量", default=0)
    expiration_date = models.DateField("消費期限")
    storage_place = models.CharField("保管場所", max_length=50)
    availability = models.CharField(
        "提供状況",
        max_length=20,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
    )

    class Meta:
        db_table = "stock_lots"
        verbose_name = "備蓄品ロット"
        verbose_name_plural = "備蓄品ロット"
        ordering = ["expiration_date"]

    def __str__(self):
        return f"{self.stock_item.name}({self.expiration_date})"

    # ---- 画面の「期限」バッジ用(保存せず、そのつど計算します) ----
    @property
    def expiry_status(self):
        today = timezone.localdate()
        if self.expiration_date < today:
            return "expired"
        if self.expiration_date <= today + timedelta(days=EXPIRY_WARNING_DAYS):
            return "warning"
        return "ok"

    @property
    def expiry_label(self):
        return EXPIRY_STATUS_INFO[self.expiry_status][0]

    @property
    def expiry_badge_class(self):
        return EXPIRY_STATUS_INFO[self.expiry_status][1]

    @property
    def availability_badge_class(self):
        return {
            self.Availability.AVAILABLE: "badge-available",
            self.Availability.RESERVED: "badge-reserved",
            self.Availability.PROVIDED: "badge-provided",
        }.get(self.availability, "badge-neutral")

    # ---- 数量の計算 ----
    @property
    def reserved_quantity(self):
        """予約中・承認済みで、まだ受け渡しが終わっていない数量の合計"""
        total = Reservation.objects.filter(
            offer__lot=self, status__in=Reservation.ACTIVE_STATUSES
        ).aggregate(total=Sum("reserved_quantity"))["total"]
        return total or 0

    @property
    def available_quantity(self):
        """予約を差し引いた、提供できる残り数量"""
        return max(self.quantity - self.reserved_quantity, 0)


# =========================================================
# 提供・予約・受け取り
# =========================================================
class Offer(TimeStampedModel):
    """提供情報(企業が公開する募集)。テーブル名: offers
    1つのロットを、複数回に分けて提供できます(ロット : 提供 = 1 : 多)。"""

    class Status(models.TextChoices):
        RECRUITING = "recruiting", "募集中"
        CLOSED = "closed", "募集終了"

    lot = models.ForeignKey(
        StockLot,
        on_delete=models.PROTECT,
        related_name="offers",
        verbose_name="ロット",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="offers",
        verbose_name="提供組織",
    )
    title = models.CharField("タイトル", max_length=100)
    description = models.TextField("説明", blank=True)
    quantity = models.PositiveIntegerField(
        "提供数量", validators=[MinValueValidator(1)]
    )
    pickup_location = models.CharField("受取場所", max_length=100)
    receiving_conditions = models.CharField("受取条件", max_length=200, blank=True)
    status = models.CharField(
        "募集状況",
        max_length=20,
        choices=Status.choices,
        default=Status.RECRUITING,
    )

    class Meta:
        db_table = "offers"
        verbose_name = "提供情報"
        verbose_name_plural = "提供情報"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Reservation(TimeStampedModel):
    """予約(活動団体が、提供情報に対して行う)。テーブル名: reservations"""

    class Status(models.TextChoices):
        PENDING = "pending", "予約中"
        APPROVED = "approved", "承認済み"
        CANCELLED = "cancelled", "キャンセル"
        COMPLETED = "completed", "受取完了"

    # 数量を押さえている(まだ受け渡しが終わっていない)状態
    ACTIVE_STATUSES = (Status.PENDING, Status.APPROVED)

    offer = models.ForeignKey(
        Offer,
        on_delete=models.PROTECT,
        related_name="reservations",
        verbose_name="提供情報",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="reservations",
        verbose_name="予約した団体",
    )
    reserved_quantity = models.PositiveIntegerField(
        "予約数量", default=1, validators=[MinValueValidator(1)]
    )
    requested_pickup_at = models.DateTimeField("希望受け取り日時")
    status = models.CharField(
        "ステータス",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    message = models.TextField("メッセージ", blank=True)

    class Meta:
        db_table = "reservations"
        verbose_name = "予約"
        verbose_name_plural = "予約"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.organization.name} → {self.offer.title}"


class PickupRecord(TimeStampedModel):
    """受け取り記録(受け渡し完了の履歴)。テーブル名: pickup_records
    一部ずつ受け取ることもあるため、予約 : 受け取り記録 = 1 : 多 です。"""

    class PickupStatus(models.TextChoices):
        COMPLETED = "completed", "受取完了"
        PARTIAL = "partial", "一部受取"
        NO_SHOW = "no_show", "受取なし"

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.PROTECT,
        related_name="pickup_records",
        verbose_name="予約",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pickup_records",
        verbose_name="受け取り担当ユーザー",
    )
    received_quantity = models.PositiveIntegerField("受取数量", default=0)
    picked_up_at = models.DateTimeField("受け取り日時")
    pickup_status = models.CharField(
        "受け取り状況", max_length=20, choices=PickupStatus.choices
    )
    notes = models.TextField("備考", blank=True)

    class Meta:
        db_table = "pickup_records"
        verbose_name = "受け取り記録"
        verbose_name_plural = "受け取り記録"
        ordering = ["-picked_up_at"]

    def __str__(self):
        return f"{self.reservation} ({self.get_pickup_status_display()})"


# =========================================================
# 会話・メッセージ・通知
# =========================================================
class Conversation(TimeStampedModel):
    """会話(予約ごとに1つ)。テーブル名: conversations
    やり取りする2つの組織は、予約から分かるため、列としては持ちません。"""

    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.CASCADE,
        related_name="conversation",
        verbose_name="予約",
    )

    class Meta:
        db_table = "conversations"
        verbose_name = "会話"
        verbose_name_plural = "会話"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"会話 #{self.pk}({self.reservation})"

    @property
    def provider_organization(self):
        """提供した側(企業)"""
        return self.reservation.offer.organization

    @property
    def requester_organization(self):
        """予約した側(活動団体)"""
        return self.reservation.organization


class Message(models.Model):
    """メッセージ。テーブル名: messages"""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="会話",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_messages",
        verbose_name="送信者",
    )
    content = models.TextField("メッセージ内容")
    is_read = models.BooleanField("既読", default=False)
    created_at = models.DateTimeField("送信日時", auto_now_add=True)

    class Meta:
        db_table = "messages"
        verbose_name = "メッセージ"
        verbose_name_plural = "メッセージ"
        ordering = ["created_at"]

    def __str__(self):
        return self.content[:20]


class Notification(models.Model):
    """通知。テーブル名: notifications"""

    class Type(models.TextChoices):
        RESERVATION = "reservation", "予約"
        MESSAGE = "message", "メッセージ"
        EXPIRY = "expiry", "消費期限"
        SYSTEM = "system", "お知らせ"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="通知先ユーザー",
    )
    title = models.CharField("タイトル", max_length=100)
    content = models.CharField("内容", max_length=255)
    type = models.CharField("種別", max_length=20, choices=Type.choices)
    is_read = models.BooleanField("既読", default=False)
    related_reservation = models.ForeignKey(
        Reservation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
        verbose_name="関連する予約",
    )
    created_at = models.DateTimeField("通知日時", auto_now_add=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "通知"
        verbose_name_plural = "通知"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
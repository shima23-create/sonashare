from datetime import timedelta

from django import forms
from django.db.models import Sum
from django.utils import timezone

from .models import PREFECTURES, Offer, Reservation, StockLot


# ---------------------------------------------------------
# 数量まわり
#
# 考え方: StockLot.quantity は「まだ募集に出していない残り数量」です。
#   - 募集を公開(募集中)にすると、その数量を StockLot.quantity から引きます。
#   - 募集を終了すると、予約されていない分を StockLot.quantity に戻します。
#   - 下書きは、数量を引きません。
# ---------------------------------------------------------
def _committed_quantity(offer):
    """その募集が、すでにロットから引いている数量(募集中のときだけ)"""
    if offer is None or not offer.pk:
        return 0
    return (
        Offer.objects.filter(pk=offer.pk, status=Offer.Status.RECRUITING)
        .values_list("quantity", flat=True)
        .first()
        or 0
    )


def offerable_quantity(lot, offer=None):
    """そのロットで、いま募集に出せる数量。
    募集中の募集を編集するときは、その募集がすでに引いている分も含みます。"""
    return lot.quantity + _committed_quantity(offer)


def reserved_quantity_of(offer):
    """その募集に入っている、予約中・承認済みの数量の合計"""
    if not offer.pk:
        return 0
    return (
        offer.reservations.filter(status__in=Reservation.ACTIVE_STATUSES).aggregate(
            total=Sum("reserved_quantity")
        )["total"]
        or 0
    )


def default_offer_values(lot):
    """期限が近い備蓄品から、募集の下書きを作るときの初期値"""
    today = timezone.localdate()
    quantity = offerable_quantity(lot)
    deadline = lot.expiration_date - timedelta(days=7)
    if deadline < today:
        deadline = lot.expiration_date
    return {
        "title": f"{lot.stock_item.name} {quantity}{lot.stock_item.unit}",
        "quantity": quantity,
        "pickup_location": lot.storage_place,
        "prefecture": lot.stock_item.organization.prefecture,
        "deadline": deadline,
    }


def publish_problems(offer):
    """公開(募集中にする)前に確認する内容。問題があれば、文章のリストを返す"""
    problems = []
    lot = offer.lot
    today = timezone.localdate()

    if lot.availability != StockLot.Availability.AVAILABLE:
        problems.append("このロットは、提供対象になっていません。備蓄品の登録内容を確認してください。")
    if lot.expiration_date < today:
        problems.append("消費期限が過ぎているため、募集できません。")
    if not offer.prefecture:
        problems.append("公開するには、受取場所の都道府県を選んでください。")
    if offer.deadline is None:
        problems.append("公開するには、募集締切日を入力してください。")
    elif offer.deadline < today:
        problems.append("募集締切日がすでに過ぎています。")

    remaining = offerable_quantity(lot, offer)
    if offer.quantity > remaining:
        problems.append(
            f"募集に出せる残り数量は {remaining}{lot.stock_item.unit} です。"
        )
    return problems


# ---------------------------------------------------------
# フォーム
# ---------------------------------------------------------
class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = [
            "lot",
            "title",
            "quantity",
            "pickup_location",
            "prefecture",
            "receiving_conditions",
            "description",
            "deadline",
        ]
        labels = {
            "lot": "提供する備蓄品(ロット)",
            "quantity": "提供数量",
        }
        help_texts = {
            "quantity": "公開すると、この数量が備蓄品の数量から差し引かれます。",
            "deadline": "消費期限より前の日付にしてください。",
            "receiving_conditions": "例:平日10時〜17時、事前連絡が必要 など",
        }
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "deadline": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

        if self.instance.pk:
            # 編集中は、ロットを変えられない
            lots = StockLot.objects.filter(pk=self.instance.lot_id)
            self.fields["lot"].disabled = True
        else:
            # 新規は、自分の組織の「提供対象」で、残りがあるロットだけ選べる
            lots = StockLot.objects.filter(
                stock_item__organization=organization,
                availability=StockLot.Availability.AVAILABLE,
                quantity__gt=0,
            )
        lots = lots.select_related("stock_item").order_by("expiration_date")
        self.fields["lot"].queryset = lots
        self.fields["lot"].empty_label = "ロットを選んでください"
        self.fields["lot"].label_from_instance = lambda lot: (
            f"{lot.stock_item.name}(期限 {lot.expiration_date:%Y年%m月%d日}"
            f"・残り{lot.quantity}{lot.stock_item.unit}・{lot.storage_place})"
        )

        # 受取場所の都道府県は必須。新規のときは、自分の組織の都道府県を初めから選んでおく
        self.fields["prefecture"].required = True
        self.fields["prefecture"].choices = [("", "都道府県を選んでください")] + list(PREFECTURES)
        if not self.instance.pk and not self.initial.get("prefecture"):
            self.initial["prefecture"] = organization.prefecture

        for field in self.fields.values():
            css = "select" if isinstance(field.widget, forms.Select) else "field-input"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        lot = cleaned.get("lot")
        quantity = cleaned.get("quantity")
        deadline = cleaned.get("deadline")

        if lot and quantity:
            limit = offerable_quantity(lot, self.instance)
            if quantity > limit:
                self.add_error(
                    "quantity",
                    f"残り数量({limit}{lot.stock_item.unit})を超えています。",
                )
            reserved = reserved_quantity_of(self.instance)
            if quantity < reserved:
                self.add_error(
                    "quantity",
                    f"すでに {reserved}{lot.stock_item.unit} の予約が入っているため、それより少なくできません。",
                )
        if lot and deadline and deadline > lot.expiration_date:
            self.add_error("deadline", "募集締切日は、消費期限以前の日付にしてください。")
        return cleaned
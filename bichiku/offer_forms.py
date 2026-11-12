from datetime import timedelta

from django import forms
from django.db.models import Sum
from django.utils import timezone

from .models import Offer, Reservation, StockLot


# ---------------------------------------------------------
# 数量まわり
# ---------------------------------------------------------
def offered_quantity(lot, exclude_offer=None):
    """そのロットで、すでに「募集中」になっている提供数量の合計"""
    offers = lot.offers.filter(status=Offer.Status.RECRUITING)
    if exclude_offer is not None and exclude_offer.pk:
        offers = offers.exclude(pk=exclude_offer.pk)
    return offers.aggregate(total=Sum("quantity"))["total"] or 0


def offerable_quantity(lot, exclude_offer=None):
    """そのロットで、あと何個まで募集に出せるか"""
    return max(lot.quantity - offered_quantity(lot, exclude_offer), 0)


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
    if offer.deadline is None:
        problems.append("公開するには、募集締切日を入力してください。")
    elif offer.deadline < today:
        problems.append("募集締切日がすでに過ぎています。")

    remaining = offerable_quantity(lot, exclude_offer=offer)
    if offer.quantity > remaining:
        problems.append(
            f"このロットで募集できる残りは {remaining}{lot.stock_item.unit} です"
            "(ほかの募集中の数量と合わせて、ロットの数量を超えないようにしてください)。"
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
            "receiving_conditions",
            "description",
            "deadline",
        ]
        labels = {
            "lot": "提供する備蓄品(ロット)",
            "quantity": "提供数量",
        }
        help_texts = {
            "quantity": "ロットの数量を超えない範囲で入力してください。",
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
            # 新規は、自分の組織の「提供対象」のロットだけ選べる
            lots = StockLot.objects.filter(
                stock_item__organization=organization,
                availability=StockLot.Availability.AVAILABLE,
            )
        lots = lots.select_related("stock_item").order_by("expiration_date")
        self.fields["lot"].queryset = lots
        self.fields["lot"].empty_label = "ロットを選んでください"
        self.fields["lot"].label_from_instance = lambda lot: (
            f"{lot.stock_item.name}(期限 {lot.expiration_date:%Y年%m月%d日}"
            f"・{lot.quantity}{lot.stock_item.unit}・{lot.storage_place})"
        )

        for field in self.fields.values():
            css = "select" if isinstance(field.widget, forms.Select) else "field-input"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        lot = cleaned.get("lot")
        quantity = cleaned.get("quantity")
        deadline = cleaned.get("deadline")

        if lot and quantity:
            if quantity > lot.quantity:
                self.add_error(
                    "quantity",
                    f"ロットの数量({lot.quantity}{lot.stock_item.unit})を超えています。",
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

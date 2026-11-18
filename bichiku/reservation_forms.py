from django import forms

from .reservation_services import remaining_quantity

PICKUP_FORMAT = "%Y-%m-%dT%H:%M"


class ReservationForm(forms.Form):
    quantity = forms.IntegerField(
        label="予約する数量",
        min_value=1,
        widget=forms.NumberInput(attrs={"min": 1, "class": "field-input"}),
    )
    requested_pickup_at = forms.DateTimeField(
        label="希望受け取り日時",
        input_formats=[PICKUP_FORMAT],
        widget=forms.DateTimeInput(
            format=PICKUP_FORMAT,
            attrs={"type": "datetime-local", "class": "field-input"},
        ),
    )
    message = forms.CharField(
        label="メッセージ(任意)",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={"rows": 3, "class": "field-input", "placeholder": "受け取り方法や、ご要望など"}
        ),
    )

    def __init__(self, *args, offer, **kwargs):
        super().__init__(*args, **kwargs)
        self.offer = offer
        self.remaining = remaining_quantity(offer)
        self.fields["quantity"].help_text = (
            f"残り {self.remaining}{offer.lot.stock_item.unit} まで予約できます。"
        )


class CompleteForm(forms.Form):
    received_quantity = forms.IntegerField(label="受け取った数量", min_value=1)

    def __init__(self, *args, reservation, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["received_quantity"].max_value = reservation.reserved_quantity
        self.reservation = reservation

    def clean_received_quantity(self):
        value = self.cleaned_data["received_quantity"]
        if value > self.reservation.reserved_quantity:
            raise forms.ValidationError(
                f"予約した数量({self.reservation.reserved_quantity})を超えています。"
            )
        return value
# 日付の加算に使う。消費期限の注意対象期間を計算する。
from datetime import timedelta

# 画面に表示する成功・エラー通知をリクエストに追加する。
from django.contrib import messages
# パスワード変更後も現在のログインセッションを有効に保つ。
from django.contrib.auth import update_session_auth_hash
# ログインしていない利用者によるビューへのアクセスを制限する。
from django.contrib.auth.decorators import login_required
# 複数のデータベース更新をまとめ、途中で失敗した場合に一括で取り消す。
from django.db import transaction
# 集計件数・関連データの先読み・複合条件検索・数量合計に使う。
from django.db.models import Count, Prefetch, Q, Sum
# 日時データを月単位にまとめ、月別の実績を集計する。
from django.db.models.functions import TruncMonth
# 関連データに保護されているレコードを削除しようとした場合の例外。
from django.db.models.deletion import ProtectedError
# レコード取得、画面遷移、テンプレート描画に使う。
from django.shortcuts import get_object_or_404, redirect, render
# タイムゾーンを考慮した現在日付を取得する。
from django.utils import timezone

# 各画面の入力値を検証し、データ保存用に整えるフォーム。
from .forms import (
    AccountPasswordChangeForm,
    MessageForm,
    OrganizationProfileForm,
    StockLotForm,
)
# 画面で使用する会話・メッセージ・団体・備蓄品などのデータモデル。
from .models import (
    Conversation,
    EXPIRY_WARNING_DAYS,
    Message,
    Organization,
    PickupRecord,
    Profile,
    Reservation,
    StockItem,
    StockLot,
)


def _inventory_lots_for(user):
    """ユーザーが所属する団体の備蓄ロットを、消費期限の近い順に取得する。

    備蓄ロットを所有団体のメンバーシップで絞り込むため、別の団体の在庫は
    一覧や詳細画面から参照できない。備蓄品本体も同時に取得し、一覧表示時の
    不要な追加データベースアクセスを抑える。

    Args:
        user: 在庫を閲覧するユーザー。

    Returns:
        所属団体の備蓄ロットを期限、備蓄品名の順に並べた QuerySet。
    """
    return (
        StockLot.objects.select_related("stock_item")
        .filter(stock_item__organization__members__user=user)
        .order_by("expiration_date", "stock_item__name")
    )


def index(request):
    """未ログイン利用者向けのサービス紹介ページを表示する。

    Args:
        request: Django の HTTP リクエスト。

    Returns:
        ログイン・新規登録への案内を含むトップページのレスポンス。
    """
    return render(request, "bichiku/index.html")


@login_required
def item_list(request):
    """ログイン中ユーザーの備蓄品一覧を表示し、検索と新規登録を処理する。

    GET パラメーターのキーワード、カテゴリ、消費期限、提供状態は、指定された
    条件をすべて満たすロットに一覧を絞り込む。POST の場合は入力フォームを
    検証し、備蓄品本体と在庫ロットを同じトランザクション内で登録する。
    ユーザーに団体プロフィールがまだない場合は、ユーザー名を使った企業団体と
    プロフィールも合わせて作成する。入力エラーがあればフォームを開いた状態で
    エラーを表示し、登録成功後は一覧へリダイレクトする。

    Args:
        request: 検索条件または新規備蓄品のフォームデータを含むリクエスト。

    Returns:
        絞り込み済み在庫一覧と登録フォームを表示するレスポンス、または
        登録成功後に一覧へ戻すリダイレクト。
    """
    inventory_lots = _inventory_lots_for(request.user)
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    expiry = request.GET.get("expiry", "")
    status = request.GET.get("status", "")

    if query:
        inventory_lots = inventory_lots.filter(
            Q(stock_item__name__icontains=query)
            | Q(stock_item__notes__icontains=query)
            | Q(lot_number__icontains=query)
            | Q(storage_place__icontains=query)
        )
    if category in StockItem.Category.values:
        inventory_lots = inventory_lots.filter(stock_item__category=category)
    if status in StockLot.Availability.values:
        inventory_lots = inventory_lots.filter(availability=status)

    today = timezone.localdate()
    if expiry == "expired":
        inventory_lots = inventory_lots.filter(expiration_date__lt=today)
    elif expiry == "warning":
        inventory_lots = inventory_lots.filter(
            expiration_date__gte=today,
            expiration_date__lte=today + timedelta(days=EXPIRY_WARNING_DAYS),
        )
    elif expiry == "ok":
        inventory_lots = inventory_lots.filter(
            expiration_date__gt=today + timedelta(days=EXPIRY_WARNING_DAYS)
        )

    if request.method == "POST":
        form = StockLotForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                try:
                    organization = request.user.profile.organization
                except Profile.DoesNotExist:
                    organization = Organization.objects.create(
                        name=request.user.first_name or request.user.get_username(),
                        account_type=Organization.AccountType.COMPANY,
                    )
                    Profile.objects.create(
                        user=request.user,
                        organization=organization,
                    )

                stock_item = StockItem.objects.create(
                    organization=organization,
                    name=form.cleaned_data["name"],
                    category=form.cleaned_data["category"],
                    unit=form.cleaned_data["unit"],
                    notes=form.cleaned_data["notes"],
                )
                StockLot.objects.create(
                    stock_item=stock_item,
                    quantity=form.cleaned_data["quantity"],
                    expiration_date=form.cleaned_data["expiration_date"],
                    storage_place=form.cleaned_data["storage_place"],
                    availability=form.cleaned_data["availability"],
                )

            return redirect("bichiku:item_list")
        show_register_form = True
    else:
        form = StockLotForm()
        show_register_form = request.GET.get("register") == "1"

    return render(
        request,
        "bichiku/items.html",
        {
            "form": form,
            "show_register_form": show_register_form,
            "inventory_lots": inventory_lots,
        },
    )


@login_required
def item_detail(request, lot_id):
    """所属団体が所有する指定ロットの詳細を備蓄品一覧ページ内に表示する。

    ロットは現在のユーザーの所属団体に限定して検索する。そのため、別団体の
    ロット ID が指定された場合も、存在しない場合と同じ 404 を返す。

    Args:
        request: Django の HTTP リクエスト。
        lot_id: 詳細を表示する備蓄ロットの ID。

    Returns:
        詳細ロットを含む備蓄品一覧ページのレスポンス。
    """
    lot = get_object_or_404(
        _inventory_lots_for(request.user).select_related("stock_item__organization"),
        pk=lot_id,
    )
    return render(
        request,
        "bichiku/items.html",
        {
            "form": StockLotForm(),
            "inventory_lots": _inventory_lots_for(request.user),
            "detail_lot": lot,
        },
    )


@login_required
def item_edit(request, lot_id):
    """所属団体の備蓄品とロット情報をフォームから編集する。

    GET では現在の備蓄品名・カテゴリ・単位・メモと、ロットの数量・期限・保管
    場所・提供状態をフォームに設定する。POST の入力が有効なら両方のレコードを
    同じトランザクション内で更新する。入力エラーの場合はエラー内容と編集対象を
    フォームに表示する。対象は所属団体のロットに限定し、他団体の在庫は編集
    できない。

    Args:
        request: 編集フォームの表示または送信を行うリクエスト。
        lot_id: 編集する備蓄ロットの ID。

    Returns:
        編集フォームを含む一覧ページのレスポンス、または更新後の一覧への
        リダイレクト。
    """
    lot = get_object_or_404(
        _inventory_lots_for(request.user).select_related("stock_item"),
        pk=lot_id,
    )
    item = lot.stock_item
    initial = {
        "name": item.name,
        "category": item.category,
        "quantity": lot.quantity,
        "unit": item.unit,
        "expiration_date": lot.expiration_date,
        "storage_place": lot.storage_place,
        "availability": lot.availability,
        "notes": item.notes,
    }

    if request.method == "POST":
        form = StockLotForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                item.name = form.cleaned_data["name"]
                item.category = form.cleaned_data["category"]
                item.unit = form.cleaned_data["unit"]
                item.notes = form.cleaned_data["notes"]
                item.save()

                lot.quantity = form.cleaned_data["quantity"]
                lot.expiration_date = form.cleaned_data["expiration_date"]
                lot.storage_place = form.cleaned_data["storage_place"]
                lot.availability = form.cleaned_data["availability"]
                lot.save()

            return redirect("bichiku:item_list")
    else:
        form = StockLotForm(initial=initial)

    return render(
        request,
        "bichiku/items.html",
        {
            "form": form,
            "show_register_form": True,
            "is_edit": True,
            "edit_lot": lot,
            "inventory_lots": _inventory_lots_for(request.user),
        },
    )


@login_required
def item_delete(request, lot_id):
    """所属団体の備蓄ロットを削除し、他のデータから保護されている場合は通知する。

    削除操作は POST のみ受け付ける。ロット削除後に同じ備蓄品にロットが残って
    いなければ備蓄品本体も削除する。提供募集や予約が関連して削除できない場合は
    トランザクションを取り消し、利用者に理由を知らせる。

    Args:
        request: 削除操作を送信するリクエスト。
        lot_id: 削除する備蓄ロットの ID。

    Returns:
        備蓄品一覧へのリダイレクト。
    """
    if request.method != "POST":
        return redirect("bichiku:item_list")

    lot = get_object_or_404(
        _inventory_lots_for(request.user).select_related("stock_item"),
        pk=lot_id,
    )
    item = lot.stock_item

    try:
        with transaction.atomic():
            lot.delete()
            if not item.lots.exists():
                item.delete()
    except ProtectedError:
        messages.error(
            request,
            "提供募集や予約があるため削除できません。先に関連する募集・予約をご確認ください。",
        )

    return redirect("bichiku:item_list")


def dashboard(request):
    """備蓄品の状況と、ログインユーザーに関係する最近の会話を表示する。

    ログイン中の場合は、所属団体が参加する会話から最大 3 件を取得し、相手の
    団体名と最新メッセージを画面表示用データにまとめる。未ログインの場合は
    会話欄を空にしてダッシュボードを表示する。

    Args:
        request: ログイン状態を含む Django の HTTP リクエスト。

    Returns:
        最近の会話一覧を含むダッシュボードのレスポンス。
    """
    recent_conversations = []
    if request.user.is_authenticated:
        conversations, organization = _conversations_for(request.user)
        for conversation in conversations[:3]:
            conversation_messages = list(conversation.messages.all())
            if conversation.reservation.organization_id == organization.pk:
                other_organization = conversation.reservation.offer.organization
            else:
                other_organization = conversation.reservation.organization
            recent_conversations.append(
                {
                    "conversation": conversation,
                    "other_organization": other_organization,
                    "last_message": (
                        conversation_messages[-1] if conversation_messages else None
                    ),
                }
            )
    return render(
        request,
        "bichiku/dashboard.html",
        {"recent_conversations": recent_conversations},
    )


@login_required
def reservation_list(request):
    """予約一覧ページを表示する。

    URL のアクセス制御は login_required が行う。予約データの表示や操作は
    共通テンプレート側で行う。

    Args:
        request: ログイン済みユーザーからの Django HTTP リクエスト。

    Returns:
        予約一覧ページのレスポンス。
    """
    return render(request, "bichiku/reservations.html")


@login_required
def performance_analysis(request):
    """所属団体の直近12か月分の受取実績と予約状況を集計して表示する。

    受取済みまたは一部受取の記録のうち、実際の受取数量が 0 より大きいものを
    集計対象にする。月別件数、カテゴリ・単位別の受取数量、受取した備蓄品数、
    取引した相手団体数、予約ステータス別件数を画面表示用にまとめる。数量の
    重量換算や CO₂ 削減量など、記録にない値の推定は行わない。

    まだ団体プロフィールがないユーザーには、集計値ではなく団体未登録の状態を
    テンプレートへ渡す。

    Args:
        request: 集計対象となるログイン済みユーザーのリクエスト。

    Returns:
        集計結果または団体未登録状態を含む実績分析ページのレスポンス。
    """
    try:
        organization = request.user.profile.organization
    except Profile.DoesNotExist:
        return render(
            request,
            "bichiku/performance_analysis.html",
            {"has_organization": False},
        )

    today = timezone.localdate()
    current_month_index = today.year * 12 + today.month - 1
    month_starts = []
    for offset in range(11, -1, -1):
        year, month_index = divmod(current_month_index - offset, 12)
        month_starts.append(today.replace(year=year, month=month_index + 1, day=1))
    period_start = month_starts[0]

    organization_reservations = Reservation.objects.filter(
        Q(organization=organization) | Q(offer__organization=organization)
    )
    successful_pickups = PickupRecord.objects.filter(
        Q(reservation__organization=organization)
        | Q(reservation__offer__organization=organization),
        pickup_status__in=(
            PickupRecord.PickupStatus.COMPLETED,
            PickupRecord.PickupStatus.PARTIAL,
        ),
        received_quantity__gt=0,
        picked_up_at__date__gte=period_start,
        picked_up_at__date__lte=today,
    )

    monthly_counts = {
        (row["month"].year, row["month"].month): row["count"]
        for row in successful_pickups.annotate(
            month=TruncMonth("picked_up_at")
        ).values("month").annotate(count=Count("pk"))
    }
    monthly_activity = [
        {
            "month": month,
            "count": monthly_counts.get((month.year, month.month), 0),
        }
        for month in month_starts
    ]
    max_monthly_count = max((row["count"] for row in monthly_activity), default=0)
    for row in monthly_activity:
        row["bar_percent"] = (
            round(row["count"] / max_monthly_count * 100)
            if max_monthly_count
            else 0
        )

    category_labels = dict(StockItem.Category.choices)
    category_field = "reservation__offer__lot__stock_item__category"
    unit_field = "reservation__offer__lot__stock_item__unit"
    category_activity = []
    for row in (
        successful_pickups.values(category_field, unit_field)
        .annotate(
            quantity=Sum("received_quantity"),
            item_count=Count("reservation__offer__lot__stock_item", distinct=True),
        )
        .order_by(category_field)
    ):
        category_activity.append(
            {
                "category": category_labels[row[category_field]],
                "unit": row[unit_field],
                "quantity": row["quantity"],
                "item_count": row["item_count"],
            }
        )

    quantity_by_unit = list(
        successful_pickups.values(
            "reservation__offer__lot__stock_item__unit"
        )
        .annotate(quantity=Sum("received_quantity"))
        .order_by("reservation__offer__lot__stock_item__unit")
    )
    for row in quantity_by_unit:
        row["unit"] = row.pop("reservation__offer__lot__stock_item__unit")

    partner_organization_field = (
        "reservation__organization"
        if organization.is_company
        else "reservation__offer__organization"
    )
    partner_organization_count = (
        successful_pickups.values(partner_organization_field)
        .distinct()
        .count()
    )

    reservation_status_labels = dict(Reservation.Status.choices)
    reservation_status_activity = [
        {
            "label": reservation_status_labels[row["status"]],
            "count": row["count"],
        }
        for row in organization_reservations.filter(
            created_at__date__gte=period_start,
            created_at__date__lte=today,
        )
        .values("status")
        .annotate(count=Count("pk"))
        .order_by("status")
    ]
    total_pickup_count = successful_pickups.count()

    return render(
        request,
        "bichiku/performance_analysis.html",
        {
            "has_organization": True,
            "period_start": period_start,
            "today": today,
            "monthly_activity": monthly_activity,
            "category_activity": category_activity,
            "quantity_by_unit": quantity_by_unit,
            "total_pickup_count": total_pickup_count,
            "unique_item_count": sum(
                row["item_count"] for row in category_activity
            ),
            "partner_organization_count": partner_organization_count,
            "reservation_status_activity": reservation_status_activity,
        },
    )


def _conversations_for(user):
    """ユーザーの所属団体が参加する会話を、画面表示に必要な情報とともに取得する。

    予約した団体または提供元の団体のいずれかがユーザーの所属先である会話に
    限定する。各会話には、自分の団体以外の相手が送った未読メッセージ数を付け、
    予約の両団体と、送信者・作成日時順のメッセージをあらかじめ読み込む。
    団体プロフィールがないユーザーには空の QuerySet と None を返す。

    Args:
        user: 会話一覧を取得するユーザー。

    Returns:
        (会話 QuerySet, 所属団体) の組。団体未登録の場合は
        (空の QuerySet, None)。
    """
    try:
        organization = user.profile.organization
    except Profile.DoesNotExist:
        return Conversation.objects.none(), None

    conversations = (
        Conversation.objects.filter(
            Q(reservation__organization=organization)
            | Q(reservation__offer__organization=organization)
        )
        .select_related(
            "reservation__organization",
            "reservation__offer__organization",
        )
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__is_read=False)
                & ~Q(messages__sender__profile__organization=organization),
            )
        )
        .prefetch_related(
            Prefetch(
                "messages",
                queryset=Message.objects.select_related("sender").order_by(
                    "created_at"
                ),
            )
        )
        .distinct()
    )
    return conversations, organization


@login_required
def messages_view(request, conversation_id=None):
    """会話一覧または指定会話を表示し、送信・既読更新を処理する。

    conversation_id がある場合は、所属団体が参加する会話か確認して詳細を表示
    する。POST で有効なメッセージが送信されたらログインユーザーを送信者として
    保存し、会話の更新日時を更新して詳細へ戻す。GET で会話詳細を開いた場合は、
    他のユーザーが送った未読メッセージを既読にする。

    一覧用には各会話の相手団体、最新メッセージ、未読数をまとめ、選択中の会話を
    active_row としてテンプレートへ渡す。会話を指定しない POST は一覧へ戻す。

    Args:
        request: メッセージ送信フォームまたはページ表示のリクエスト。
        conversation_id: 詳細を表示する会話の ID。省略時は会話一覧を表示する。

    Returns:
        会話一覧・詳細ページのレスポンス、または送信後の会話詳細へのリダイレクト。
    """
    conversations, organization = _conversations_for(request.user)
    conversation = None
    if conversation_id is not None:
        conversation = get_object_or_404(conversations, pk=conversation_id)

    form = MessageForm()
    if request.method == "POST":
        if conversation is None:
            return redirect("bichiku:messages")
        form = MessageForm(request.POST)
        if form.is_valid():
            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=form.cleaned_data["content"],
            )
            conversation.save(update_fields=["updated_at"])
            return redirect(
                "bichiku:conversation_detail", conversation_id=conversation.pk
            )

    if conversation is not None and request.method == "GET":
        conversation.messages.filter(is_read=False).exclude(
            sender=request.user
        ).update(is_read=True)

    conversation_rows = []
    for item in conversations:
        conversation_messages = list(item.messages.all())
        last_message = conversation_messages[-1] if conversation_messages else None
        other_organization = (
            item.reservation.offer.organization
            if item.reservation.organization_id == getattr(
                organization, "pk", None
            )
            else item.reservation.organization
        )
        conversation_rows.append(
            {
                "conversation": item,
                "other_organization": other_organization,
                "last_message": last_message,
                "unread_count": item.unread_count,
            }
        )

    active_row = next(
        (
            row
            for row in conversation_rows
            if conversation is not None
            and row["conversation"].pk == conversation.pk
        ),
        None,
    )
    return render(
        request,
        "bichiku/messages.html",
        {
            "conversation_rows": conversation_rows,
            "active_row": active_row,
            "form": form,
        },
    )


@login_required
def my_page(request):
    """マイページを表示し、団体情報とログインパスワードの変更を処理する。

    団体プロフィールがあれば団体情報フォームを表示し、GET の edit=1 が指定
    された場合は編集モードで開く。POST の action に応じて団体情報または
    パスワードのフォームを検証・保存する。パスワード変更後もログイン状態を
    維持するため、セッションの認証ハッシュを更新する。入力エラーの場合は
    エラーをフォームに残したままマイページを再表示する。

    Args:
        request: 表示または編集フォーム送信を行うログイン済みユーザーのリクエスト。

    Returns:
        プロフィールと各フォームを含むマイページのレスポンス、または保存後の
        マイページへのリダイレクト。
    """
    try:
        profile = Profile.objects.select_related("organization").get(
            user=request.user
        )
    except Profile.DoesNotExist:
        profile = None

    edit_mode = request.GET.get("edit") == "1"
    organization_form = (
        OrganizationProfileForm(instance=profile.organization)
        if profile
        else None
    )
    password_form = AccountPasswordChangeForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "organization" and profile:
            organization_form = OrganizationProfileForm(
                request.POST, instance=profile.organization
            )
            if organization_form.is_valid():
                organization_form.save()
                return redirect("bichiku:my_page")
            edit_mode = True
        elif action == "password":
            password_form = AccountPasswordChangeForm(
                user=request.user, data=request.POST
            )
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, request.user)
                return redirect("bichiku:my_page")

    return render(
        request,
        "bichiku/my_page.html",
        {
            "profile": profile,
            "organization_form": organization_form,
            "password_form": password_form,
            "edit_mode": edit_mode,
        },
    )
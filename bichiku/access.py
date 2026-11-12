from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from .models import Profile


def get_organization(user):
    """ログイン中ユーザーの所属組織を返す。なければ None。
    組織は、ここでは勝手に作りません(登録・管理画面で作ります)。"""
    try:
        return user.profile.organization
    except Profile.DoesNotExist:
        return None


def _forbidden(message):
    return HttpResponseForbidden(message, content_type="text/plain; charset=utf-8")


def company_required(view):
    """企業アカウントだけが使える画面につけるデコレーター。

    - ログインしていなければ、ログイン画面へ
    - 所属組織がない、または企業でなければ、403(閲覧不可)
    - 通れば、request.organization に所属組織が入る
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        organization = get_organization(request.user)
        if organization is None:
            return _forbidden("所属組織が設定されていません。管理者に連絡してください。")
        if not organization.is_company:
            return _forbidden("この画面は、企業アカウント専用です。")
        request.organization = organization
        return view(request, *args, **kwargs)

    return login_required(wrapper)

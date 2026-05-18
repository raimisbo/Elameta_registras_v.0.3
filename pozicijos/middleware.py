from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


FORCE_PASSWORD_CHANGE_GROUP = "Privalomas slaptažodžio keitimas"


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user and user.is_authenticated:
            path = request.path

            try:
                password_change_url = reverse("password_change")
            except NoReverseMatch:
                password_change_url = "/accounts/password_change/"

            allowed_prefixes = [
                password_change_url,
                "/accounts/logout/",
                getattr(settings, "STATIC_URL", "/static/"),
                getattr(settings, "MEDIA_URL", "/media/"),
            ]

            is_allowed_path = any(
                prefix and path.startswith(prefix)
                for prefix in allowed_prefixes
            )

            if (
                not is_allowed_path
                and user.groups.filter(name=FORCE_PASSWORD_CHANGE_GROUP).exists()
            ):
                return redirect("password_change")

        return self.get_response(request)

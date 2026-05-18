from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from pozicijos.auth_views import ForcedPasswordChangeView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/password_change/",
        ForcedPasswordChangeView.as_view(),
        name="password_change",
    ),
    path("accounts/", include("django.contrib.auth.urls")),

    path(
        "",
        RedirectView.as_view(
            pattern_name="pozicijos:list",
            permanent=False,
        ),
        name="home_redirect",
    ),

    path("pozicijos/", include(("pozicijos.urls", "pozicijos"), namespace="pozicijos")),
]

if settings.DEBUG:
    # MEDIA
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # STATIC per Django staticfiles finders (naudojasi tuo pačiu, ką rodo findstatic)
    urlpatterns += staticfiles_urlpatterns()

from django.contrib.auth.views import PasswordChangeView


FORCE_PASSWORD_CHANGE_GROUP = "Privalomas slaptažodžio keitimas"


class ForcedPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.groups.remove(
            *self.request.user.groups.filter(name=FORCE_PASSWORD_CHANGE_GROUP)
        )
        return response

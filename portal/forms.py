"""
Portal authentication forms.

Thin Bootstrap 5 wrappers around Django's built-in auth forms. No custom
authentication logic - only presentation (CSS classes, placeholders, labels).

Forms map 1:1 to Django's own forms:
    AuthenticationForm  -> LoginForm
    PasswordChangeForm  -> PasswordChangeForm
    PasswordResetForm   -> PasswordResetForm
    SetPasswordForm     -> SetPasswordForm
    ModelForm (User)    -> ProfileForm
"""

from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.models import User


class MfStyleMixin:
    """Add Bootstrap 5 styling to every widget on the form."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
                continue
            if isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
                continue
            widget.attrs.setdefault("class", "form-control")


class LoginForm(MfStyleMixin, auth_forms.AuthenticationForm):
    """Django's AuthenticationForm + a "remember me" checkbox."""

    remember_me = forms.BooleanField(
        required=False,
        label="Keep me signed in on this device",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username or email"
        self.fields["username"].widget.attrs.update(
            {"placeholder": "you@company.com", "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"placeholder": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022",
             "autocomplete": "current-password"}
        )


class PasswordChangeForm(MfStyleMixin, auth_forms.PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update(
            {"autocomplete": "current-password"}
        )
        self.fields["new_password1"].help_text = (
            "Use at least 12 characters, including letters, numbers and symbols."
        )
        self.fields["new_password2"].widget.attrs.update(
            {"autocomplete": "new-password"}
        )


class PasswordResetForm(MfStyleMixin, auth_forms.PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {"placeholder": "you@company.com", "autocomplete": "email"}
        )


class SetPasswordForm(MfStyleMixin, auth_forms.SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].help_text = (
            "Use at least 12 characters, including letters, numbers and symbols."
        )


class ProfileForm(MfStyleMixin, forms.ModelForm):
    """Edits basic identity fields on Django's built-in User model."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

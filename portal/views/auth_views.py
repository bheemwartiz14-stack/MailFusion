"""
Authentication views.

All authentication-related views live here. They reuse Django's built-in auth
views (``LoginView``, ``LogoutView``, ``PasswordResetView``,
``PasswordResetConfirmView``, ``PasswordChangeView``) end to end — Django owns
authentication, sessions, password handling and validation.

Methods are only overridden where the business needs extra side-effects
(audit trail + notifications), delegated to ``AuthService``. No Django auth
logic is duplicated here.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import FormView

from ..base_view import APP_NAME, APP_VERSION, PortalContextMixin
from ..forms import (
    LoginForm,
    PasswordChangeForm,
    PasswordResetForm,
    ProfileForm,
    SetPasswordForm,
)
from ..services import AuthService


class PortalAuthMixin:
    """Standalone auth page rendered outside the app shell (login/reset)."""

    auth_page = True
    title = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            app_name=APP_NAME,
            app_version=APP_VERSION,
            title=self.title or context.get("title", ""),
            auth_page=self.auth_page,
        )
        return context


class LoginView(PortalAuthMixin, auth_views.LoginView):
    template_name = "authentication/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True
    title = "Sign in"

    service = AuthService()

    def form_valid(self, form):
        # Remember me: long-lived session. Otherwise session-only cookie with
        # an inactivity timeout (SESSION_SAVE_EVERY_REQUEST refreshes expiry).
        remember = form.cleaned_data.get("remember_me")
        self.request.session.set_expiry(
            settings.SESSION_COOKIE_AGE if remember else settings.SESSION_INACTIVITY_TIMEOUT
        )
        response = super().form_valid(form)
        self.service.record_login(self.request, self.request.user)
        return response

    def form_invalid(self, form):
        self.service.record_failed_login(
            self.request, form.cleaned_data.get("username", "")
        )
        return super().form_invalid(form)


class LogoutView(PortalAuthMixin, auth_views.LogoutView):
    template_name = "authentication/logged_out.html"
    title = "Signed out"

    service = AuthService()

    def post(self, request, *args, **kwargs):
        self.service.record_logout(request, request.user)
        return super().post(request, *args, **kwargs)


class PasswordResetView(PortalAuthMixin, auth_views.PasswordResetView):
    template_name = "authentication/forgot_password.html"
    form_class = PasswordResetForm
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    title = "Forgot Password"

    service = AuthService()

    def form_valid(self, form):
        self.service.record_password_reset_requested(
            self.request, form.cleaned_data.get("email")
        )
        return super().form_valid(form)


class PasswordResetDoneView(PortalAuthMixin, auth_views.PasswordResetDoneView):
    template_name = "authentication/password_reset_done.html"
    title = "Check Your Email"


class PasswordResetConfirmView(PortalAuthMixin, auth_views.PasswordResetConfirmView):
    template_name = "authentication/reset_password.html"
    form_class = SetPasswordForm
    success_url = reverse_lazy("password_reset_complete")
    title = "Reset Password"

    service = AuthService()

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.user.is_authenticated:
            self.service.record_password_reset(self.request, self.request.user)
        return response


class PasswordResetCompleteView(PortalAuthMixin, auth_views.PasswordResetCompleteView):
    template_name = "authentication/password_reset_complete.html"
    title = "Password Reset Complete"


class PasswordChangeView(LoginRequiredMixin, PortalContextMixin, auth_views.PasswordChangeView):
    template_name = "authentication/change_password.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("password_change_done")
    title = "Change Password"
    breadcrumbs = [{"label": "Change Password"}]
    active_page = "profile"

    service = AuthService()

    def form_valid(self, form):
        response = super().form_valid(form)
        self.service.record_password_change(self.request, self.request.user)
        return response


class PasswordChangeDoneView(LoginRequiredMixin, PortalContextMixin, auth_views.PasswordChangeDoneView):
    template_name = "authentication/change_password_done.html"
    title = "Password Updated"
    breadcrumbs = [{"label": "Password Updated"}]
    active_page = "profile"


class ProfileView(LoginRequiredMixin, PortalContextMixin, FormView):
    template_name = "authentication/profile.html"
    title = "User Profile"
    breadcrumbs = [{"label": "User Profile"}]
    active_page = "profile"
    form_class = ProfileForm
    success_url = reverse_lazy("profile")

    service = AuthService()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        self.service.record_profile_update(self.request, self.request.user)
        messages.success(self.request, "Your profile was updated successfully.")
        return super().form_valid(form)

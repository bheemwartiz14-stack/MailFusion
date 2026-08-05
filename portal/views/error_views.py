

from portal.base_view import build_shell_context
from django.shortcuts import redirect, render
def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403, context=build_shell_context(auth_page=True, title="403 Forbidden"))


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404, context=build_shell_context(auth_page=True, title="404 Not Found"))


def error_500(request):
    return render(request, "errors/500.html", status=500, context=build_shell_context(auth_page=True, title="500 Server Error"))


def maintenance(request):
    return render(request, "errors/maintenance.html", context=build_shell_context(auth_page=True, title="Maintenance"))

def _querystring(request):
    """Preserve current GET filters when paginating (drops the page key)."""
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""
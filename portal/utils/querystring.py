_PAGE_SIZE_OPTIONS = (5, 10, 20, 50, 100)


def _page_size(request, default=20):
    """Read a sane ``page_size`` from the request querystring."""
    try:
        value = int(request.GET.get("page_size", default))
    except (TypeError, ValueError):
        return default
    if value not in _PAGE_SIZE_OPTIONS:
        return default
    return value


def _page_size_options():
    """Available page-size choices for the pagination selector."""
    return list(_PAGE_SIZE_OPTIONS)


def _querystring(request):
    """Preserve current GET filters when paginating (drops the page key)."""
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""
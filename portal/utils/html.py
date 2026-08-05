"""
HTML sanitization for external (email) content.

Email bodies arrive from Microsoft Graph as arbitrary HTML and CANNOT be
rendered with ``|safe`` unless sanitized. ``bleach`` strips scripts,
attributes and protocols that could enable XSS or phishing markup.

Kept deliberately small: no business logic, only a thin wrapper.
"""

import bleach

# Allow typical email markup but refuse scripts/events/dangerous protocols.
ALLOWED_TAGS = [
    "a", "p", "br", "hr", "b", "strong", "i", "em", "u", "s", "strike",
    "blockquote", "pre", "code", "ul", "ol", "li", "h1", "h2", "h3", "h4",
    "h5", "h6", "table", "thead", "tbody", "tr", "th", "td", "img", "span",
    "div", "font", "sub", "sup", "small", "big",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "p": ["align"],
    "span": ["style"],
    "div": ["style"],
    "font": ["color", "face", "size"],
}


def sanitize_html(html):
    """Sanitize untrusted email HTML for safe display. Returns a safe string."""
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
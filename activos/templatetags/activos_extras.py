from django import template

register = template.Library()

@register.filter
def is_pdf(value):
    """Return True if given string (file path/URL) ends with .pdf"""
    if not value:
        return False
    return str(value).lower().endswith('.pdf')


@register.simple_tag
def media_abs(request, path):
    """Return an absolute URI for the given media path."""
    return request.build_absolute_uri(path)
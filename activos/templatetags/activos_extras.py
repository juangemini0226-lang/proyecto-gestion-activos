from django import template

register = template.Library()

@register.filter
def is_pdf(value):
    """Return True if given string (file path/URL) ends with .pdf"""
    if not value:
        return False
    return str(value).lower().endswith('.pdf')
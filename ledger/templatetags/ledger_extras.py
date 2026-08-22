from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Look up a dict value by a variable key inside a template (row.amounts|dict_get:d)."""
    return d.get(key, 0)

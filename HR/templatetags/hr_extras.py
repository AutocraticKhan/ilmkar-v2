"""Small template filters for the HR attendance grid."""
from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dict lookup by variable key: ``records|get_item:iso_date``."""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""


LETTERS = {
    "present": "P",
    "absent": "A",
    "late": "L",
    "half_day": "H",
    "leave": "V",
}


@register.filter
def ab_char(status):
    """One-letter cell marker for an attendance status."""
    return LETTERS.get(status, "·")

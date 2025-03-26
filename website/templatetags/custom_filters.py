from django import template
register = template.Library()

@register.filter(name='abs')
def abs_filter(value):
    """Returns the absolute value of a number.
    Converts strings to float first to handle SafeString objects from other filters."""
    try:
        # Convert to float first if it's a string or SafeString
        if isinstance(value, str):
            value = float(value.replace(',', ''))
        return abs(value)
    except (ValueError, TypeError):
        # Return original if conversion fails
        return value
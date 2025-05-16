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
    
@register.filter
def filter_by_platform(accounts, platform_slug):
    return [account for account in accounts if account.platform_connection.platform_type.slug == platform_slug]

@register.filter(name='div')
def div_filter(value, arg):
    """
    Divides the value by the argument
    """
    try:
        # Convert strings to float first if needed
        if isinstance(value, str):
            value = float(value.replace(',', ''))
        if isinstance(arg, str):
            arg = float(arg.replace(',', ''))
            
        # Avoid division by zero
        if arg == 0:
            return 0
            
        return value / arg
    except (ValueError, TypeError):
        return 0
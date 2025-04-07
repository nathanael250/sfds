def format_currency(value):
    """Format a number as currency with 2 decimal places."""
    try:
        return "{:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return "0.00" 
"""What a discount takes off a Stripe invoice: a promo code of free months leaves invoices of 0 € that are still
ERPlora's invoices, each line with its price, its discount and its base after it."""


def line_amounts(line: dict) -> tuple[int, int]:
    """``(amount, discount)`` of a Stripe invoice line in cents: its ``amount`` is the price BEFORE the discount, so
    what is billed is that minus ``discount_amounts``."""
    discount = sum(int(part.get("amount") or 0) for part in line.get("discount_amounts") or [])
    return int(line.get("amount") or 0) - discount, discount


def is_fully_discounted(invoice: dict) -> bool:
    """An invoice a discount took to 0: something was sold (``subtotal``) and nothing is due. A trial's is 0 because
    nothing was sold, and that one is no invoice."""
    return int(invoice.get("total") or 0) == 0 and int(invoice.get("subtotal") or 0) > 0

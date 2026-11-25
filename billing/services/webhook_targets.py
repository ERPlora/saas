"""The business a Stripe event is about: named by the ``hub_id`` of its metadata, or known by its Stripe subscription."""

from django.core.exceptions import ValidationError as DjangoValidationError

from hubs.models import Hub, Subscription


def _hub_named(hub_id) -> Hub | None:
    try:
        return Hub.objects.filter(pk=hub_id, is_platform=False).first() if hub_id else None
    except ValueError, TypeError, DjangoValidationError:
        return None


def _local_subscription(subscription_id: str) -> Subscription | None:
    if not subscription_id:
        return None
    return (
        Subscription.objects.select_related("hub", "plan")
        .filter(stripe_subscription_id=subscription_id)
        .first()
    )

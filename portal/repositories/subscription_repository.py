"""
Subscription repository.

Data access for Microsoft Graph Change Notification subscriptions and the
``AccountHealth`` rollup. Pure queries only.
"""

from django.utils import timezone

from portal.models import AccountHealth, GraphSubscription


class SubscriptionRepository:
    """Persistence for webhook subscriptions and account health."""

    # -------------------- GraphSubscription --------------------

    def create_subscription(
        self,
        *,
        account,
        subscription_id,
        resource,
        change_type="created",
        notification_url="",
        client_state="",
        expiration_date_time,
    ):
        return GraphSubscription.objects.create(
            account=account,
            subscription_id=subscription_id,
            resource=resource,
            change_type=change_type,
            notification_url=notification_url,
            client_state=client_state,
            expiration_date_time=expiration_date_time,
        )

    def list_active(self, account=None):
        qs = GraphSubscription.objects.filter(status="active").select_related("account")
        if account:
            qs = qs.filter(account=account)
        return qs

    def list_expiring(self, within_hours=24):
        from datetime import timedelta

        cutoff = timezone.now() + timedelta(hours=within_hours)
        return GraphSubscription.objects.filter(
            status="active", expiration_date_time__lte=cutoff
        ).select_related("account")

    def get_by_subscription_id(self, subscription_id):
        return GraphSubscription.objects.filter(subscription_id=subscription_id).first()

    def update_subscription(self, subscription, **fields):
        for field, value in fields.items():
            setattr(subscription, field, value)
        subscription.save(update_fields=list(fields.keys()) + ["updated_at"])
        return subscription

    def mark_expired(self, subscription):
        return self.update_subscription(subscription, status="expired")

    # -------------------- AccountHealth --------------------

    def get_or_create_health(self, account):
        health, _ = AccountHealth.objects.get_or_create(account=account)
        return health

    def update_health(self, health, **fields):
        for field, value in fields.items():
            setattr(health, field, value)
        health.save(update_fields=list(fields.keys()) + ["updated_at"])
        return health

    def unhealthy_accounts(self):
        from django.db.models import F

        return (
            AccountHealth.objects.filter(
                created_at__isnull=False
            )
            .filter(consecutive_failures__gte=1)
            .select_related("account")
        )
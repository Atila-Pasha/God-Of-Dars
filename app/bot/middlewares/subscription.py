from app.core.config import settings
from app.services.subscription_service import SubscriptionService

subscription_service = SubscriptionService(settings.required_channel_list)

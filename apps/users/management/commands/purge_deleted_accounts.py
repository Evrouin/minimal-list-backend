from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.users.models import User


class Command(BaseCommand):
    help = "Permanently delete accounts past their scheduled deletion date."

    def handle(self, *args, **options):
        expired = User.objects.filter(scheduled_deletion_at__lte=timezone.now(), is_active=False)
        count = expired.count()
        for user in expired:
            if user.avatar:
                user.avatar.delete(save=False)
            user.delete()
        self.stdout.write(f"Purged {count} account(s).")

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_template_email(subject, template_name, context, to_email, from_email=None):
    """Send an email with both HTML and plain text versions."""
    from django.conf import settings

    text_content = render_to_string(f"emails/{template_name}.txt", context)
    html_content = render_to_string(f"emails/{template_name}.html", context)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=True)


def send_account_deactivated_email(user, token, reason):
    from django.conf import settings
    context = {"user": user, "reason": reason, "frontend_url": settings.FRONTEND_URL, "token": token}
    send_template_email("Your account has been deactivated", "account-deactivated", context, user.email)


def send_account_reactivated_email(user):
    send_template_email("Your account has been reactivated", "account-reactivated", {"user": user}, user.email)


def send_deletion_scheduled_email(user, token):
    from django.conf import settings
    context = {"user": user, "token": token, "frontend_url": settings.FRONTEND_URL, "scheduled_deletion_at": user.scheduled_deletion_at}
    send_template_email("Your account is scheduled for deletion", "account-deletion-scheduled", context, user.email)

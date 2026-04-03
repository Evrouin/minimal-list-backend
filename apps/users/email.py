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

import re

from django.core.exceptions import ValidationError


class ComplexityValidator:
    """Enforce letters, numbers, and at least one special character."""

    def validate(self, password, user=None):
        if not re.search(r"[a-zA-Z]", password):
            raise ValidationError("Password must include at least one letter.")
        if not re.search(r"\d", password):
            raise ValidationError("Password must include at least one number.")
        if not re.search(r"[^a-zA-Z0-9]", password):
            raise ValidationError("Password must include at least one special character.")

    def get_help_text(self):
        return "Password must include letters, numbers, and a special character."

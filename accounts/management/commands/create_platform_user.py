"""``manage.py create_platform_user <email> --role admin|support [--password …]``: the platform's staff.

Platform users are created only here or in the SaaS's Django admin. ``admin`` is a superuser;
``support`` is staff in the ``support`` group (view only on accounts). Running it again on the same
email updates the role (and the password, if given). Platform roles never reach a hub.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts import services


class Command(BaseCommand):
    help = "Create or update a platform user: admin (superuser) or support (staff, view only)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--role", required=True, choices=services.PLATFORM_ROLES)
        parser.add_argument(
            "--password",
            help="Without it, a new account has no usable password (set it in the admin or by password reset).",
        )

    def handle(self, *args, email, role, password, **options):
        if password is not None:
            try:
                validate_password(password)
            except ValidationError as exc:
                raise CommandError(f"The password is not valid: {' '.join(exc.messages)}") from exc
        try:
            user, created = services.create_platform_user(email, role, password)
        except services.PlatformRoleRefused as exc:
            raise CommandError(f"Refused: {exc}. A customer account cannot be platform staff.") from exc
        except services.SupportGroupMissing as exc:
            raise CommandError(
                f"The {exc} group is missing: run `manage.py migrate accounts` to create it."
            ) from exc
        verb = "Created" if created else "Updated"
        self.stdout.write(f"{verb} {user.email}: platform {role}.")
        if created and password is None:
            self.stdout.write("No password set: set it in the admin or with the password reset.")

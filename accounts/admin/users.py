"""Django admin of the users: email and password, what the account chose in the Account page (its preferences and
photo) seen only, and «Close all their sessions»."""

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from accounts.models import ProfilePhoto, User, UserPreferences
from accounts.services import active_sessions


class UserCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email",)


class UserEditForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


class ReadOnlyInline(admin.StackedInline):
    """What the account chose in the Account page, seen only: it changes it there."""

    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class UserPreferencesInline(ReadOnlyInline):
    model = UserPreferences
    fields = ("theme_mode", "transparency", "hub_alerts", "updated_at")
    readonly_fields = fields


class ProfilePhotoInline(ReadOnlyInline):
    model = ProfilePhoto
    fields = ("preview", "content_type", "updated_at")
    readonly_fields = fields

    @admin.display(description=_("photo"))
    def preview(self, obj):
        return format_html('<img src="{}" alt="" width="96" height="96" style="object-fit: cover">', obj.data_url())


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserEditForm
    add_form = UserCreationForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "language", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser", "language")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("id", "last_login", "date_joined", "terms_accepted_at", "terms_version", "privacy_version")
    inlines = [UserPreferencesInline, ProfilePhotoInline]
    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "language")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_store_review_account",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
        # What the account accepted: evidence, so nobody edits it here.
        (_("Terms and privacy"), {"fields": ("terms_accepted_at", "terms_version", "privacy_version")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "usable_password", "password1", "password2")}),)
    actions = ("close_sessions",)

    def get_readonly_fields(self, request, obj=None):
        # The store review account drops the mailed code of its sign-in: only a superuser sets or clears
        # it; whoever else sees the page sees it. A staff account never carries it (``User.clean``).
        readonly = super().get_readonly_fields(request, obj)
        return readonly if request.user.is_superuser else (*readonly, "is_store_review_account")

    def get_inlines(self, request, obj):
        # Adding is email + password only (as Django's UserAdmin); hubs are given once it exists.
        if obj is None:
            return []
        # A read-only box with no row (an account still on the defaults) would be an empty heading.
        return [
            inline
            for inline in self.inlines
            if not issubclass(inline, ReadOnlyInline) or inline.model.objects.filter(user=obj).exists()
        ]

    def has_close_sessions_permission(self, request):
        return request.user.is_superuser

    @admin.action(
        description=_("Close all their sessions"),
        permissions=["close_sessions"],
    )
    def close_sessions(self, request, queryset):
        """An incident: the accounts picked are signed out everywhere and asked for their app's code
        again on every browser."""
        count = active_sessions.close_sessions(by=request.user, users=list(queryset.values_list("pk", flat=True)))
        self.message_user(request, gettext("Sessions closed: %(count)s.") % {"count": count}, messages.SUCCESS)

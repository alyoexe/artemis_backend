from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

from ingestion.models import CustomUser, TechnicalDocument


class IsSystemAdministrator(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == CustomUser.Roles.SYSTEM_ADMINISTRATOR


class IsSystemAdministratorOrDataSteward(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {
            CustomUser.Roles.SYSTEM_ADMINISTRATOR,
            CustomUser.Roles.DATA_STEWARD,
        }


class DocumentAccessPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in SAFE_METHODS:
            return True

        if request.method == "POST":
            return request.user.role in {
                CustomUser.Roles.SYSTEM_ADMINISTRATOR,
                CustomUser.Roles.DATA_STEWARD,
            }

        if request.method in {"PUT", "PATCH"}:
            return request.user.role == CustomUser.Roles.SYSTEM_ADMINISTRATOR

        if request.method == "DELETE":
            return request.user.role in {
                CustomUser.Roles.SYSTEM_ADMINISTRATOR,
                CustomUser.Roles.DATA_STEWARD,
            }

        return request.user.role in {
            CustomUser.Roles.SYSTEM_ADMINISTRATOR,
            CustomUser.Roles.DATA_STEWARD,
        }

    def has_object_permission(self, request, view, obj):
        if request.user.role == CustomUser.Roles.SYSTEM_ADMINISTRATOR:
            return True

        if request.user.role == CustomUser.Roles.DATA_STEWARD:
            return obj.uploaded_by_id == request.user.id

        if request.user.role == CustomUser.Roles.FIELD_TECHNICIAN:
            if request.method in SAFE_METHODS:
                if obj.status != TechnicalDocument.Status.READY:
                    return False
                # If allowlist is empty, document is visible to all technicians.
                if not obj.visible_to.exists():
                    return True
                return obj.visible_to.filter(id=request.user.id).exists()
            return False

        if request.method in SAFE_METHODS:
            return obj.status == TechnicalDocument.Status.READY

        return False


class CanUpdateDocumentStatus(BasePermission):
    """Allow status updates from privileged roles or a trusted pipeline token."""

    def has_permission(self, request, view):
        if (
            request.user
            and request.user.is_authenticated
            and request.user.role == CustomUser.Roles.SYSTEM_ADMINISTRATOR
        ):
            return True

        expected = settings.PIPELINE_STATUS_TOKEN
        provided = request.headers.get("X-PIPELINE-TOKEN", "")
        return bool(expected) and provided == expected

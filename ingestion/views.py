from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from ingestion.models import CustomUser, EquipmentCategory, TechnicalDocument, Vendor
from ingestion.permissions import (
    CanUpdateDocumentStatus,
    DocumentAccessPermission,
    IsSystemAdministrator,
    IsSystemAdministratorOrDataSteward,
)
from ingestion.serializers import (
    CustomTokenObtainPairSerializer,
    CustomUserSerializer,
    EquipmentCategorySerializer,
    RegistrationSerializer,
    TechnicalDocumentSerializer,
    TechnicalDocumentStatusUpdateSerializer,
    VendorSerializer,
)


class AuthTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class AuthTokenRefreshView(TokenRefreshView):
    pass


class AuthRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        requested_role = request.data.get("role")
        if (
            requested_role == CustomUser.Roles.DATA_STEWARD
            and not getattr(settings, "DATA_STEWARD_PUBLIC_SIGNUP_ENABLED", False)
        ):
            return Response(
                {"detail": "Data Steward signup is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        response_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)


class CustomUserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all().order_by("username")
    serializer_class = CustomUserSerializer
    permission_classes = [IsSystemAdministrator]

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsSystemAdministratorOrDataSteward],
        url_path="technicians",
    )
    def technicians(self, request):
        qs = CustomUser.objects.filter(role=CustomUser.Roles.FIELD_TECHNICIAN).order_by("username")
        data = [
            {
                "id": u.id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
            }
            for u in qs
        ]
        return Response(data, status=status.HTTP_200_OK)


class EquipmentCategoryViewSet(viewsets.ModelViewSet):
    queryset = EquipmentCategory.objects.all()
    serializer_class = EquipmentCategorySerializer

    def get_permissions(self):
        if self.request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            return [IsSystemAdministrator()]
        return [IsAuthenticated()]


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer

    def get_permissions(self):
        if self.request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            return [IsSystemAdministrator()]
        return [IsAuthenticated()]


class TechnicalDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = TechnicalDocumentSerializer
    permission_classes = [DocumentAccessPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = TechnicalDocument.objects.select_related(
            "vendor",
            "category",
            "uploaded_by",
        )

        user = self.request.user
        if not user or not user.is_authenticated:
            return queryset

        if user.role == CustomUser.Roles.FIELD_TECHNICIAN:
            return (
                queryset.filter(status=TechnicalDocument.Status.READY)
                .filter(Q(visible_to__isnull=True) | Q(visible_to=user))
                .distinct()
            )

        if user.role == CustomUser.Roles.DATA_STEWARD:
            return queryset.filter(uploaded_by=user)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save(uploaded_by=request.user)

        # TODO: Trigger external processing pipeline here

        response_serializer = self.get_serializer(document)
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_destroy(self, instance):
        # Delete the underlying file object first so row and storage stay in sync.
        if instance.file:
            instance.file.delete(save=False)
        instance.delete()

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsSystemAdministrator],
        url_path="cleanup-orphans",
    )
    def cleanup_orphans(self, request):
        """Delete storage objects that are not referenced by any TechnicalDocument row.

        This is intended as an admin-only maintenance operation.
        """

        prefix = (request.data.get("prefix") or "technical_documents/").strip()
        if not prefix:
            prefix = "technical_documents/"
        if not prefix.endswith("/"):
            prefix += "/"

        referenced = set(
            TechnicalDocument.objects.exclude(file="").values_list("file", flat=True)
        )

        deleted = []

        # S3-compatible storages (Supabase S3 endpoint via django-storages)
        if hasattr(default_storage, "connection") and hasattr(default_storage, "bucket_name"):
            client = default_storage.connection.meta.client
            bucket = default_storage.bucket_name

            continuation = None
            while True:
                kwargs = {"Bucket": bucket, "Prefix": prefix}
                if continuation:
                    kwargs["ContinuationToken"] = continuation

                resp = client.list_objects_v2(**kwargs)
                for obj in resp.get("Contents", []) or []:
                    key = obj.get("Key")
                    if not key or key.endswith("/"):
                        continue
                    if key not in referenced:
                        default_storage.delete(key)
                        deleted.append(key)

                if resp.get("IsTruncated"):
                    continuation = resp.get("NextContinuationToken")
                else:
                    break

        # Local filesystem storage fallback
        else:
            root = Path(settings.MEDIA_ROOT) / prefix
            if root.exists():
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    rel = str(path.relative_to(settings.MEDIA_ROOT)).replace("\\", "/")
                    if rel not in referenced:
                        default_storage.delete(rel)
                        deleted.append(rel)

        return Response(
            {
                "prefix": prefix,
                "deleted_count": len(deleted),
                "deleted": deleted,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[CanUpdateDocumentStatus],
        url_path="status",
    )
    def update_status(self, request, pk=None):
        document = self.get_object()
        serializer = TechnicalDocumentStatusUpdateSerializer(document, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TechnicalDocumentSerializer(document).data, status=status.HTTP_200_OK)

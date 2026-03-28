from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ingestion.views import (
    AuthRegisterView,
    AuthTokenObtainPairView,
    AuthTokenRefreshView,
    CustomUserViewSet,
    EquipmentCategoryViewSet,
    TechnicalDocumentViewSet,
    VendorViewSet,
)

router = DefaultRouter()
router.register("users", CustomUserViewSet, basename="user")
router.register("documents", TechnicalDocumentViewSet, basename="document")
router.register("vendors", VendorViewSet, basename="vendor")
router.register("equipment-categories", EquipmentCategoryViewSet, basename="equipment-category")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/register/", AuthRegisterView.as_view(), name="auth_register"),
    path("api/auth/token/", AuthTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", AuthTokenRefreshView.as_view(), name="token_refresh"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

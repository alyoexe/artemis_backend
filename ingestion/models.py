from django.contrib.auth.models import AbstractUser
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CustomUser(AbstractUser):
    class Roles(models.TextChoices):
        SYSTEM_ADMINISTRATOR = "SYSTEM_ADMINISTRATOR", "System Administrator"
        DATA_STEWARD = "DATA_STEWARD", "Data Steward"
        FIELD_TECHNICIAN = "FIELD_TECHNICIAN", "Field Technician"

    role = models.CharField(
        max_length=32,
        choices=Roles.choices,
        default=Roles.FIELD_TECHNICIAN,
    )

    @property
    def is_system_administrator(self):
        return self.role == self.Roles.SYSTEM_ADMINISTRATOR

    @property
    def is_data_steward(self):
        return self.role == self.Roles.DATA_STEWARD

    @property
    def is_field_technician(self):
        return self.role == self.Roles.FIELD_TECHNICIAN


class EquipmentCategory(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Vendor(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TechnicalDocument(TimeStampedModel):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        PROCESSING = "PROCESSING", "Processing"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    file = models.FileField(upload_to="technical_documents/%Y/%m/%d")
    title = models.CharField(max_length=255)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="documents")
    category = models.ForeignKey(
        EquipmentCategory,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_documents",
    )

    # Optional per-user visibility restriction for Field Technicians.
    # If empty, READY documents are visible to all Field Technicians (backwards-compatible).
    visible_to = models.ManyToManyField(
        CustomUser,
        related_name="visible_documents",
        blank=True,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["vendor"]),
            models.Index(fields=["category"]),
            models.Index(fields=["uploaded_by"]),
        ]

    def __str__(self):
        return self.title

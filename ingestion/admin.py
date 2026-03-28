from django.contrib import admin

from ingestion.models import CustomUser, EquipmentCategory, TechnicalDocument, Vendor


admin.site.register(CustomUser)
admin.site.register(EquipmentCategory)
admin.site.register(Vendor)
admin.site.register(TechnicalDocument)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from . import models


@admin.register(models.User)
class CustomUserAdmin(UserAdmin):
    model = models.User
    ordering = ("email",)
    list_display = ("email", "full_name", "is_staff", "is_active")
    fieldsets = UserAdmin.fieldsets + (("SayaraHub", {"fields": ("full_name", "phone_number", "image", "is_verified")}),)


for model in (
    models.Car, models.CarBrand, models.CarModel, models.BodyType, models.CarCondition,
    models.Feature, models.FuelType, models.Transmission, models.Review, models.Chat,
    models.Message, models.ContactMessage, models.Report, models.Notification, models.SavedSearch,
):
    admin.site.register(model)

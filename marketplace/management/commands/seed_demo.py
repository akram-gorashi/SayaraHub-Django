from django.core.management.base import BaseCommand
from marketplace import models


class Command(BaseCommand):
    help = "Create repeatable SayaraHub lookup data, demo users, and sample listings."

    def handle(self, *args, **options):
        lookups = {
            models.BodyType: ["Sedan", "SUV", "Coupe", "Pickup"],
            models.CarCondition: ["New", "Used", "Certified"],
            models.Feature: ["Bluetooth", "Cruise Control", "Navigation", "Parking Sensors"],
            models.FuelType: ["Petrol", "Diesel", "Hybrid", "Electric"],
            models.Transmission: ["Automatic", "Manual"],
        }
        for model, names in lookups.items():
            for name in names:
                model.objects.get_or_create(name=name)

        toyota, _ = models.CarBrand.objects.get_or_create(name="Toyota")
        hyundai, _ = models.CarBrand.objects.get_or_create(name="Hyundai")
        camry, _ = models.CarModel.objects.get_or_create(brand=toyota, name="Camry")
        models.CarModel.objects.get_or_create(brand=toyota, name="Land Cruiser")
        models.CarModel.objects.get_or_create(brand=hyundai, name="Sonata")

        seller, created = models.User.objects.get_or_create(
            email="seller@sayarahub.local",
            defaults={"username": "seller@sayarahub.local", "full_name": "Demo Seller"},
        )
        if created:
            seller.set_password("SellerDemo_44")
            seller.save()
        admin, created = models.User.objects.get_or_create(
            email="admin@sayarahub.local",
            defaults={"username": "admin@sayarahub.local", "full_name": "Demo Admin", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password("AdminDemo_44")
            admin.save()

        if not models.Car.objects.filter(seller=seller).exists():
            models.Car.objects.create(
                title="2024 Toyota Camry", brand=toyota, model=camry, price=125000,
                status=models.Car.Status.AVAILABLE, body_type=models.BodyType.objects.get(name="Sedan"),
                condition=models.CarCondition.objects.get(name="Used"), mileage=12000, year=2024,
                transmission=models.Transmission.objects.get(name="Automatic"),
                fuel_type=models.FuelType.objects.get(name="Petrol"), city="Riyadh",
                color="White", doors=4, cylinders=4, engine_size="2.5L",
                description="Clean demo listing for API practice.", seller=seller,
            )
        self.stdout.write(self.style.SUCCESS("Demo data is ready."))

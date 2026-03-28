from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="technicaldocument",
            name="visible_to",
            field=models.ManyToManyField(blank=True, related_name="visible_documents", to="ingestion.customuser"),
        ),
    ]

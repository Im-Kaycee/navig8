from django.contrib import admin
from .models import *
# Register your models here.
admin.site.register(City)
admin.site.register(Place)
admin.site.register(PlaceAlias)
admin.site.register(RouteStepSubmission)
admin.site.register(RouteSubmission)
admin.site.register(Route)
admin.site.register(RouteStep)
admin.site.register(StepFare)

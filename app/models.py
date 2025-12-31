from django.db import models
from django.db import transaction
from django.utils import timezone
from main.models import User
# Create your models here.
class City(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
class Place(models.Model):
    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        related_name="places"
    )
    canonical_name = models.CharField(max_length=200)
    area = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    class Meta:
        unique_together = ("city", "canonical_name")
        indexes = [
            models.Index(fields=["city", "canonical_name"]),
        ]

    def __str__(self):
        return f"{self.canonical_name} ({self.city.name})"
class PlaceAlias(models.Model):
    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="aliases"
    )
    name = models.CharField(max_length=200)

    class Meta:
        unique_together = ("place", "name")

    def __str__(self):
        return self.name
    
class RouteSubmission(models.Model):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"

    STATUS_CHOICES = [
        (SUBMITTED, "Submitted"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="route_submissions"
    )

    destination = models.CharField(
        max_length=200,
        help_text="What the user thinks the destination is called"
    )
    starting_point = models.ForeignKey(
        Place,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="starting_point_submissions",
        max_length=200,
        help_text="Where the user started from"
    )

    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        related_name="route_submissions"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=SUBMITTED,
        db_index=True
    )

    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # audit fields
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_route_submissions"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # link to created route (set when approved)
    approved_route = models.OneToOneField(
        "Route",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="originating_submission"
    )

    # new: keep the original submitted text so frontend can just send a name
    starting_point_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Free-text starting point from the submitter (optional)"
    )

    def __str__(self):
        return f"Submission to {self.destination}"

    def approve(self, place, reviewer=None):
        """
        Create Route and RouteSteps from this submission in an atomic operation.
        'place' should be a Place instance (destination mapping).
        Sets status, reviewed_by, reviewed_at and approved_route.
        """
        if self.status != self.SUBMITTED:
            raise ValueError("Only submitted submissions can be approved")
                # defensive checks
        if place.city_id != self.city_id:
            raise ValueError("Place city does not match submission city")

        steps_qs = list(self.steps.all().order_by("order"))
        if not steps_qs:
            raise ValueError("Cannot approve an empty submission (no steps)")

        with transaction.atomic():
            route = Route.objects.create(destination=place, recommended=False)
            for step in steps_qs:
                RouteStep.objects.create(
                    route=route,
                    order=step.order,
                    mode=step.mode,
                    instruction=step.instruction,
                    drop_name=step.drop_name,
                    landmark=step.landmark,
                )

            # attach resolved FK if present; otherwise attempt to resolve from starting_point_text
            if self.starting_point_id:
                route.starting_places.add(self.starting_point)
            elif self.starting_point_text:
                city = self.city
                name = self.starting_point_text.strip()
                sp = Place.objects.filter(city=city, canonical_name__iexact=name).first()
                if not sp:
                    alias = PlaceAlias.objects.filter(place__city=city, name__iexact=name).select_related("place").first()
                    sp = alias.place if alias else Place.objects.create(city=city, canonical_name=name)
                route.starting_places.add(sp)

            self.approved_route = route
            self.status = self.APPROVED
            self.reviewed_by = reviewer
            self.reviewed_at = timezone.now()
            self.save()
            return route

    def reject(self, reviewer=None, notes=""):
        if self.status != self.SUBMITTED:
            raise ValueError("Only submitted submissions can be rejected")
        self.status = self.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        if notes:
            # append admin notes rather than overwrite
            self.admin_notes = (self.admin_notes + "\n" + notes).strip()
        self.save()
        return self

class RouteStepSubmission(models.Model):
    WALK = "walk"
    CAB = "cab"
    BUS = "bus"

    MODE_CHOICES = [
        (WALK, "Walk"),
        (CAB, "Cab"),
        (BUS, "Bus"),
    ]

    route_submission = models.ForeignKey(
        RouteSubmission,
        on_delete=models.CASCADE,
        related_name="steps"
    )

    order = models.PositiveIntegerField()
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)
    instruction = models.TextField()
    drop_name = models.CharField(max_length=200, blank=True)
    landmark = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["order"]
        unique_together = (("route_submission", "order"),)
        indexes = [
            models.Index(fields=["route_submission", "order"]),
        ]

    def __str__(self):
        return f"Submission Step {self.order} ({self.mode})"
class Route(models.Model):
    
    destination = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="incoming_routes",
    )
    starting_places = models.ManyToManyField(
        Place,
        related_name="outgoing_routes"
    )

    recommended = models.BooleanField(default=False)
    estimated_time = models.CharField(max_length=50, blank=True)

    difficulty = models.CharField(
        max_length=20,
        choices=[
            ("easy", "Easy"),
            ("medium", "Medium"),
            ("hard", "Hard"),
        ],
        default="easy"
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Route to {self.destination.canonical_name} from {[p.canonical_name for p in self.starting_places.all()]}"
class RouteStep(models.Model):
    WALK = "walk"
    CAB = "cab"
    BUS = "bus"

    MODE_CHOICES = [
        (WALK, "Walk"),
        (CAB, "Cab"),
        (BUS, "Bus"),
    ]

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="steps"
    )

    order = models.PositiveIntegerField()
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)

    instruction = models.TextField()

    drop_name = models.CharField(
        max_length=200,
        blank=True
    )

    landmark = models.CharField(
        max_length=200,
        blank=True
    )

    class Meta:
        ordering = ["order"]
        unique_together = ("route", "order")
        indexes = [
            models.Index(fields=["route", "order"]),
        ]

    def __str__(self):
        return f"Step {self.order} ({self.mode}) for Route to {self.route.destination.canonical_name} from {[p.canonical_name for p in self.route.starting_places.all()]}"
class StepFare(models.Model):
    route_step = models.ForeignKey(
        RouteStep,
        on_delete=models.CASCADE,
        related_name="fares"
    )

    amount = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

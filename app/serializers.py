from rest_framework import serializers
from .models import *

class PlaceAutocompleteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = [
            "id",
            "canonical_name",
            "area",
        ]
class RouteStepSerializer(serializers.ModelSerializer):
    estimated_fare = serializers.SerializerMethodField()

    class Meta:
        model = RouteStep
        fields = [
            "order",
            "mode",
            "instruction",
            "drop_name",
            "landmark",
            "estimated_fare",
        ]

    def get_estimated_fare(self, obj):
        fares = obj.fares.order_by("-created_at")[:30]
        amounts = [f.amount for f in fares]

        if len(amounts) < 3:
            return None

        amounts.sort()
        lower = amounts[int(len(amounts) * 0.2)]
        upper = amounts[int(len(amounts) * 0.8)]

        return {
            "currency": "NGN",
            "min": lower,
            "max": upper,
            "sample_size": len(amounts),
        }
class PlaceSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = ["id", "canonical_name"]

class RouteSerializer(serializers.ModelSerializer):
    steps = RouteStepSerializer(many=True)
    starting_places = PlaceSearchSerializer(many=True, read_only=True)
    destination = PlaceSearchSerializer(read_only=True)

    class Meta:
        model = Route
        fields = [
            "id",
            "destination",
            "starting_places",
            "recommended",
            "estimated_time",
            "difficulty",
            "notes",
            "steps",
        ]
class PlaceSerializer(serializers.ModelSerializer):
    routes = RouteSerializer(many=True)

    class Meta:
        model = Place
        fields = [
            "id",
            "canonical_name",
            "area",
            "description",
            "routes",
        ]
class RouteStepSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteStepSubmission
        fields = ["id", "order", "mode", "instruction", "drop_name", "landmark"]

class RouteSubmissionSerializer(serializers.ModelSerializer):
    steps = RouteStepSubmissionSerializer(many=True, read_only=True)
    submitted_by = serializers.StringRelatedField(read_only=True)
    reviewed_by = serializers.StringRelatedField(read_only=True)
    approved_route = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = RouteSubmission
        fields = [
            "id",
            "submitted_by",
            "destination",
            "starting_point",
            "city",
            "status",
            "admin_notes",
            "created_at",
            "reviewed_by",
            "reviewed_at",
            "approved_route",
            "steps",
        ]

class ApproveSubmissionSerializer(serializers.Serializer):
    place_id = serializers.IntegerField(required=False)
    # optional payload to create a new Place on approve
    create_place = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text='{"canonical_name": "...", "area": "..."}'
    )

    def validate(self, data):
        # allow empty data -> view will try to auto-match and then auto-create a Place
        cp = data.get("create_place")
        if cp and not cp.get("canonical_name"):
            raise serializers.ValidationError({"create_place": "canonical_name is required when creating a place"})
        return data

class RejectSubmissionSerializer(serializers.Serializer):
    admin_notes = serializers.CharField(required=False, allow_blank=True)

class StepFareSerializer(serializers.Serializer):
    class Meta:
        model = StepFare
        fields = [
            "id",
            "route_step",
            "amount",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

class RouteStepSubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteStepSubmission
        fields = ["order", "mode", "instruction", "drop_name", "landmark"]

class RouteSubmissionCreateSerializer(serializers.ModelSerializer):
    steps = RouteStepSubmissionCreateSerializer(many=True)
    submitted_by = serializers.PrimaryKeyRelatedField(read_only=True)

    # keep optional FK for clients that can provide it, and accept free-text
    starting_point = serializers.PrimaryKeyRelatedField(queryset=Place.objects.all(), required=False, allow_null=True)
    starting_point_text = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = RouteSubmission
        fields = [
            "id",
            "submitted_by",
            "destination",
            "starting_point",
            "starting_point_text",
            "city",
            "status",
            "admin_notes",
            "created_at",
            "steps",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def create(self, validated_data):
        steps_data = validated_data.pop("steps", [])
        starting_point = validated_data.pop("starting_point", None)
        starting_point_text = validated_data.pop("starting_point_text", None)

        # Resolve text -> Place if text provided and FK not provided
        if not starting_point and starting_point_text:
            city = validated_data.get("city")
            name = starting_point_text.strip()
            starting_point = Place.objects.filter(city=city, canonical_name__iexact=name).first()
            if not starting_point:
                alias = PlaceAlias.objects.filter(place__city=city, name__iexact=name).select_related("place").first()
                if alias:
                    starting_point = alias.place
            if not starting_point:
                starting_point = Place.objects.create(city=city, canonical_name=name)

        if starting_point is not None:
            validated_data["starting_point"] = starting_point

        submission = RouteSubmission.objects.create(**validated_data)
        objs = [RouteStepSubmission(route_submission=submission, **step) for step in steps_data]
        RouteStepSubmission.objects.bulk_create(objs)
        # store the original text for audit/display
        if starting_point_text and not submission.starting_point_text:
            submission.starting_point_text = starting_point_text
            submission.save(update_fields=["starting_point_text"])
        return submission


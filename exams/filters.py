import django_filters

from .models import Student


class StudentFilter(django_filters.FilterSet):
    program_id = django_filters.NumberFilter(field_name="program_id")
    level_id = django_filters.NumberFilter(field_name="level_id")
    level = django_filters.NumberFilter(field_name="level_id")
    is_active = django_filters.BooleanFilter()
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Student
        fields = ["program_id", "level_id", "is_active"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(full_name__icontains=value) | queryset.filter(
            index_number__icontains=value
        )

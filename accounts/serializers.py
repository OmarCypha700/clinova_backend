from django.contrib.auth import authenticate
from rest_framework import serializers
from .models import User, School


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ['id', 'name', 'subdomain', 'code', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    school_id = serializers.IntegerField(required=False)

    def validate(self, data):
        request = self.context.get('request')
        
        # Get school from request context or data
        school = None
        if hasattr(request, 'school') and request.school:
            school = request.school
        elif data.get('school_id'):
            try:
                school = School.objects.get(id=data['school_id'], is_active=True)
            except School.DoesNotExist:
                raise serializers.ValidationError("Invalid school")
        
        if not school:
            raise serializers.ValidationError("School must be specified")
        
        # Try to get user from this school
        try:
            user_obj = User.objects.get(username=data.get("username"), school=school)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials")
        
        # Authenticate
        user = authenticate(
            username=data.get("username"),
            password=data.get("password")
        )

        if not user or user.school != school:
            raise serializers.ValidationError("Invalid credentials")

        if not user.is_active:
            raise serializers.ValidationError("User account is inactive")

        data["user"] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "role",
            "school",
            "school_name",
        ]


class ExaminerSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    school_name = serializers.CharField(source='school.name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "role",
            "school",
            "school_name",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined", "school", "school_name"]
    
    def create(self, validated_data):
        from core.middleware import get_current_school
        
        password = validated_data.pop('password', None)
        validated_data['role'] = 'examiner'
        
        # Get school from context
        school = get_current_school()
        if not school:
            raise serializers.ValidationError("School context not found")
        
        validated_data['school'] = school
        user = User(**validated_data)
        
        if password:
            user.set_password(password)
        user.save()
        return user
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance
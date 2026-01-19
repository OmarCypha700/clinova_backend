from django.contrib.auth.models import AbstractUser
from django.db import models


class School(models.Model):
    """Multi-tenancy: Each school is a tenant"""
    name = models.CharField(max_length=255, unique=True)
    subdomain = models.CharField(max_length=100, unique=True, db_index=True)
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # School settings
    # max_users = models.IntegerField(default=100)
    # max_students = models.IntegerField(default=1000)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("examiner", "Examiner"),
    )

    school = models.ForeignKey(
        School, 
        on_delete=models.CASCADE, 
        related_name='users',
        null=True  # Temporary for migration
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [['school', 'username']]  # Username unique per school
        indexes = [
            models.Index(fields=['school', 'username']),
            models.Index(fields=['school', 'role']),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.role}) - {self.school.name if self.school else 'No School'}"
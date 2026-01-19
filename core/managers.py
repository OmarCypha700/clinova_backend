# from django.db import models
# from django.db.models import Q


# class TenantManager(models.Manager):
#     """
#     Manager that automatically filters querysets by current school
#     """
    
#     def get_queryset(self):
#         from core.middleware import get_current_school
        
#         queryset = super().get_queryset()
#         school = get_current_school()
        
#         # Filter by current school if available
#         if school:
#             return queryset.filter(school=school)
        
#         return queryset
    
#     def all_tenants(self):
#         """Get all records across all tenants (use with caution)"""
#         return super().get_queryset()


# class TenantModel(models.Model):
#     """
#     Abstract base model for all tenant-aware models
#     """
#     school = models.ForeignKey(
#         'accounts.School',
#         on_delete=models.CASCADE,
#         related_name='%(class)s_set',
#         db_index=True,
#     )
    
#     objects = TenantManager()
#     all_objects = models.Manager()  # Unfiltered manager for admin/migrations
    
#     class Meta:
#         abstract = True
    
#     def save(self, *args, **kwargs):
#         from core.middleware import get_current_school
        
#         # Auto-assign current school if not set
#         if not self.school_id:
#             current_school = get_current_school()
#             if current_school:
#                 self.school = current_school
#             else:
#                 raise ValueError(
#                     f"Cannot save {self.__class__.__name__} without a school. "
#                     "Either set school explicitly or ensure request context has a school."
#                 )
        
#         super().save(*args, **kwargs)


from django.db import models


class TenantManager(models.Manager):
    """
    Manager that automatically filters querysets by current school
    """
    
    # def get_queryset(self):
    #     from core.middleware import get_current_school
        
    #     queryset = super().get_queryset()
    #     school = get_current_school()
        
    #     # Filter by current school if available
    #     if school:
    #         return queryset.filter(school=school)
        
    #     # If no school context, return the queryset as-is
    #     # This allows superusers and migrations to work
    #     return queryset

    def get_queryset(self):
        from core.middleware import get_current_school

        school = get_current_school()
        print("Manager school:", school) #get_current_school()

        if not school:
            return super().get_queryset().none()

        return super().get_queryset().filter(school=school)
    
    def all_tenants(self):
        """Get all records across all tenants (use with caution)"""
        return super().get_queryset()


class TenantModel(models.Model):
    """
    Abstract base model for all tenant-aware models
    """
    school = models.ForeignKey(
        'accounts.School',
        on_delete=models.CASCADE,
        # related_name='%(class)s_set',
        db_index=True
    )
    
    # Default manager with automatic tenant filtering
    objects = TenantManager()
    
    # Unfiltered manager for admin, migrations, and superusers
    all_objects = models.Manager()
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        from core.middleware import get_current_school
        
        # Auto-assign current school if not set
        if not self.school_id:
            current_school = get_current_school()
            if current_school:
                self.school = current_school
            else:
                # Check if we're in a migration or script context
                import sys
                is_migration = any('migrate' in arg for arg in sys.argv)
                is_shell = any('shell' in arg for arg in sys.argv)
                
                if is_migration or is_shell:
                    # In migration/shell, don't enforce school requirement
                    pass
                else:
                    raise ValueError(
                        f"Cannot save {self.__class__.__name__} without a school. "
                        "Either set school explicitly or ensure request context has a school."
                    )
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """
        Override delete to ensure we're only deleting objects from current school
        """
        from core.middleware import get_current_school
        
        current_school = get_current_school()
        
        # If there's a current school and it doesn't match, prevent deletion
        if current_school and self.school_id != current_school.id:
            raise ValueError(
                f"Cannot delete {self.__class__.__name__} from a different school. "
                f"Object belongs to {self.school.name}, current context is {current_school.name}."
            )
        
        super().delete(*args, **kwargs)
"""
Taxonomy repository.

Data access for the ``Category`` and ``Tag`` models. Pure persistence only —
no business logic.

Dependency rule: repositories may access models, nothing else.
"""

from portal.models import Category, Tag


class TaxonomyRepository:
    """Persistence layer for email categories and tags."""

    # -------------------- categories --------------------

    def list_categories(self, user):
        return Category.objects.filter(user=user).order_by("name")

    def get_category(self, user, pk):
        return Category.objects.filter(user=user, pk=pk).first()

    def get_or_create_category(self, user, name, color="primary", icon="bi-tag"):
        category, _ = Category.objects.get_or_create(
            user=user, name=name, defaults={"color": color, "icon": icon}
        )
        return category

    def delete_category(self, category):
        category.delete()

    # -------------------- tags --------------------

    def list_tags(self, user):
        return Tag.objects.filter(user=user).order_by("name")

    def get_tag(self, user, pk):
        return Tag.objects.filter(user=user, pk=pk).first()

    def get_or_create_tag(self, user, name, color="neutral"):
        tag, _ = Tag.objects.get_or_create(
            user=user, name=name, defaults={"color": color}
        )
        return tag

    def delete_tag(self, tag):
        tag.delete()
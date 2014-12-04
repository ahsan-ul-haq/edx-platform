from rest_framework import generics
from openedx.core.lib.api.permissions import ApiKeyHeaderPermission
from openedx.core.lib.api.serializers import PaginationSerializer


class ApiKeyHeaderPermissionMixin(object):
    """
    Mixin that protects views via an API key in the request header.
    """
    permission_classes = (ApiKeyHeaderPermission,)


class PaginatedListAPIViewWithKeyHeaderPermissions(ApiKeyHeaderPermissionMixin, generics.ListAPIView):
    """ Paginated list view secured by header keys. """
    paginate_by = 10
    paginate_by_param = 'page_size'
    pagination_serializer_class = PaginationSerializer

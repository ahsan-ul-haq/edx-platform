""" API implementation for course-oriented interactions. """

import logging

from django.http import Http404
from rest_framework.exceptions import ParseError
from rest_framework.generics import RetrieveAPIView, ListAPIView
from xmodule.modulestore.django import modulestore
from opaque_keys.edx.keys import CourseKey
from openedx.core.lib.api.views import PaginatedListAPIViewWithKeyHeaderPermissions, ApiKeyHeaderPermissionMixin

from course_api.courseware_access import get_course, get_course_child, get_course_descriptor
from course_api.v0.serializers import CourseSerializer, GradedContentSerializer, GradingPolicySerializer, \
    CourseContentSerializer


log = logging.getLogger(__name__)


class CourseContentMixin(object):
    default_depth = 0
    serializer_class = CourseContentSerializer
    lookup_field = 'course_id'

    def get_serializer_context(self):
        context = super(CourseContentMixin, self).get_serializer_context()
        context['course_id'] = self.kwargs.get('course_id')
        return context

    def depth(self, request):
        try:
            return int(request.QUERY_PARAMS.get('depth', self.default_depth))
        except ValueError:
            raise ParseError

    def get_course_or_404(self, request, course_id):
        depth = self.depth(request)
        course_descriptor = get_course(course_id, depth=depth)

        if not course_descriptor:
            raise Http404

        return course_descriptor

    def fetch_children(self, content_descriptor, depth=0):
        if not content_descriptor.has_children:
            return content_descriptor

        if depth == 0:
            content_descriptor.children = None
            return content_descriptor

        content_descriptor.children = [self.fetch_children(child, depth - 1) for child in
                                       content_descriptor.get_children()]
        return content_descriptor


class CourseContentList(CourseContentMixin, ApiKeyHeaderPermissionMixin, ListAPIView):
    """
    **Use Case**

        CourseContentList gets a collection of content for a given
        course. You can use the **uri** value in
        the response to get details for that content entity.

        The optional **depth** parameter that allows clients to get child content down to the specified tree level.

    **Example requests**:

        GET /{course_id}/content/

        GET /{course_id}/content/

    **Response Values**

        * category: The type of content.

        * name: The name of the content entity.

        * uri: The URI of the content entity.

        * id: The unique identifier for the course.

        * children: Content entities that this content entity contains.
    """

    default_depth = 1

    def get_queryset(self):
        course_id = self.kwargs.get('course_id')
        request = self.request
        course_descriptor = self.get_course_or_404(request, course_id)
        depth = self.depth(request)
        content = [self.fetch_children(child, depth - 1) for child in course_descriptor.get_children()]
        return content


class CourseContentDetail(CourseContentMixin, ApiKeyHeaderPermissionMixin, RetrieveAPIView):
    """
    **Use Case**

        CourseContentDetail returns a JSON collection for a specified
        CourseContent entity. If the specified CourseContent is the Course, the
        course representation is returned. You can use the uri values in the
        children collection in the JSON response to get details for that content
        entity.

        The optional **depth** parameter that allows clients to get child content down to the specified tree level.

    **Example Request**

          GET /{course_id}/content/{content_id}/

    **Response Values**

        * category: The type of content.

        * name: The name of the content entity.

        * uri: The URI of the content entity.

        * id: The unique identifier for the course.

        * children: Content entities that this content entity contains.
    """

    def get_object(self, queryset=None):
        course_id = self.kwargs.get('course_id')
        content_id = self.kwargs.get('content_id')
        request = self.request

        course_descriptor = self.get_course_or_404(request, course_id)
        course_key = course_descriptor.id
        depth = self.depth(request)

        content_descriptor, _content_key, _content = get_course_child(request, request.user, course_key, content_id)
        content = self.fetch_children(content_descriptor, depth)

        return content


class CourseList(CourseContentMixin, PaginatedListAPIViewWithKeyHeaderPermissions):
    """
    **Use Case**

        CourseList returns paginated list of courses in the edX Platform. The list can be
        filtered by course_id

    **Example Request**

          GET /
          GET /?course_id={course_id1},{course_id2}

    **Response Values**

        * category: The type of content. In this case, the value is always "course".

        * name: The name of the course.

        * uri: The URI to use to get details of the course.

        * course: The course number.

        * due:  The due date. For courses, the value is always null.

        * org: The organization specified for the course.

        * id: The unique identifier for the course.
    """
    serializer_class = CourseSerializer

    def get_queryset(self):
        course_ids = self.request.QUERY_PARAMS.get('course_id', None)

        course_descriptors = []
        if course_ids:
            course_ids = course_ids.split(',')
            for course_id in course_ids:
                course_key = CourseKey.from_string(course_id)
                course_descriptor = get_course_descriptor(course_key, 0)
                course_descriptors.append(course_descriptor)
        else:
            course_descriptors = modulestore().get_courses()

        results = [self.fetch_children(descriptor) for descriptor in course_descriptors]

        # Sort the results in a predictable manner.
        results.sort(key=lambda x: x.id)

        return results


class CourseDetail(CourseContentMixin, ApiKeyHeaderPermissionMixin, RetrieveAPIView):
    """
    **Use Case**

        CourseDetail returns details for a course.

        The optional **depth** parameter that allows clients to get child content down to the specified tree level.

    **Example requests**:

        GET /{course_id}/

        GET /{course_id}/?depth=2

    **Response Values**

        * category: The type of content.

        * name: The name of the course.

        * uri: The URI to use to get details of the course.

        * course: The course number.

        * content: When the depth parameter is used, a collection of child
          course content entities, such as chapters, sequentials, and
          components.

        * due:  The due date. For courses, the value is always null.

        * org: The organization specified for the course.

        * id: The unique identifier for the course.
    """

    serializer_class = CourseSerializer

    def get_object(self, queryset=None):
        course_id = self.kwargs.get('course_id')
        request = self.request
        course_descriptor = self.get_course_or_404(request, course_id)
        depth = self.depth(request)
        course_descriptor = self.fetch_children(course_descriptor, depth)
        return course_descriptor


class CourseGradedContent(CourseContentMixin, ApiKeyHeaderPermissionMixin, ListAPIView):
    """
    **Use Case**

        Retrieves course graded content and filtered children.

    **Example requests**:

        GET /{course_id}/graded_content/?filter_children_category=problem

    **Response Values**

        * category: The type of content.

        * name: The name of the content entity.

        * uri: The URI of the content entity.

        * id: The unique identifier for the course.

        * children: Content entities that this content entity contains.

        * format: The type of the content (e.g. Exam, Homework). Note: These values are course-dependent.
          Do not make any assumptions based on assignment type.

        * problems: {
            * id: The ID of the problem.

            * name: The name of the problem.
        }
    """

    serializer_class = GradedContentSerializer
    allow_empty = False

    def _filter_children(self, node, **kwargs):
        """ Retrieve the problems from the node/tree. """

        matched = True
        for name, value in kwargs.iteritems():
            matched &= (getattr(node, name, None) == value)
            if not matched:
                break

        if matched:
            return [node]

        if not node.has_children:
            return []

        problems = []
        for child in node.get_children():
            problems += self._filter_children(child, **kwargs)

        return problems

    def depth(self, request):
        # Load the entire content tree since we will need to filter down to the leaf nodes.
        return None

    def get_queryset(self):
        course_id = self.kwargs.get('course_id')
        course_descriptor = self.get_course_or_404(self.request, course_id)
        course_key = course_descriptor.id
        _modulestore = modulestore()

        items = _modulestore.get_items(course_key, settings={'graded': True})
        category = self.request.QUERY_PARAMS.get('filter_children_category')

        if not category:
            raise ParseError('The parameter filter_children_category must be supplied.')

        for item in items:
            item.children = self._filter_children(item, category=category)

        return items


class CourseGradingPolicy(ApiKeyHeaderPermissionMixin, ListAPIView):
    """
    **Use Case**

        Retrieves course grading policy.

    **Example requests**:

        GET /{course_id}/grading_policy/

    **Response Values**

        * assignment_type: The type of the assignment (e.g. Exam, Homework). Note: These values are course-dependent.
          Do not make any assumptions based on assignment type.

        * count: Number of assignments of the type.

        * dropped: Number of assignments of the type that are dropped.

        * weight: Effect of the assignment type on grading.
    """

    serializer_class = GradingPolicySerializer
    allow_empty = False

    def get_queryset(self):
        course_id = self.kwargs.get('course_id')
        course_key = CourseKey.from_string(course_id)

        course = modulestore().get_course(course_key)

        # Ensure the course exists
        if not course:
            raise Http404

        # Return the raw data. The serializer will handle the field mappings.
        return course.raw_grader

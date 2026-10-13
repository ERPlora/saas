"""A URLconf for the template tests only: the project's routes plus pages that extend the public
base, so the base, the navbar, the footer and the cookie banner are exercised through a real request
(session, context processors, CSP nonce) before any public page of their own exists.

Used with ``@pytest.mark.urls("public.tests.urls")``; never imported by the project.
"""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.template import RequestContext, Template
from django.urls import path

from config.urls import urlpatterns as project_urlpatterns

PAGE = Template(
    '{% extends "public/public_base.html" %}'
    "{% block title %}Test page{% endblock %}"
    '{% block page_content %}<h1 id="test-page">Test page</h1>{% endblock %}'
)


def public_page(request):
    return HttpResponse(PAGE.render(RequestContext(request)))


def page_with_message(request):
    messages.success(request, "Message sent")
    return public_page(request)


def error_page(request, status):
    return render(request, f"public/{status}.html", status=status)


urlpatterns = [
    path("test-public-page/", public_page, name="test_public_page"),
    path("test-public-page/message/", page_with_message, name="test_message_page"),
    path("test-error/<int:status>/", error_page, name="test_error_page"),
    *project_urlpatterns,
]

from urllib.parse import urljoin

from django.apps import apps
from django.conf import settings
from django.template.response import TemplateResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _
import requests
from wagtail.admin import messages
from webstories import Story

from .forms import ImportStoryForm
from .markup import AMPText

import re
import string
from urllib import parse

url_regex = re.compile("(artwork|src|poster|amp-orig-src|poster-portrait-src"
                       "|publisher-logo-src)\s*=\s*(?:(?:\"((?:[^\\\"]|\\.)"
                       "*)\")|(?:'((?:[^\\']|\\.)*)'))")

def _contains_whitespace(s):
    for c in s:
        if c in string.whitespace:
            return True
    return False

def _percent_encode_urls(regex_match):
    match_full_text = regex_match.group(0)
    value = regex_match.group(2)
    if not value.startswith('data:') and _contains_whitespace(value):
        return match_full_text.replace(value,
                                       parse.quote(value,
                                                   safe=string.punctuation))
    return match_full_text

def _make_url_absolute(regex_match, base_url):
    match_full_text = regex_match.group(0)
    value = regex_match.group(2)
    if not value.startswith('http') and not \
            value.strip() == '' and not \
            value.startswith('data:'):
        absolute_value = base_url + (''
                                     if base_url.endswith('/')
                                        or value.startswith('/')
                                     else '/') \
                         + value
        return match_full_text.replace(value, absolute_value)
    return match_full_text


def import_story(request):
    if request.method == 'POST':
        form = ImportStoryForm(request.POST, user=request.user)
        if form.is_valid():
            source_url = form.cleaned_data['source_url']
            try:
                req = requests.get(source_url)
                req.encoding = 'utf-8'
                html = req.text
                # Search and replace relative paths, appending the source url
                html = url_regex.sub(lambda x:
                                    _make_url_absolute(x, source_url), html)
                # Percent-encode URLs with spaces
                html = url_regex.sub(_percent_encode_urls, html)
                story = Story(html)
                story_is_valid = True
            except requests.exceptions.RequestException:
                form.add_error('source_url', _("Could not fetch URL."))
                story_is_valid = False
            except Story.InvalidStoryException:
                form.add_error('source_url', _("URL is not a valid web story."))
                story_is_valid = False

            if story_is_valid:
                page_model = apps.get_model(settings.WAGTAIL_WEBSTORIES_IMPORT_MODEL)

                if story.publisher_logo_src:
                    publisher_logo_src = urljoin(source_url, story.publisher_logo_src)
                else:
                    publisher_logo_src = ''

                if story.poster_portrait_src:
                    poster_portrait_src = urljoin(source_url, story.poster_portrait_src)
                else:
                    poster_portrait_src = ''

                if story.poster_square_src:
                    poster_square_src = urljoin(source_url, story.poster_square_src)
                else:
                    poster_square_src = ''

                if story.poster_landscape_src:
                    poster_landscape_src = urljoin(source_url, story.poster_landscape_src)
                else:
                    poster_landscape_src = ''

                page = page_model(
                    title=story.title,
                    publisher=story.publisher or '',
                    publisher_logo_src_original=publisher_logo_src,
                    poster_portrait_src_original=poster_portrait_src,
                    poster_square_src_original=poster_square_src,
                    poster_landscape_src_original=poster_landscape_src,
                    custom_css=story.custom_css or '',
                    original_url=source_url,
                )
                if getattr(settings, 'WAGTAIL_WEBSTORIES_CLEAN_HTML', True):
                    page.pages = [
                        ('page', {'id': subpage.id, 'html': AMPText(subpage.get_clean_html())})
                        for subpage in story.pages
                    ]
                else:
                    page.pages = [
                        ('page', {'id': subpage.id, 'html': AMPText(subpage.html)})
                        for subpage in story.pages
                    ]

                parent_page = form.cleaned_data['destination']
                parent_page.add_child(instance=page)
                messages.success(request, _("Story '%s' imported.") % page.title)
                return redirect('wagtailadmin_explore', parent_page.id)
    else:
        form = ImportStoryForm(user=request.user)

    return TemplateResponse(request, 'wagtail_webstories/admin/import.html', {
        'form': form,
    })

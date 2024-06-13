import hashlib
import json
import os.path
import requests

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from django.core.files.images import ImageFile
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.images import get_image_model_string
from wagtail.images.models import Filter
from wagtail.models import Page, get_page_models

from webstories import Story

from .blocks import PageBlock
from .markup import AMPText


# Retrieve the (possibly custom) image model. Can't use get_image_model as of Wagtail 2.11, as we
# need require_ready=False: https://github.com/wagtail/wagtail/pull/6568
Image = apps.get_model(get_image_model_string(), require_ready=False)


def _fetch(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36'}
    return requests.get(url, headers=headers)


def _name_from_url(url):
    url_obj = urlparse(url)
    filename = url_obj.path.split('/')[-1]
    return os.path.splitext(filename)[0]


class WebStoryPageMixin(models.Model):
    PUBLISHER_LOGO_IMAGE_FILTER = 'original'
    PORTRAIT_IMAGE_FILTER = 'fill-640x853'
    SQUARE_IMAGE_FILTER = 'fill-640x640'
    LANDSCAPE_IMAGE_FILTER = 'fill-853x640'

    publisher = models.CharField(blank=False, max_length=2047)

    publisher_logo = models.ForeignKey(
        Image, blank=True, null=True, related_name='+', on_delete=models.SET_NULL)
    publisher_logo_src_original = models.URLField(
        'Publisher logo URL', blank=True, max_length=2047, editable=False)

    poster_image = models.ForeignKey(
        Image, blank=True, null=True, related_name='+', on_delete=models.SET_NULL)
    poster_portrait_src_original = models.URLField(
        'Poster portrait image URL', blank=True, max_length=2047, editable=False)
    poster_square_src_original = models.URLField(
        'Poster square image URL', blank=True, max_length=2047, editable=False)
    poster_landscape_src_original = models.URLField(
        'Poster landscape image URL', blank=True, max_length=2047, editable=False)

    original_url = models.URLField('Original URL', blank=True, max_length=2047)

    custom_css = models.TextField(blank=True)

    pages = StreamField([
        ('page', PageBlock()),
    ], use_json_field=True)

    web_story_content_panels = [
        FieldPanel('custom_css'),
        FieldPanel('pages'),
    ]

    web_story_promote_panels = [
        MultiFieldPanel([
            FieldPanel('publisher'),
            FieldPanel('publisher_logo'),
            FieldPanel('original_url'),
        ], heading="Publisher"),
        MultiFieldPanel([
            FieldPanel('poster_image'),
        ], heading="Poster"),
    ]        

    def clean(self):
        super().clean()

        errors = {}
        if not (self.publisher_logo or self.publisher_logo_src_original):
            errors['publisher_logo'] = _("A publisher logo must be provided.")

        if not (self.poster_image or self.poster_portrait_src_original):
            errors['poster_image'] = _("A poster image must be provided.")

        if errors:
            raise ValidationError(errors)

    def get_publisher_logo_rendition(self):
        if self.publisher_logo:
            return self.publisher_logo.get_rendition(self.PUBLISHER_LOGO_IMAGE_FILTER)

    @property
    def publisher_logo_src(self):
        rendition = self.get_publisher_logo_rendition()
        if rendition:
            return rendition.url
        else:
            return urljoin(self.original_url, self.publisher_logo_src_original)

    def get_poster_portrait_rendition(self):
        if self.poster_image:
            return self.poster_image.get_rendition(self.PORTRAIT_IMAGE_FILTER)

    @property
    def poster_portrait_src(self):
        rendition = self.get_poster_portrait_rendition()
        if rendition:
            return rendition.url
        else:
            return urljoin(self.original_url, self.poster_portrait_src_original)

    def get_poster_square_rendition(self):
        if self.poster_image:
            return self.poster_image.get_rendition(self.SQUARE_IMAGE_FILTER)

    @property
    def poster_square_src(self):
        rendition = self.get_poster_square_rendition()
        if rendition:
            return rendition.url
        else:
            return urljoin(self.original_url, self.poster_square_src_original)

    def get_poster_landscape_rendition(self):
        if self.poster_image:
            return self.poster_image.get_rendition(self.LANDSCAPE_IMAGE_FILTER)

    @property
    def poster_landscape_src(self):
        rendition = self.get_poster_landscape_rendition()
        if rendition:
            return rendition.url
        else:
            return urljoin(self.original_url, self.poster_landscape_src_original)

    @property
    def linked_data(self):
        return {
            "@context": "http://schema.org",
            "@type": "NewsArticle",
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": self.full_url,
            },
            "headline": self.title,
            "image": list(filter(bool, [
                self.poster_portrait_src, self.poster_square_src, self.poster_landscape_src
            ])),
            "datePublished": (
                self.first_published_at and self.first_published_at.isoformat()
            ),
            "dateModified": (
                self.last_published_at and self.last_published_at.isoformat()
            ),
            "publisher": {
                "@type": "Organisation",
                "name": self.publisher,
                "logo": {
                    "@type": "ImageObject",
                    "url": self.publisher_logo_src
                }
            }
        }

    def get_context(self, request):
        context = super().get_context(request)
        context['ld_json'] = json.dumps(self.linked_data)
        return context

    def import_images(self):
        # if flag indicates we have imported images on this instance already,
        # don't repeat; this allows us to call import_images / save within a
        # post_save signal without the second save retriggering a full import_images
        if getattr(self, '_has_imported_images', False):
            return False  # report no changes

        meta_has_changed = self._import_metadata_images()
        content_has_changed = self._import_content_images()
        self._has_imported_images = True
        return meta_has_changed or content_has_changed

    def _import_metadata_images(self):
        has_changed = False

        if self.publisher_logo_src_original and not self.publisher_logo:
            try:
                self.publisher_logo, created = self._image_from_url(
                    urljoin(self.original_url,
                            self.publisher_logo_src_original),
                    title="%s logo" % self.publisher,
                )
                has_changed = True
            except requests.exceptions.RequestException:
                pass

        if self.poster_portrait_src_original and not self.poster_image:
            try:
                portrait_image_file = self._image_file_from_url(
                    urljoin(self.original_url,
                            self.poster_portrait_src_original)
                )
                self.poster_image, created = self._image_from_image_file(
                    portrait_image_file, title=self.title
                )
                has_changed = True
            except requests.exceptions.RequestException:
                created = False

            if created:
                # Pre-generate renditions for whichever of portrait, square and landscape poster images
                # have been supplied, indexed under PORTRAIT_IMAGE_FILTER, SQUARE_IMAGE_FILTER
                # and LANDSCAPE_IMAGE_FILTER respectively so that when we look those up again we get
                # the original appropriately-cropped version
                portrait_filter = Filter(self.PORTRAIT_IMAGE_FILTER)
                self.poster_image.renditions.create(
                    filter_spec=self.PORTRAIT_IMAGE_FILTER,
                    file=portrait_image_file,
                    focal_point_key=portrait_filter.get_cache_key(
                        self.poster_image)
                )

                if self.poster_square_src_original:
                    square_filter = Filter(self.SQUARE_IMAGE_FILTER)
                    try:
                        self.poster_image.renditions.create(
                            filter_spec=self.SQUARE_IMAGE_FILTER,
                            file=self._image_file_from_url(
                                urljoin(self.original_url,
                                        self.poster_square_src_original)
                            ),
                            focal_point_key=square_filter.get_cache_key(
                                self.poster_image)
                        )
                    except requests.exceptions.RequestException:
                        pass

                if self.poster_landscape_src_original:
                    landscape_filter = Filter(self.LANDSCAPE_IMAGE_FILTER)
                    try:
                        self.poster_image.renditions.create(
                            filter_spec=self.LANDSCAPE_IMAGE_FILTER,
                            file=self._image_file_from_url(
                                urljoin(self.original_url,
                                        self.poster_landscape_src_original)
                            ),
                            focal_point_key=landscape_filter.get_cache_key(
                                self.poster_image)
                        )
                    except requests.exceptions.RequestException:
                        pass

        return has_changed

    def _import_content_images(self):
        new_pages = []
        has_changed = False

        for page in self.pages:
            if not isinstance(page.block, PageBlock):
                # leave unrecognised block types unchanged in the output
                new_pages.append((page.block_type, page.value))
                continue

            page_html = page.value['html'].source
            page_dom = dom = BeautifulSoup(page_html, 'html.parser')
            # look for <amp-img> elements with src attributes
            for img_tag in page_dom.select('amp-img[src]'):
                image_url = urljoin(self.original_url, img_tag['src'])
                title = (
                    img_tag.get('alt')
                    or _name_from_url(image_url)
                    or ("image from story: %s" % self.title)
                )
                try:
                    image, created = self._image_from_url(
                        image_url, title=title)
                    img_tag['data-wagtail-image-id'] = image.id
                    del img_tag['src']
                    has_changed = True
                except requests.exceptions.RequestException:
                    pass

            page.value['html'] = AMPText(str(page_dom))
            new_pages.append((page.block_type, page.value))

        if has_changed:
            self.pages = new_pages

        return has_changed

    def _image_file_from_url(self, url):
        url_obj = urlparse(url)
        filename = url_obj.path.split('/')[-1] or 'image'
        response = _fetch(url)
        response.raise_for_status()
        return ImageFile(ContentFile(response.content), name=filename)

    def _create_image(self, file, title=None):
        """
        Return an unsaved image instance for the given ImageFile and title. Override this if your
        image model requires extra metadata to be filled in, or you want to assign it to a specific
        collection
        """
        return Image(file=file, title=title)

    def _image_from_image_file(self, file, title=None):
        with file.open() as f:
            file_hash = hashlib.sha1(f.read()).hexdigest()

        # check if we already have an image with the same file content
        image = Image.objects.filter(file_hash=file_hash).first()
        if image:
            return (image, False)
        else:
            image = self._create_image(file, title=title)
            image.save()
            image.get_file_hash()  # ensure file_hash is populated
            return (image, True)

    def _image_from_url(self, url, title=None):
        image_file = self._image_file_from_url(url)
        return self._image_from_image_file(image_file, title=title)

    def import_videos(self):
        # if flag indicates we have imported videos on this instance already,
        # don't repeat; this allows us to call import_videos / save within a
        # post_save signal without the second save retriggering a full import_videos
        if getattr(self, '_has_imported_videos', False):
            return False  # report no changes

        content_has_changed = False
        new_pages = []

        for page in self.pages:
            if not isinstance(page.block, PageBlock):
                # leave unrecognised block types unchanged in the output
                new_pages.append((page.block_type, page.value))
                continue

            page_html = page.value['html'].source
            page_dom = dom = BeautifulSoup(page_html, 'html.parser')
            # look for <amp-video> elements
            for video_tag in page_dom.select('amp-video'):
                poster_url = video_tag.get('poster')
                if poster_url:
                    try:
                        poster_image_file = self._image_file_from_url(
                            urljoin(self.original_url, poster_url)
                        )
                    except requests.exceptions.RequestException:
                        poster_image_file = None
                else:
                    poster_image_file = None

                width = video_tag.get('width')
                height = video_tag.get('height')
                fallback_title = "video from story: %s" % self.title

                video_url = video_tag.get('src')
                if video_url:
                    title = _name_from_url(video_url) or fallback_title
                    try:
                        video, created = self._video_from_url(
                            urljoin(self.original_url, video_url),
                            title=title, width=width, height=height,
                            thumbnail=poster_image_file
                        )
                        video_tag['data-wagtail-media-id'] = video.id
                        del video_tag['src']
                        content_has_changed = True
                    except requests.exceptions.RequestException:
                        pass

                for source_tag in video_tag.find_all('source', recursive=False):
                    video_url = source_tag.get('src')
                    if video_url:
                        title = _name_from_url(video_url) or fallback_title
                        try:
                            video, created = self._video_from_url(
                                urljoin(self.original_url, video_url),
                                title=title, width=width, height=height,
                                thumbnail=poster_image_file
                            )
                            source_tag['data-wagtail-media-id'] = video.id
                            del source_tag['src']
                            content_has_changed = True
                        except requests.exceptions.RequestException:
                            pass

            page.value['html'] = AMPText(str(page_dom))
            new_pages.append((page.block_type, page.value))

        if content_has_changed:
            self.pages = new_pages

        self._has_imported_videos = True
        return content_has_changed

    def _video_file_from_url(self, url):
        url_obj = urlparse(url)
        filename = url_obj.path.split('/')[-1] or 'video'
        response = _fetch(url)
        response.raise_for_status()
        return File(ContentFile(response.content), name=filename)

    def _create_video(self, file, **kwargs):
        from wagtailmedia.models import get_media_model
        Media = get_media_model()
        # for wagtailmedia < 0.7, need to ensure that the duration field
        # is populated
        if 'duration' not in kwargs and not Media._meta.get_field('duration').blank:
            kwargs['duration'] = 0
        video = Media(file=file, **kwargs)
        return video

    def _video_from_url(self, url, **kwargs):
        video_file = self._video_file_from_url(url)
        video = self._create_video(video_file, type='video', **kwargs)
        video.save()
        return (video, True)

    class Meta:
        abstract = True


class BaseWebStoryPage(WebStoryPageMixin, Page):
    content_panels = Page.content_panels + WebStoryPageMixin.web_story_content_panels
    promote_panels = Page.promote_panels + WebStoryPageMixin.web_story_promote_panels

    class Meta:
        abstract = True


def get_story_page_models():
    """
    Return a list of all non-abstract page models that inherit from WebStoryPageMixin
    """
    return [
        model for model in get_page_models()
        if issubclass(model, WebStoryPageMixin)
    ]


class ExternalStory(models.Model):
    url = models.TextField()
    # a SHA-1 hash of the URL
    url_hash = models.CharField(
        max_length=40, editable=False, unique=True, db_index=True)
    title = models.TextField(blank=True, editable=False)
    publisher = models.TextField(blank=False, editable=False)
    publisher_logo_src = models.TextField(
        'Publisher logo URL', blank=True, editable=False)
    poster_portrait_src = models.TextField(
        'Poster portrait image URL', blank=True, editable=False)
    poster_square_src = models.TextField(
        'Poster square image URL', blank=True, editable=False)
    poster_landscape_src = models.TextField(
        'Poster landscape image URL', blank=True, editable=False)
    last_fetched_at = models.DateTimeField()

    @classmethod
    def get_for_url(cls, url):
        url_hash = hashlib.sha1(url.encode('utf-8')).hexdigest()
        try:
            return cls.objects.get(url_hash=url_hash)
        except cls.DoesNotExist:
            html = _fetch(url).text
            story = Story(html)
            result, created = cls.objects.update_or_create(
                url_hash=url_hash, defaults={
                    'url': url,
                    'title': story.title,
                    'publisher': story.publisher,
                    'publisher_logo_src': urljoin(url, story.publisher_logo_src) if story.publisher_logo_src else '',
                    'poster_portrait_src': urljoin(url, story.poster_portrait_src) if story.poster_portrait_src else '',
                    'poster_square_src': urljoin(url, story.poster_square_src) if story.poster_square_src else '',
                    'poster_landscape_src': urljoin(url, story.poster_landscape_src) if story.poster_landscape_src else '',
                    'last_fetched_at': timezone.now(),
                }
            )
            return result

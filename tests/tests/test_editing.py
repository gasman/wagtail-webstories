import shutil

from django.contrib.auth.models import User
from django.test import override_settings

from wagtail.images.models import Image
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase
from wagtail.test.utils.form_data import nested_form_data, streamfield

from tests.models import StoryPage
from tests.utils import get_test_image_file, TEST_MEDIA_DIR


class TestEditing(WagtailPageTestCase):
    def setUp(self):
        shutil.rmtree(TEST_MEDIA_DIR, ignore_errors=True)
        self.user = User.objects.create_superuser(username='admin', email='admin@example.com', password='12345')
        self.client.login(username='admin', password='12345')
        self.home = Page.objects.filter(depth=2).first()

    def tearDown(self):
        shutil.rmtree(TEST_MEDIA_DIR, ignore_errors=True)

    def test_clean_on_save(self):
        logo = Image.objects.create(
            title="logo",
            file=get_test_image_file(colour='white'),
        )
        poster = Image.objects.create(
            title="poster",
            file=get_test_image_file(colour='white'),
        )

        self.assertCanCreate(self.home, StoryPage, nested_form_data({
            'title': "Wagtail spotting",
            'publisher': "Torchbox",
            'publisher_logo': logo.id,
            'poster_image': poster.id,
            'pages': streamfield([
                ('page', {
                    'id': 'cover',
                    'html': """
                        <amp-story-page id="cover">
                            <amp-story-grid-layer template="vertical">
                                <h1>Wagtail spotting</h1>
                                <script>alert("boo!")</script>
                            </amp-story-grid-layer>
                        </amp-story-page>
                    """
                }),
            ])
        }))

        page = StoryPage.objects.get(title="Wagtail spotting")
        cover_html = page.pages[0].value['html'].source
        self.assertIn("<h1>Wagtail spotting</h1>", cover_html)
        self.assertNotIn('<script>alert("boo!")</script>', cover_html)

    @override_settings(WAGTAIL_WEBSTORIES_CLEAN_HTML=False)
    def test_disable_cleaning_on_save(self):
        logo = Image.objects.create(
            title="logo",
            file=get_test_image_file(colour='white'),
        )
        poster = Image.objects.create(
            title="poster",
            file=get_test_image_file(colour='white'),
        )

        self.assertCanCreate(self.home, StoryPage, nested_form_data({
            'title': "Wagtail spotting",
            'publisher': "Torchbox",
            'publisher_logo': logo.id,
            'poster_image': poster.id,
            'pages': streamfield([
                ('page', {
                    'id': 'cover',
                    'html': """
                        <amp-story-page id="cover">
                            <amp-story-grid-layer template="vertical">
                                <h1>Wagtail spotting</h1>
                                <script>alert("boo!")</script>
                            </amp-story-grid-layer>
                        </amp-story-page>
                    """
                }),
            ])
        }))

        page = StoryPage.objects.get(title="Wagtail spotting")
        cover_html = page.pages[0].value['html'].source
        self.assertIn("<h1>Wagtail spotting</h1>", cover_html)
        self.assertIn('<script>alert("boo!")</script>', cover_html)

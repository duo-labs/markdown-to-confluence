import unittest
import textwrap

from convert import convtoconf, ConfluenceRenderer


class TestConvert(unittest.TestCase):
    def __init__(self, *args):
        self.maxDiff = None
        super().__init__(*args)

    def testLocalImageTag(self):
        have_path = '/images/example.png'
        want = '<ac:image><ri:attachment ri:filename="example.png" /></ac:image>'
        renderer = ConfluenceRenderer()
        got = renderer.image(have_path, '', '')
        got = got.strip()
        self.assertEqual(len(renderer.attachments), 1)
        self.assertEqual(renderer.attachments[0], have_path)
        self.assertEqual(got, want)

    def testExternalImageTag(self):
        have_url = 'https://example.com/images/example.png'
        want = '<ac:image><ri:url ri:value="{}" /></ac:image>'.format(have_url)
        renderer = ConfluenceRenderer()
        got = renderer.image(have_url, '', '')
        got = got.strip()
        self.assertEqual(len(renderer.attachments), 0)
        self.assertEqual(got, want)

    def testAuthorTag(self):
        author_key = '1234567890'
        want = textwrap.dedent(
            '''<h1>Authors</h1><p><ac:structured-macro ac:name="profile-picture" ac:schema-version="1">
                <ac:parameter ac:name="User"><ri:user ri:userkey="{user_key}" /></ac:parameter>
            </ac:structured-macro>&nbsp;
            <ac:link><ri:user ri:userkey="{user_key}" /></ac:link></p>'''.
            format(user_key=author_key))
        renderer = ConfluenceRenderer(authors=[author_key])
        got = renderer.render_authors()
        got = got.strip()
        self.assertEqual(got, want)

    def testHeader(self):
        have = 'test'
        want = '<h1>{}</h1>'.format(have)
        renderer = ConfluenceRenderer()
        got = renderer.header(have, 1)
        got = got.strip()
        self.assertEqual(got, want)
        self.assertEqual(renderer.has_toc, True)
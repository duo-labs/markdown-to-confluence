import logging
import json
from typing import List, Optional
import requests
import os

from urllib.parse import urljoin

API_HEADERS = {
    'User-Agent': 'markdown-to-confluence',
}

MULTIPART_HEADERS = {
    'X-Atlassian-Token': 'nocheck'  # Only need this for form uploads
}

DEFAULT_LABEL_PREFIX = 'global'

log = logging.getLogger(__name__)


class MissingArgumentException(Exception):
    def __init__(self, arg):
        self.message = 'Missing required argument: {}'.format(arg)


class Confluence():
    def __init__(self,
                 api_url=None,
                 username=None,
                 password=None,
                 headers=None,
                 dry_run=False,
                 _client=None):
        """Creates a new Confluence API client.
        
        Arguments:
            api_url {str} -- The URL to the Confluence API root (e.g. https://wiki.example.com/api/rest/)
            username {str} -- The Confluence service account username
            password {str} -- The Confluence service account password
            headers {list(str)} -- The HTTP headers which will be set for all requests
            dry_run {str} -- The Confluence service account password
        """
        # A common gotcha will be given a URL that doesn't end with a /, so we
        # can account for this
        if not api_url.endswith('/'):
            api_url = api_url + '/'
        self.api_url = api_url

        self.username = username
        self.password = password
        self.dry_run = dry_run

        if _client is None:
            _client = requests.Session()

        self._session = _client
        self._session.auth = (self.username, self.password)
        for header in headers or []:
            try:
                name, value = header.split(':', 1)
            except ValueError:
                name, value = header, ''
            self._session.headers[name] = value.lstrip()

    def _require_kwargs(self, kwargs):
        """Ensures that certain kwargs have been provided
        
        Arguments:
            kwargs {dict} -- The dict of required kwargs
        """
        missing = []
        for k, v in kwargs.items():
            if not v:
                missing.append(k)
        if missing:
            raise MissingArgumentException(missing)

    def _request(self,
                 method='GET',
                 path='',
                 params=None,
                 files=None,
                 data=None,
                 headers=None):
        url = urljoin(self.api_url, path)

        if not headers:
            headers = {}
        headers.update(API_HEADERS)

        if files:
            headers.update(MULTIPART_HEADERS)

        if data:
            headers.update({'Content-Type': 'application/json'})

        if self.dry_run:
            log.info('''{method} {url}:
            Params: {params}
            Data: {data}
            Files: {files}'''.format(method=method,
                                     url=url,
                                     params=params,
                                     data=data,
                                     files=files))
            if method != 'GET':
                return {}

        response = self._session.request(method=method,
                                         url=url,
                                         params=params,
                                         json=data,
                                         headers=headers,
                                         files=files)

        if not response.ok:
            log.info('''{method} {url}: {status_code} {reason}
            Params: {params}
            Data: {data}
            Files: {files}'''.format(method=method,
                                     url=url,
                                     status_code=response.status_code,
                                     reason=response.reason,
                                     params=params,
                                     data=data,
                                     files=files))
            log.error('Error response: {}'.format(response.content))
            return response.json()

        # Will probably want to be more robust here, but this should work for now
        log.debug('Success response: {}'.format(response.content))
        return response.json()

    def get(self, path=None, params=None):
        return self._request(method='GET', path=path, params=params)

    def post(self, path=None, params=None, data=None, files=None):
        return self._request(method='POST',
                             path=path,
                             params=params,
                             data=data,
                             files=files)

    def put(self, path=None, params=None, data=None):
        return self._request(method='PUT', path=path, params=params, data=data)

    def exists(self, space: str, id_label: str, ancestor_id=None):
        """Returns the Confluence page that matches the provided metdata, if it exists.

        Specifically, this leverages a Confluence Query Language (CQL) query
        against the Confluence API. We assume that each slug is unique, at
        least to the provided space/ancestor_id.
        
        Arguments:
            space {str} -- The Confluence space to use for filtering posts
            slug {str} -- The page slug
            ancestor_id {str} -- The ID of the parent page
        """

        cql_args = []
        if id_label:
            cql_args.append('label=\'{}\''.format(id_label))
        if ancestor_id:
            cql_args.append('ancestor={}'.format(ancestor_id))
        if space:
            cql_args.append('space={!r}'.format(space))

        cql = ' and '.join(cql_args)

        params = {'expand': 'version', 'cql': cql}
        response = self.get(path='content/search', params=params)
        # log.info('Response: {}'.format(response))
        if not response.get('size'):
            return None
        return response['results'][0]

    def create_labels(self, page_id: str, id_label: str, tags: Optional[List[str]]=None):
        """Creates labels for the page to both assist with searching as well
        as categorization.

        We specifically require a slug to be provided, since this is how we
        determine if a page exists. Any other tags are optional.
        
        Keyword Arguments:
            page_id {str} -- The ID of the existing page to which the label should apply
            slug {str} -- The page slug to use as the label value
            tags {list(str)} -- Any other tags to apply to the post
        """
        labels = [{'prefix': DEFAULT_LABEL_PREFIX, 'name': id_label}]

        if tags is None:
            tags = []
        for tag in tags:
            labels.append({'prefix': DEFAULT_LABEL_PREFIX, 'name': tag})
        path = 'content/{page_id}/label'.format(page_id=page_id)
        response = self.post(path=path, data=labels)

        # Do a sanity check to ensure that the label for the slug appears in
        # the results, since that's needed for us to find the page later.
        labels = response.get('results', [])
        if not labels:
            log.error(
                'No labels found after attempting to update page {}'.format(
                    id_label))
            log.error('Here\'s the response we got:\n{}'.format(response))
            return labels

        if not any(label['name'] == id_label for label in labels):
            log.error(
                'Returned labels missing the expected slug: {}'.format(id_label))
            log.error('Here are the labels we got: {}'.format(labels))
            return labels

        log.info(
            'Created the following labels for page {id_label}: {labels}'.format(
                id_label=id_label,
                labels=', '.join(label['name'] for label in labels)))
        return labels

    def _create_page_payload(self,
                             content=None,
                             title=None,
                             ancestor_id=None,
                             space=None,
                             type='page'):
        return {
            'type': type,
            'title': title,
            'space': {
                'key': space
            },
            'body': {
                'storage': {
                    'representation': 'storage',
                    'value': content
                }
            },
            'ancestors': [{
                'id': str(ancestor_id)
            }]
        }

    def get_attachments(self, post_id):
        """Gets the attachments for a particular Confluence post
        
        Arguments:
            post_id {str} -- The Confluence post ID
        """
        response = self.get("/content/{}/attachments".format(post_id))
        return response.get('results', [])

    def upload_attachment(self, post_id=None, attachment_path=None):
        """Uploads an attachment to a Confluence post
        
        Keyword Arguments:
            post_id {str} -- The Confluence post ID
            attachment_path {str} -- The absolute path to the attachment
        """
        path = 'content/{}/child/attachment'.format(post_id)
        if not os.path.exists(attachment_path):
            log.error('Attachment {} does not exist'.format(attachment_path))
            return
        log.info(
            'Uploading attachment {attachment_path} to post {post_id}'.format(
                attachment_path=attachment_path, post_id=post_id))
        self.post(path=path,
                  params={'allowDuplicated': 'true'},
                  files={'file': open(attachment_path, 'rb')})
        log.info('Uploaded {} to post ID {}'.format(attachment_path, post_id))

    def get_author(self, username):
        """Returns the Confluence author profile for the provided username,
        if it exists.

        Arguments:
            username {str} -- The Confluence username
        """
        log.info('Looking up Confluence user key for {}'.format(username))
        response = self.get(path='user', params={'username': username})
        if not isinstance(response, dict) or not response.get('userKey'):
            log.error('No Confluence user key for {}'.format(username))
            return {}
        return response

    def create(self,
               id_label: str,
               space: str,
               title: str,
               ancestor_id: str,
               type: str='page') -> str:
        """Creates a new page with the provided content.

        If an ancestor_id is specified, then the page will be created as a
        child of that ancestor page.
        
        Keyword Arguments:
            content {str} -- The HTML content to upload (required)
            space {str} -- The Confluence space where the page should reside
            title {str} -- The page title
            ancestor_id {str} -- The ID of the parent Confluence page
            slug {str} -- The unique slug for the page
            tags {list(str)} -- The list of tags for the page
            attachments {list(str)} -- List of absolute paths to attachments
                which should uploaded.
        """
        page = self._create_page_payload(
            content='Upload in progress...',
            title=title,
            ancestor_id=ancestor_id,
            space=space,
            type=type
        )
        response = self.post(path='content/', data=page)
        log.info('Create response: {}'.format(response))

        page_id = response['id']
        page_url = urljoin(self.api_url, response['_links']['webui'])

        log.info('Page "{title}" (id {page_id}) created successfully at {url}'.
                 format(title=title, page_id=response.get('id'), url=page_url))
        
        self.create_labels(page_id, id_label)

        return response

    def update(
        self,
        page_id: str,
        page_version: int,
        content: str,
        space: str,
        title: str,
        ancestor_id: str,
        id_label: str,
        tags: Optional[List[str]] = None,
        attachments: Optional[List[str]]=None,
        type='page'
    ):
        
        # Since the page already has an ID in Confluence, before updating our
        # content which references certain attachments, we should make sure
        # those attachments have been uploaded.
        if attachments is None:
            attachments = []

        for attachment in attachments:
            self.upload_attachment(post_id=page_id, attachment_path=attachment)

        # Next, we can create the updated page structure
        new_page = self._create_page_payload(content=content,
                                             title=title,
                                             ancestor_id=ancestor_id,
                                             space=space,
                                             type=type)
        # Increment the version number, as required by the Confluence API
        # https://docs.atlassian.com/ConfluenceServer/rest/7.1.0/#api/content-update
        new_version = page_version + 1
        new_page['version'] = {'number': new_version}

        # With the attachments uploaded, and our new page structure created,
        # we can upload the final content up to Confluence.
        path = 'content/{}'.format(page_id)
        response = self.put(path=path, data=new_page)

        page_url = urljoin(self.api_url, response['_links']['webui'])

        # Finally, we can update the labels on the page
        self.create_labels(page_id=page_id, id_label=id_label, tags=tags)

        log.info('Page "{title}" (id {page_id}) updated successfully at {url}'.
                 format(title=title, page_id=page_id, url=page_url))
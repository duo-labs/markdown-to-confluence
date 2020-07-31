import argparse
import logging
import os
import requests
import git
import sys

from confluence import Confluence
from convert import convtoconf, parse
"""Deploys Markdown posts to Confluenceo

This script is meant to be executed as either part of a CI/CD job or on an
adhoc basis.
"""

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)

SUPPORTED_FORMATS = ['.md']


def get_environ_headers(prefix):
    """Returns a list of headers read from environment variables whose key
    starts with prefix.

    The header names are derived from the environment variable keys by
    stripping the prefix. The header values are set to the environment
    variable values.

    Arguments:
        prefix {str} -- The prefix of the environment variable keys which specify headers.
    """
    headers = []
    for key, value in os.environ.items():
        if key.startswith(prefix):
            header_name = key[len(prefix):]
            headers.append("{}:{}".format(header_name, value))
    return headers


def get_last_modified(repo):
    """Returns the paths to the last modified files in the provided Git repo

    Arguments:
        repo {git.Repo} -- The repository object
    """
    changed_files = repo.git.diff('HEAD~1..HEAD', name_only=True).split()
    for filepath in changed_files:
        if not filepath.startswith('content/'):
            changed_files.remove(filepath)
    return changed_files


def get_slug(filepath, prefix=''):
    """Returns the slug for a given filepath

    Arguments:
        filepath {str} -- The filepath for the post
        prefix {str} -- Any prefixes to the slug
    """
    slug, _ = os.path.splitext(os.path.basename(filepath))
    # Confluence doesn't support searching for labels with a "-",
    # so we need to adjust it.
    slug = slug.replace('-', '_')
    if prefix:
        slug = '{}_{}'.format(prefix, slug)
    return slug


def parse_args():
    parser = argparse.ArgumentParser(
        description='Converts and deploys a markdown post to Confluence')
    parser.add_argument(
        '--git',
        dest='git',
        default=os.getcwd(),
        help='The path to your Git repository (default: {}))'.format(
            os.getcwd()))
    parser.add_argument(
        '--api_url',
        dest='api_url',
        default=os.getenv('CONFLUENCE_API_URL'),
        help=
        'The URL to the Confluence API (e.g. https://wiki.example.com/rest/api/)'
    )
    parser.add_argument(
        '--username',
        dest='username',
        default=os.getenv('CONFLUENCE_USERNAME'),
        help=
        'The username for authentication to Confluence (default: env(\'CONFLUENCE_USERNAME\'))'
    )
    parser.add_argument(
        '--password',
        dest='password',
        default=os.getenv('CONFLUENCE_PASSWORD'),
        help=
        'The password for authentication to Confluence (default: env(\'CONFLUENCE_PASSWORD\'))'
    )
    parser.add_argument(
        '--space',
        dest='space',
        default=os.getenv('CONFLUENCE_SPACE'),
        help=
        'The Confluence space where the post should reside (default: env(\'CONFLUENCE_SPACE\'))'
    )
    parser.add_argument(
        '--ancestor_id',
        dest='ancestor_id',
        default=os.getenv('CONFLUENCE_ANCESTOR_ID'),
        help=
        'The Confluence ID of the parent page to place posts under (default: env(\'CONFLUENCE_ANCESTOR_ID\'))'
    )
    parser.add_argument(
        '--global_label',
        dest='global_label',
        default=os.getenv('CONFLUENCE_GLOBAL_LABEL'),
        help=
        'The label to apply to every post for easier discovery in Confluence (default: env(\'CONFLUENCE_GLOBAL_LABEL\'))'
    )
    parser.add_argument(
        '--header',
        metavar='HEADER',
        dest='headers',
        action='append',
        default=get_environ_headers('CONFLUENCE_HEADER_'),
        help=
        'Extra header to include in the request when sending HTTP to a server. May be specified multiple times. (default: env(\'CONFLUENCE_HEADER_<NAME>\'))'
    )
    parser.add_argument(
        '--dry-run',
        dest='dry_run',
        action='store_true',
        help=
        'Print requests that would be sent- don\'t actually make requests against Confluence (note: we return empty responses, so this might impact accuracy)'
    )
    parser.add_argument(
        '--static-path',
        dest='static_path',
        default='static',
        help='The prefix of your static files (default: {}))'.format(
            'static'))
    parser.add_argument(
        'posts',
        type=str,
        nargs='*',
        help=
        'Individual files to deploy to Confluence (takes precendence over --git)'
    )

    args = parser.parse_args()

    if not args.api_url:
        log.error('Please provide a valid API URL')
        sys.exit(1)

    return parser.parse_args()


def deploy_file(post_path, args, confluence):
    """Creates or updates a file in Confluence

    Arguments:
        post_path {str} -- The absolute path of the post to deploy to Confluence
        args {argparse.Arguments} -- The parsed command-line arguments
        confluence {confluence.Confluence} -- The Confluence API client
    """

    _, ext = os.path.splitext(post_path)
    if ext not in SUPPORTED_FORMATS:
        log.info('Skipping {} since it\'s not a supported format.'.format(
            post_path))
        return

    try:
        front_matter, markdown = parse(post_path)
    except Exception as e:
        log.error(
            'Unable to process {}. Normally not a problem, but here\'s the error we received: {}'
            .format(post_path, e))
        return

    if 'wiki' not in front_matter or not front_matter['wiki'].get('share'):
        log.info(
            'Post {} not set to be uploaded to Confluence'.format(post_path))
        return

    front_matter['author_keys'] = []
    authors = front_matter.get('authors', [])
    for author in authors:
        confluence_author = confluence.get_author(author)
        if not confluence_author:
            continue
        front_matter['author_keys'].append(confluence_author['accountId'])

    if len(front_matter['author_keys']) == 0:
        front_matter['author_keys'].append(confluence.get_current_user())

    # Normalize the content into whatever format Confluence expects
    html, attachments = convtoconf(markdown, front_matter=front_matter)


    static_path = os.path.join(args.git, args.static_path)
    for i, attachment in enumerate(attachments):
        attachments[i] = os.path.join(static_path, attachment.lstrip('/'))

    slug_prefix = '{}{}'.format('s','_'.join(author.lower() for author in authors))
    post_slug = get_slug(post_path, prefix=slug_prefix)

    ancestor_id = front_matter['wiki'].get('ancestor_id', args.ancestor_id)
    space = front_matter['wiki'].get('space', args.space)

    tags = front_matter.get('tags', [])
    if args.global_label:
        tags.append(args.global_label)

    page = confluence.exists(slug=post_slug,
                             ancestor_id=ancestor_id,
                             space=space)

    if page:
        confluence.update(page['id'],
                          content=html,
                          title=front_matter['title'],
                          tags=tags,
                          slug=post_slug,
                          space=space,
                          ancestor_id=ancestor_id,
                          page=page,
                          attachments=attachments)
    else:
        confluence.create(content=html,
                            title=front_matter['title'],
                            tags=tags,
                            slug=post_slug,
                            space=space,
                            ancestor_id=ancestor_id,
                            attachments=attachments)


def main():
    args = parse_args()

    confluence = Confluence(api_url=args.api_url,
                            username=args.username,
                            password=args.password,
                            headers=args.headers,
                            dry_run=args.dry_run)

    if args.posts:
        changed_posts = [os.path.abspath(post) for post in args.posts]
        for post_path in changed_posts:
            if not os.path.exists(post_path) or not os.path.isfile(post_path):
                log.error('File doesn\'t exist: {}'.format(post_path))
                sys.exit(1)
    else:
        repo = git.Repo(args.git)
        changed_posts = [
            os.path.join(args.git, post) for post in get_last_modified(repo)
        ]
    if not changed_posts:
        log.info('No post created/modified in the latest commit')
        return

    for post in changed_posts:
        log.info('Attempting to deploy {}'.format(post))
        deploy_file(post, args, confluence)


if __name__ == '__main__':
    main()
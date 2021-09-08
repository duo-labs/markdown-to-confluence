#!/usr/bin/env python3
import argparse
from dataclasses import dataclass, field
import logging
import os
from typing import List, Optional, Tuple
from record import Article, ArticleState
import sys
import stat
import mistune

from confluence import Confluence
from convert import ConfluenceRenderer, parse
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
        'files',
        type=str,
        nargs='*',
        help=
        'List of directories and files to deploy to Confluence. The whole subtree of the listed directories are scanned for markdown (.md) files. (takes precendence over --git)'
    )

    args = parser.parse_args()

    if not args.api_url:
        log.error('Please provide a valid API URL')
        sys.exit(1)

    return parser.parse_args()


@dataclass
class ArticleToSync:

    article: Article
    front_matter: dict
    markdown: str
    author_keys: List[str] = field(default_factory=list)

    @property
    def wiki_config(self) -> dict:
        return (self.front_matter or {}).get('wiki', {})

    @property
    def to_share(self) -> bool:
        return self.wiki_config.get('share', False)

    @property
    def authors(self) -> List[str]:
        return (self.front_matter or {}).get('authors', [])

    @property
    def self_placement(self) -> Tuple[Optional[str], Optional[str]]:
        return self.wiki_config.get('space'), self.wiki_config.get('ancestor_id')

class MarkdownToConfluence:

    def __init__(self, confluence: Confluence, articles: List[Article], ancestor_id: str, space: str, global_label: Optional[str]) -> None:
        self.confluence = confluence
        self.articles = articles
        self.ancestor_id = ancestor_id
        self.space = space
        self.global_label = global_label

    def _get_placement(self, article_to_sync: ArticleToSync) -> Tuple[str, str]:
        space, ancestor_id = article_to_sync.self_placement
        if space is not None and ancestor_id is not None:
            return space, ancestor_id

        parent_relative_path = article_to_sync.article.parent
        if not parent_relative_path:
            return space or self.space, ancestor_id or self.ancestor_id

        parent = [ article for article in self.articles if article.relative_path == parent_relative_path ]
        if parent:
            parent = parent[0]

        if not parent:
            parent = Article(
                absolute_path=os.path.dirname(article_to_sync.article.absolute_path),
                relative_path=parent_relative_path,
                is_directory=True,
            )
            self.articles.append(parent)
        
        self._sync_article(parent)

        # TODO check parent state

        return space or parent.space, ancestor_id or parent.confluence_id

    def sync(self, ):
        for article in self.articles:
            log.info('Attempting to sync {}'.format(article))
            self._sync_article(article)

    def _parse(self, article: Article) -> ArticleToSync:
        front_matter, markdown = parse(article.content_path)
        articleToSync = ArticleToSync(
            article=article,
            front_matter=front_matter,
            markdown=markdown
        )
        self._set_author_keys(articleToSync)
        return articleToSync


    def _set_author_keys(self, articleToSync: ArticleToSync):
        author_keys = []
        authors = articleToSync.front_matter.get('authors', [])
        for author in authors:
            confluence_author = self.confluence.get_author(author)
            if not confluence_author:
                continue
            author_keys.append(confluence_author['userKey'])
        articleToSync.author_keys = author_keys

    
    def _convert_to_confluence(self, articleToSync: ArticleToSync):
        renderer = ConfluenceRenderer(authors=articleToSync.author_keys, article=articleToSync.article)
        content_html = mistune.markdown(articleToSync.markdown, renderer=renderer)
        page_html = renderer.layout(content_html)

        return page_html, renderer.attachments

    def _ensure_exists(self, article_to_sync: ArticleToSync):
        space, ancestor_id = self._get_placement(article_to_sync)

        if space is None or ancestor_id is None:
            raise Exception('Could not find placement for article: {} Space: {} Anchestor Id: {}'.format(article_to_sync.article, space, ancestor_id))

        page = self.confluence.exists(
            id_label=article_to_sync.article.id_label,
            ancestor_id=ancestor_id,
            space=space
        )

        if not page:
            log.info('{} Page does not exist, creating...'.format(article_to_sync.article))
            page = self.confluence.create(
                id_label=article_to_sync.article.id_label,
                space=space,
                title=article_to_sync.article.name or 'Title missing',
                ancestor_id=ancestor_id,
            )
        else:
            log.info('{} Page exists'.format(article_to_sync))
            
        # TODO error handling. set SKIPPED
        article_to_sync.article.ancestor_id = ancestor_id
        article_to_sync.article.space = space
        article_to_sync.article.confluence_id = page['id']
        article_to_sync.article.page_version = page['version']['number']
        article_to_sync.article.state = ArticleState.CREATED

        return page

    def _sync_article(self, article: Article):
        log.info('Attempting to sync {}'.format(article))
        if article.content_path and article.state in [ ArticleState.TO_BE_SYNCED, ArticleState.CREATED ]:
            try:
                articleToSync: ArticleToSync = self._parse(article)
            except Exception as e:
                log.exception(
                    'Unable to process {}. Normally not a problem, but here\'s the error we received: {}'
                    .format(article, e))
                article.state = ArticleState.SKIPPED
                return

            if not articleToSync.to_share:
                log.info(
                    'Article {} not set to be uploaded to Confluence'.format(article))
                article.state = ArticleState.SKIPPED
                return

            if article.state == ArticleState.TO_BE_SYNCED:
                self._ensure_exists(articleToSync)

            if article.state == ArticleState.CREATED:
                # Normalize the content into whatever format Confluence expects
                html, attachments = self._convert_to_confluence(articleToSync)

                tags = articleToSync.front_matter.get('tags', [])
                if self.global_label:
                    tags.append(self.global_label)

                log.info('Page exists, updating...')
                self.confluence.update(
                    article.confluence_id,
                    content=html,
                    # TODO fixme
                    title=articleToSync.front_matter['title'],
                    tags=tags,
                    id_label=article.id_label,
                    space=article.space,
                    ancestor_id=article.ancestor_id,
                    page_version=article.page_version,
                    attachments=attachments,
                )

                article.state = ArticleState.SYNCED
        elif not article.content_path and article.is_directory and article.state in [ ArticleState.TO_BE_SYNCED ]:
            articleToSync = ArticleToSync(
                article=article,
                front_matter={},
                markdown="",
            )
            self._ensure_exists(articleToSync)
            # article.state = ArticleState.SYNCED

        log.info('Finished syncing {}. State: {}'.format(article, article.state))

def is_hidden(filepath):
    name = os.path.basename(os.path.abspath(filepath))
    return name.startswith('.') or has_hidden_attribute(filepath)

def has_hidden_attribute(filepath):
    return bool(os.stat(filepath).st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)

def main():
    args = parse_args()

    confluence = Confluence(api_url=args.api_url,
                            username=args.username,
                            password=args.password,
                            headers=args.headers,
                            dry_run=args.dry_run)
                            
    articles: List[Article] = []
    if args.files:
        files = [os.path.abspath(post) for post in args.files]
        for file_path in files:
            if os.path.exists(file_path):
                if os.path.isdir(file_path):
                    for root, dirs, files in os.walk(file_path):
                        files = [f for f in files if not f[0] == '.']
                        dirs[:] = [d for d in dirs if not d[0] == '.']
                        for f in files:
                            absolute_path = os.path.join(root, f)
                            if f == 'README.md':
                                dir_path = os.path.dirname(absolute_path)
                                articles.append(Article(
                                    absolute_path=dir_path,
                                    relative_path=os.path.relpath(dir_path, start=file_path),
                                    content_path=absolute_path,
                                    is_directory=True,
                                ))
                            else:
                                articles.append(Article(
                                    absolute_path=absolute_path,
                                    relative_path=os.path.relpath(absolute_path, start=file_path),
                                    content_path=absolute_path,
                                    is_directory=False
                                ))
                elif os.path.isfile(file_path):
                    absolute_path=os.path.abspath(file_path)
                    articles.append(Article(
                        absolute_path=absolute_path,
                        relative_path=file_path,
                        content_path=absolute_path,
                    ))
                else:
                    log.info('Skipped: {}'.format(file_path))
            else:
                log.info('File doesn\'t exist: {}'.format(file_path))

        articles = [ article for article in articles if article.is_markdown or article.is_directory ]
        log.debug('Articles to sync: {}'.format(articles))
    # else:
    #     repo = git.Repo(args.git)
    #     files_to_upload = [
    #         os.path.join(args.git, file_to_upload) for file_to_upload in get_last_modified(repo)
    #     ]
    if not articles:
        log.info('Could not find any article to upload or update')
        return

    MarkdownToConfluence(
        confluence=confluence,
        articles=articles,
        ancestor_id=args.ancestor_id,
        space=args.space,
        global_label=args.global_label,
    ).sync()



if __name__ == '__main__':
    main()

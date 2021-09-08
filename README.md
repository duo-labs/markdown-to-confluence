# markdown-to-confluence

Converts and deploys a Markdown file to Confluence.

This repository is a fork of [duo-labs/markdown-to-confluence](https://github.com/duo-labs/markdown-to-confluence). It was created to sync [Journal](https://duo-labs.github.io/journal/) posts to Confluence as part of the CI process. However, it's able to more generally handle Markdown files that have front-matter at the top, such as those used in Hugo, Jeykll, etc.

# Installation

To install the project, you need to first install the dependencies:

```
pip install -r requirements.txt
```

Alternatively, you can use the provided Dockerfile:

```
docker build -t markdown-to-confluence .
```

# Usage

```
usage: markdown-to-confluence.py [-h] [--git GIT] [--api_url API_URL]
                                 [--username USERNAME] [--password PASSWORD]
                                 [--space SPACE] [--ancestor_id ANCESTOR_ID]
                                 [--global_label GLOBAL_LABEL]
                                 [--header HEADER] [--dry-run]
                                 [files|directories ...]

Converts and deploys a markdown post to Confluence

positional arguments:
  files|directories     List of directories and files to deploy to Confluence.
                        The whole subtree of the listed directories are
                        scanned for markdown (.md) files. (takes precendence
                        over --git)

optional arguments:
  -h, --help            show this help message and exit
  --api_url API_URL     The URL to the Confluence API (e.g.
                        https://wiki.example.com/rest/api/)
  --username USERNAME   The username for authentication to Confluence
                        (default: env('CONFLUENCE_USERNAME'))
  --password PASSWORD   The password for authentication to Confluence
                        (default: env('CONFLUENCE_PASSWORD'))
  --space SPACE         The Confluence space where the post should reside
                        (default: env('CONFLUENCE_SPACE'))
  --ancestor_id ANCESTOR_ID
                        The Confluence ID of the parent page to place posts
                        under (default: env('CONFLUENCE_ANCESTOR_ID'))
  --global_label GLOBAL_LABEL
                        The label to apply to every post for easier discovery
                        in Confluence (default:
                        env('CONFLUENCE_GLOBAL_LABEL'))
  --header HEADER       Extra header to include in the request when sending
                        HTTP to a server. May be specified multiple times.
                        (default: env('CONFLUENCE_HEADER_<NAME>'))
  --dry-run             Print requests that would be sent- don't actually make
                        requests against Confluence (note: we return empty
                        responses, so this might impact accuracy)
```

## What Posts are Deployed

This project assumes that the Markdown files being processed have YAML formatted front-matter at the top. In order for a file to be processed, we expect the following front-matter to be present:

```yaml
wiki:
    share: true
```

## Deploying a Post

There are two ways to deploy a post:

## Using with Docker

```bash
docker run --read-only -v <directory containing the markdowns>:/data barnabassudy/markdown-to-confluence:v0.1 --api_url <confluence base url> --username <confluence username> --password <confluence api token> --space <confluence space> --ancestor_id <parent page> /data
```

### Deploying Posts On-Demand

You may wish to deploy a post on-demand, rather than building this process into your CI/CD pipeline. To do this, just put the filenames of the posts you wish to deploy to Confluence as arguments:

```
markdown-to-confluence.py /path/to/your/post.md
```
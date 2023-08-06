---
title: 'Documentation Guidelines'
date: 2022-05-19
authors: [{username: 'Aitzaz Ahmad'}]
description: 'Documentation guidelines for content writers'
wiki:
    share: false
    ancestor_id: to_be_added
---

## Creating informational alerts for Confluence pages

The standard Markdown syntax doesn't provide built-in support for creating informational alerts. Confluence, however, provides the following varieties:

 - info
 - tip
 - note
 - warning


 In order bridge this gap and empower our writers we've come up with the following macro definitions that can be used in Markdown documents:


```xml
<!-- the info macro -->
~: An important piece of information. :~

<!-- the tip macro -->
~% Here's a useful tip! %~

<!-- the note macro -->
~? Take a note of this. ?~

<!-- the warning macro -->
~! Be warned!! !~
```

The macros above will render in Confluence as below:

~: An important piece of information. :~

~% Here's a useful tip! %~

~? Take note of this. ?~

~! Be warned!! !~


**Important:** You will only see the macro definitions above rendered correctly once a Markdown file has been published on Confluence. _None of the aforementioned macros would render as Confluence tooltips when viewed in GitHub._

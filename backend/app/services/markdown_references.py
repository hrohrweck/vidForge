"""Markdown reference parser for media-asset: URLs"""

import re
from uuid import UUID

MEDIA_ASSET_PATTERN = re.compile(r'!\[([^\]]*)\]\(media-asset:([a-fA-F0-9-]+)\)')
LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(media-asset:([a-fA-F0-9-]+)\)')


def extract_media_asset_references(markdown_text: str) -> set[UUID]:
    """Extract all media-asset UUID references from markdown text.

    Returns a set of UUIDs referenced in the markdown.
    """
    references = set()

    # Find image references: ![alt](media-asset:uuid)
    for match in MEDIA_ASSET_PATTERN.finditer(markdown_text):
        try:
            asset_id = UUID(match.group(2))
            references.add(asset_id)
        except ValueError:
            continue

    # Find link references: [text](media-asset:uuid)
    for match in LINK_PATTERN.finditer(markdown_text):
        try:
            asset_id = UUID(match.group(2))
            references.add(asset_id)
        except ValueError:
            continue

    return references


def replace_media_asset_urls(markdown_text: str, url_resolver: callable) -> str:
    """Replace media-asset: URLs with resolved URLs.

    Args:
        markdown_text: The markdown text containing media-asset: URLs
        url_resolver: A function that takes a UUID and returns the resolved URL string

    Returns:
        Markdown text with resolved URLs
    """
    def replace_image(match: re.Match) -> str:
        alt_text = match.group(1)
        asset_id = match.group(2)
        try:
            resolved_url = url_resolver(UUID(asset_id))
            return f'![{alt_text}]({resolved_url})'
        except (ValueError, Exception):
            return match.group(0)  # Keep original if resolution fails

    def replace_link(match: re.Match) -> str:
        link_text = match.group(1)
        asset_id = match.group(2)
        try:
            resolved_url = url_resolver(UUID(asset_id))
            return f'[{link_text}]({resolved_url})'
        except (ValueError, Exception):
            return match.group(0)  # Keep original if resolution fails

    text = MEDIA_ASSET_PATTERN.sub(replace_image, markdown_text)
    text = LINK_PATTERN.sub(replace_link, text)
    return text


def has_media_asset_references(markdown_text: str) -> bool:
    """Check if markdown text contains any media-asset references."""
    return bool(MEDIA_ASSET_PATTERN.search(markdown_text) or LINK_PATTERN.search(markdown_text))

# coding=utf-8

import re


# JavTrailers mirrors the DMM sample streams, which are geo-blocked outside Japan, as HLS playlists that play from anywhere.
MIRROR_URL = u"https://media.javtrailers.com/hlsvideo/freepv/{0}/{1}/{2}/playlist.m3u8"

# Pulls the content id out of a DMM sample movie filename, e.g. "1sun00045a" from ".../1sun00045ahhb.mp4" or "ebod00889" from
# ".../ebod00889_mhb_w.mp4".
SAMPLE_FILE_RE = re.compile(r"^https?://cc3001\.dmm\.co\.jp/.*/([a-z0-9_]+?)_?(?:sm|dm|dmb|mmb|mhb|hmb|hhb|hhbs|4k)(?:_w)?\.mp4$")


def mirror_url(sample_url):
    """Return the JavTrailers playlist url of a DMM sample movie.

    Args:
        sample_url: A DMM sample movie url (str), or None.

    Returns:
        str: The mirrored HLS playlist url, or None when the url is not a DMM sample movie.
    """
    if not sample_url:
        return None
    match = SAMPLE_FILE_RE.match(sample_url)
    if not match:
        return None
    cid = match.group(1)
    return MIRROR_URL.format(cid[:1], cid[:3], cid)

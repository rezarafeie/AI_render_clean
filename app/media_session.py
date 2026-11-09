"""Browser media authentication is read-only and limited to existing Studio files."""
import re

COOKIE = 'editorgpt_media'

def allowed(method: str, path: str) -> bool:
    routes = (
        r'/studio/(?:projects/[^/]+/output|projects/[^/]+/job-files/(?!.*\.\.)[\w./-]+|conversations/[^/]+/attachments/[^/]+|motion/[^/]+/video|discovery/[^/]+/candidates/[^/]+/preview)',
        r'/jobs/[^/]+/(?:raw|exports/[^/]+|talking-reel/output|motion-scenes/[^/]+/video)',
        r'/localize/[^/]+/output',
        r'/library/[^/]+/[^/]+/preview',
    )
    return method in {'GET', 'HEAD'} and any(re.fullmatch(pattern, path) for pattern in routes)

import hashlib
import json
from pathlib import Path
import re
import threading

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

_VERIFIED_DESIGN_SYSTEM = None
_DESIGN_SYSTEM_LOCK = threading.Lock()


def verified_design_system_graph_sha():
    """Verify one immutable collected asset generation per manifest inode/mtime.

    Publish CSS, module, then manifest atomically and restart workers after
    collectstatic so a live process never spans two asset generations.
    """
    global _VERIFIED_DESIGN_SYSTEM
    static_source = settings.BASE_DIR / 'static' / 'littlehands'
    manifest_path = static_source / 'design-system.manifest.json'
    manifest_stat = manifest_path.stat()
    generation = (str(manifest_path), manifest_stat.st_dev, manifest_stat.st_ino,
                  manifest_stat.st_mtime_ns, manifest_stat.st_size,
                  id(staticfiles_storage._wrapped), type(staticfiles_storage).__module__,
                  type(staticfiles_storage).__qualname__, str(settings.STATIC_ROOT))
    with _DESIGN_SYSTEM_LOCK:
        cached = _VERIFIED_DESIGN_SYSTEM
    if cached and cached[0] == generation:
        return cached[1]
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    graph_sha = manifest.get('graphSha256')
    if not isinstance(graph_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', graph_sha):
        raise RuntimeError('Design-system manifest has no valid graph SHA-256')
    expected = {
        'littlehands/design-system.css': manifest.get('cssSha256'),
        'littlehands/design-system.js': manifest.get('moduleSha256'),
    }
    for logical_name, expected_sha in expected.items():
        if not isinstance(expected_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha):
            raise RuntimeError('Design-system manifest has an invalid asset SHA-256')
        source_path = settings.BASE_DIR / 'static' / logical_name
        source_bytes = source_path.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != expected_sha:
            raise RuntimeError(f'Design-system source asset does not match manifest: {logical_name}')
        stored_name = getattr(staticfiles_storage, 'stored_name', None)
        if callable(stored_name):
            deployed_name = stored_name(logical_name)
            deployed_path = Path(settings.STATIC_ROOT) / deployed_name
            if not deployed_path.is_file() or hashlib.sha256(deployed_path.read_bytes()).hexdigest() != expected_sha:
                raise RuntimeError(f'Collected static asset does not match design-system manifest: {logical_name}')
        elif settings.ENVIRONMENT == 'production':
            raise RuntimeError('Production requires manifest-backed collected design-system assets')
    module = (settings.BASE_DIR / 'static' / 'littlehands' / 'design-system.js').read_text(encoding='utf-8')
    if f'export const graphSha256 = "{graph_sha}";' not in module:
        raise RuntimeError('Design-system module graph SHA-256 does not match manifest')
    css = (settings.BASE_DIR / 'static' / 'littlehands' / 'design-system.css').read_text(encoding='utf-8')
    if f'/* graph-sha256: {graph_sha} */' not in css:
        raise RuntimeError('Design-system CSS graph SHA-256 does not match manifest')
    with _DESIGN_SYSTEM_LOCK:
        _VERIFIED_DESIGN_SYSTEM = (generation, graph_sha)
    return graph_sha


def service_context(request):
    unread = 0
    if request.user.is_authenticated:
        from booking.models import Notification
        unread = Notification.objects.filter(member=request.user, read_at__isnull=True).count()
    return {'service_name':'작은손 커피공방', 'service_environment':settings.ENVIRONMENT,
            'service_staging':settings.ENVIRONMENT != 'production', 'notifications_unread':unread,
            'design_system_graph_sha':verified_design_system_graph_sha()}

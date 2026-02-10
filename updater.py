"""Check GitHub Releases for app updates."""
import logging
import requests
import config

log = logging.getLogger(__name__)


def check_for_update():
    """Check if a newer version is available on GitHub Releases.

    Returns (latest_version, download_url) if an update exists, or None.
    Silently returns None on any error (no internet, API down, etc.).
    """
    try:
        url = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None

        data = resp.json()
        latest = data.get("tag_name", "").lstrip("vV")
        if not latest:
            return None

        if _is_newer(latest, config.APP_VERSION):
            download_url = data.get("html_url", "")
            return latest, download_url

    except Exception:
        log.debug("Update check failed", exc_info=True)

    return None


def _is_newer(remote, local):
    """Compare semver strings. Returns True if remote > local."""
    try:
        remote_parts = [int(x) for x in remote.split(".")]
        local_parts = [int(x) for x in local.split(".")]
        return remote_parts > local_parts
    except (ValueError, AttributeError):
        return False

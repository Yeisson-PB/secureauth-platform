import re


def parse_user_agent(user_agent: str | None) -> dict[str, str | None]:
    """
    Parse a raw User-Agent header into (browser, os, device_type, device_name).

    Returns a dict with all four keys set (device_type defaults to
    "unknown" rather than None so it's always a queryable/filterable
    value in the DB).
    """
    if not user_agent:
        return {
            "browser": None,
            "os": None,
            "device_type": "unknown",
            "device_name": None,
        }

    ua = user_agent

    # --- Device type ------------------------------
    if re.search(r"iPad|Tablet", ua, re.I):
        device_type = "tablet"
    elif re.search(r"Mobi|Android(?!.*Tablet)|iPhone", ua, re.I):
        device_type = "mobile"
    else:
        device_type = "desktop"

    # --- Operating system ------------------------------
    os_patterns = [
        (r"Windows NT 10\.0", "Windows 10/11"),
        (r"Windows NT", "Windows"),
        (r"iPhone OS|CPU OS", "iOS"),
        (r"Mac OS X", "macOS"),
        (r"Android", "Android"),
        (r"Linux", "Linux"),
    ]
    os_name = next(
        (label for pattern, label in os_patterns if re.search(pattern, ua)), None
    )

    # --- Browser ------------------------------
    # Order matters: Edge/Opera/Chrome-iOS all contain "Safari" or "Chrome"
    # in their UA strings too, so the more specific tokens must be checked
    # first
    browser_patterns = [
        (r"Edg/", "Edge"),
        (r"OPR/|Opera", "Opera"),
        (r"CriOS/", "Chrome (iOS)"),
        (r"Chrome/", "Chrome"),
        (r"Firefox/", "Firefox"),
        (r"Version/.*Safari", "Safari"),
    ]
    browser = next(
        (label for pattern, label in browser_patterns if re.search(pattern, ua)),
        "Unknown",
    )

    device_name = f"{browser} on {os_name}" if os_name else browser

    return {
        "browser": browser,
        "os": os_name,
        "device_type": device_type,
        "device_name": device_name,
    }

import json
import urllib.error
import urllib.request


DEFAULT_COMPARE_ENDPOINTS = [
    "/api/moods/all",
    "/api/journal/entries/all",
    "/api/stats/overview",
    "/api/server/values/all",
]


def normalize_base_url(url):
    return url.rstrip("/")


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        return None, str(exc)
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def canonicalize_value(value):
    if isinstance(value, dict):
        return {k: canonicalize_value(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return sorted((canonicalize_value(item) for item in value), key=repr)
    return value


def compare_rows(baseline_rows, target_rows):
    def serialize_row(row):
        return json.dumps(canonicalize_value(row), sort_keys=True, separators=(",", ":"))

    baseline_counts = {}
    for row in baseline_rows:
        key = serialize_row(row)
        baseline_counts[key] = baseline_counts.get(key, 0) + 1

    target_counts = {}
    for row in target_rows:
        key = serialize_row(row)
        target_counts[key] = target_counts.get(key, 0) + 1

    missing = []
    extra = []
    for key, count in baseline_counts.items():
        diff = count - target_counts.get(key, 0)
        if diff > 0:
            missing.append((key, diff))
    for key, count in target_counts.items():
        diff = count - baseline_counts.get(key, 0)
        if diff > 0:
            extra.append((key, diff))

    return missing, extra


def compare_payloads(baseline_payload, target_payload):
    if (
        isinstance(baseline_payload, dict)
        and isinstance(target_payload, dict)
        and "rows" in baseline_payload
        and "rows" in target_payload
        and isinstance(baseline_payload["rows"], list)
        and isinstance(target_payload["rows"], list)
    ):
        missing, extra = compare_rows(baseline_payload["rows"], target_payload["rows"])
        return not missing and not extra, {"missing": missing, "extra": extra}

    baseline_value = canonicalize_value(baseline_payload)
    target_value = canonicalize_value(target_payload)
    equal = baseline_value == target_value
    detail = None if equal else {"baseline": baseline_value, "target": target_value}
    return equal, detail


def compare_endpoints(baseline_url, target_url, endpoints):
    baseline_url = normalize_base_url(baseline_url)
    target_url = normalize_base_url(target_url)
    results = []
    all_ok = True

    for endpoint in endpoints:
        endpoint = endpoint.strip()
        if not endpoint:
            continue
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        base_payload, base_err = fetch_json(f"{baseline_url}{endpoint}")
        target_payload, target_err = fetch_json(f"{target_url}{endpoint}")

        if base_err or target_err:
            all_ok = False
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "error",
                    "baseline_error": base_err,
                    "target_error": target_err,
                }
            )
            continue

        ok, detail = compare_payloads(base_payload, target_payload)
        if ok:
            results.append({"endpoint": endpoint, "status": "match"})
            continue

        all_ok = False
        if isinstance(detail, dict) and "missing" in detail:
            missing = detail["missing"]
            extra = detail["extra"]
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "mismatch",
                    "missing": missing,
                    "extra": extra,
                    "missing_count": len(missing),
                    "extra_count": len(extra),
                }
            )
        else:
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "mismatch",
                    "detail": detail,
                }
            )

    return all_ok, results

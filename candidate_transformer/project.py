from .normalize import normalize_phone


MISSING = object()


def _resolve_path(value, path: str):
    if path.endswith("[].name"):
        base = path[:-7]
        items = _resolve_path(value, base)
        if items is MISSING or items is None:
            return MISSING
        return [item.get("name") for item in items if isinstance(item, dict) and item.get("name")]

    parts = path.replace("[", ".[").split(".")
    current = value
    for part in parts:
        if part == "":
            continue
        if part.startswith("[") and part.endswith("]"):
            if not isinstance(current, list):
                return MISSING
            index_text = part[1:-1]
            try:
                current = current[int(index_text)]
            except (ValueError, IndexError):
                return MISSING
        else:
            if not isinstance(current, dict) or part not in current:
                return MISSING
            current = current[part]
    return current


def _coerce(value, expected_type: str):
    if value is None:
        return None
    if expected_type == "string":
        return value if isinstance(value, str) else str(value)
    if expected_type == "string[]":
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]
    if expected_type == "number":
        return value if isinstance(value, (int, float)) else float(value)
    if expected_type == "object":
        if isinstance(value, dict):
            return value
        raise ValueError(f"Expected object, got {type(value).__name__}")
    return value


def project_output(profile: dict, config: dict) -> dict:
    output = {}
    on_missing = config.get("on_missing", "null")

    for field in config.get("fields", []):
        output_path = field["path"]
        source_path = field.get("from", output_path)
        value = _resolve_path(profile, source_path)

        if value is MISSING:
            if field.get("required") or on_missing == "error":
                raise ValueError(f"Missing required field: {source_path}")
            if on_missing == "omit":
                continue
            value = None

        if field.get("normalize", "").lower() == "e164" and value is not None:
            value = normalize_phone(value)

        output[output_path] = _coerce(value, field.get("type", "any"))

    if config.get("include_confidence", False):
        output["overall_confidence"] = profile.get("overall_confidence")
    if config.get("include_provenance", False):
        output["provenance"] = profile.get("provenance", [])
    return output

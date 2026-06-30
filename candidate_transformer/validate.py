DEFAULT_REQUIRED_KEYS = {
    "candidate_id",
    "full_name",
    "emails",
    "phones",
    "location",
    "links",
    "headline",
    "years_experience",
    "skills",
    "experience",
    "education",
    "provenance",
    "overall_confidence",
    "warnings",
}


def validate_profile(profile: dict) -> None:
    missing = DEFAULT_REQUIRED_KEYS - set(profile)
    if missing:
        raise ValueError(f"Canonical profile missing keys: {sorted(missing)}")
    if not isinstance(profile["emails"], list):
        raise ValueError("emails must be a list")
    if not isinstance(profile["phones"], list):
        raise ValueError("phones must be a list")
    if not isinstance(profile["skills"], list):
        raise ValueError("skills must be a list")
    if not isinstance(profile["provenance"], list):
        raise ValueError("provenance must be a list")
    if not isinstance(profile["overall_confidence"], (int, float)):
        raise ValueError("overall_confidence must be numeric")
    if not isinstance(profile["warnings"], list):
        raise ValueError("warnings must be a list")


def validate_projection(output: dict, config: dict) -> None:
    for field in config.get("fields", []):
        path = field["path"]
        if field.get("required") and path not in output:
            raise ValueError(f"Projected output missing required field: {path}")
        if path not in output or output[path] is None:
            continue
        expected = field.get("type")
        value = output[path]
        if expected == "string" and not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
        if expected == "string[]" and not (
            isinstance(value, list) and all(isinstance(item, str) for item in value)
        ):
            raise ValueError(f"{path} must be a string[]")
        if expected == "number" and not isinstance(value, (int, float)):
            raise ValueError(f"{path} must be a number")

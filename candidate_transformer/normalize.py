import re


SKILL_ALIASES = {
    "py": "Python",
    "python": "Python",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "react": "React",
    "react.js": "React",
    "sql": "SQL",
    "pyspark": "PySpark",
    "spark": "Apache Spark",
    "aws": "AWS",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "data pipelines": "Data Pipelines",
    "etl": "ETL",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "typescript": "TypeScript",
    "java": "Java",
}

COUNTRY_ALIASES = {
    "india": "IN",
    "in": "IN",
    "usa": "US",
    "united states": "US",
    "us": "US",
}


def clean_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None


def normalize_email(value: object) -> str | None:
    cleaned = clean_string(value)
    if not cleaned or "@" not in cleaned:
        return None
    return cleaned.lower()


def normalize_phone(value: object, default_country_code: str = "+91") -> str | None:
    cleaned = clean_string(value)
    if not cleaned:
        return None
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return None
    if cleaned.strip().startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    if len(digits) == 10:
        return f"{default_country_code}{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if 8 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def canonical_skill(value: object) -> str:
    cleaned = clean_string(value) or ""
    lowered = cleaned.lower()
    return SKILL_ALIASES.get(lowered, cleaned.title())


CITY_MAP = {
    "bengaluru": ("Bengaluru", "KA"),
    "bangalore": ("Bengaluru", "KA"),
    "mumbai": ("Mumbai", "MH"),
    "bombay": ("Mumbai", "MH"),
    "delhi": ("Delhi", "DL"),
    "new delhi": ("Delhi", "DL"),
    "hyderabad": ("Hyderabad", "TS"),
    "chennai": ("Chennai", "TN"),
    "madras": ("Chennai", "TN"),
    "pune": ("Pune", "MH"),
    "kolkata": ("Kolkata", "WB"),
    "calcutta": ("Kolkata", "WB"),
    "ahmedabad": ("Ahmedabad", "GJ"),
    "noida": ("Noida", "UP"),
    "gurugram": ("Gurugram", "HR"),
    "gurgaon": ("Gurugram", "HR"),
}

def normalize_location(value: object) -> dict:
    text = (clean_string(value) or "").lower()
    city = None
    region = None
    country = None

    # detect city + region from known map
    for keyword, (city_name, region_code) in CITY_MAP.items():
        if keyword in text:
            city = city_name
            region = region_code
            break

    # detect country
    for alias, code in COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            country = code
            break

    # if city found in India and no country → default IN
    if city and country is None and region in {
        "KA","MH","DL","TS","TN","WB","GJ","UP","HR"
    }:
        country = "IN"

    return {"city": city, "region": region, "country": country}
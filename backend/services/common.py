def clean_string(value, fallback=""):
    if value is None:
        return fallback
    if isinstance(value, list):
        joined = ", ".join(clean_string(item, "") for item in value)
        return joined if joined.strip() else fallback
    text = str(value)
    return text if text.strip() else fallback


def model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()

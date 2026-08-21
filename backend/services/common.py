import re

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


_BLANK_VALUES = ("", "unknown", "n/a", "none", "null")


def is_blank(value) -> bool:
    """True for empty values and for the placeholders agents write when a probe fails."""
    return clean_string(value, "").strip().lower() in _BLANK_VALUES


_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def execution_day(raw) -> str | None:
    """
    An audit's `execution_datetime` as a `YYYY-MM-DD` day, or None when it
    cannot be read.

    Nearly every row is `2026-07-27 16:16:19`, plain to slice — but the column
    is text, not a real timestamp, and one older agent format instead writes
    `27-Jul-2026_18:02:00`. A bare slice reads that row's day as garbage
    (`27-Jul-202`) rather than the 27th it means, so both shapes are matched
    explicitly instead of assuming every row looks like the common case.
    """
    value = clean_string(raw, "").strip()
    if not value:
        return None

    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
    if iso:
        return iso.group(0)

    spelled = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})", value)
    if spelled:
        day, month_name, year = spelled.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return f"{year}-{month}-{day.zfill(2)}"

    return None


def is_identifiable_audit(row) -> bool:
    """
    False for an audit carrying no identifying information whatsoever.

    Probe/test posts reach the ingest endpoint with an effectively empty body and
    land as a row with no name, OS, serial or MAC. Nothing can be done with such
    a record and it surfaces in the inventory as a phantom "Unknown" device, so
    the listing endpoints skip it. Anything with even one identifier is kept.
    """
    return not all(
        is_blank(row.get(key))
        for key in ("computer_name", "os_name", "serial_number", "mac_address")
    )


# Storage-device model strings that agents have historically mis-reported as the
# machine model (see the $model clobber fixed in scripts/audit.ps1). Kept here so
# the device list and the device detail endpoints agree on what counts as junk,
# and so audits already in the database still render a sane model.
_DISK_MODEL_MARKERS = (
    'gb', 'tb', 'nvme', 'ssd', 'hdd', 'nand', 'sata', 'mzvl', 'kioxia',
    'kingston', 'om8pcp', 'om8', 'om3', 'samsung', 'wd', 'wdc', 'seagate',
    'toshiba', 'micron', 'crucial', 'sandisk', 'evmnv', 'pm9', 'pm98',
    'hynix', 'sk hynix', 'lexar', 'transcend', 'adata', 'sn5000', 'sn750',
    'sn850', 'cruzer', 'flash', 'usb device',
    '512', '256', '128', '1tb', '2tb', 'disk', 'drive', 'storage',
)


def is_disk_model(model) -> bool:
    """True when `model` looks like a disk/USB product name rather than a machine model."""
    text = clean_string(model, "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _DISK_MODEL_MARKERS)


def _trim_repeated_suffix(model: str) -> str:
    """
    Drop an OEM's redundant "_CODE" suffix when CODE already appears in the name.

    'ROG Zephyrus G14 GA403UV_GA403UV' -> 'ROG Zephyrus G14 GA403UV', while a
    suffix carrying new information ('Azalea_FMS') is left intact.
    """
    head, sep, tail = model.partition("_")
    if sep and tail and tail.strip().lower() in head.strip().lower():
        return head.strip()
    return model


def resolve_machine_model(model, mobo_product=None, computer_name=None) -> str:
    """
    Best available machine model.

    Prefers the reported model, falls back to the motherboard product (which is
    the real model on most OEM laptops, e.g. GA403UV) when the reported value is
    actually a storage device, and finally to the computer name.
    """
    candidate = clean_string(model, "").strip()
    if candidate and candidate.lower() not in ("unknown", "n/a") and not is_disk_model(candidate):
        return _trim_repeated_suffix(candidate)

    board = clean_string(mobo_product, "").strip()
    if board and board.lower() not in ("unknown", "n/a") and not is_disk_model(board):
        return board

    return clean_string(computer_name, "Unknown").strip() or "Unknown"

import os

mac_vendor_dict = {}
try:
    cache_path = os.path.expanduser("~/.cache/mac-vendors.txt")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(":", 1)
                if len(parts) == 2:
                    mac_vendor_dict[parts[0]] = parts[1]
except Exception:
    pass

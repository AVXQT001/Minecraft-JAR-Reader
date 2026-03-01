import os


def format_bytes(size: int) -> str:
    """Format bytes into MB/KB/GB."""
    power = 2**10
    n = 0
    size_f = float(size)
    power_labels = {0: "", 1: "K", 2: "M", 3: "G", 4: "T"}
    while size_f > power:
        size_f /= power
        n += 1
    return f"{size_f:.2f} {power_labels[n]}B"


def is_valid_jar(file_path: str) -> bool:
    """Check if file exists and ends with .jar or .zip."""
    return os.path.exists(file_path) and file_path.lower().endswith((".jar", ".zip"))

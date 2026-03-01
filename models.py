from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class JarData:
    """Represents a loaded Minecraft JAR file and its parsed metadata."""

    file_path: str
    file_name: str
    file_size_bytes: int

    # Technical Info
    total_files: int = 0
    java_version: Optional[str] = None
    mod_loader: str = "Unknown"  # Fabric, Forge, NeoForge, etc.
    is_minecraft_related: bool = False
    category: str = "Mods"  # Mods, Resourcepacks, Shaderpacks

    # Mod Info
    mod_id: str = "unknown"
    mod_name: str = "Unknown Mod"
    version: str = "Unknown Version"
    mc_version: str = "Unknown"
    is_mc_compatible: bool = True  # New field to flag incompatible mods
    description: str = "No description provided."
    url: str = ""
    update_url: str = ""
    authors: List[str] = field(default_factory=list)
    parsed_from: List[str] = field(
        default_factory=list
    )  # Files this info was built from
    dependencies: List[dict] = field(
        default_factory=list
    )  # List of {"id": str, "optional": bool}

    # Icon (as bytes, can be loaded into QPixmap later)
    icon_bytes: Optional[bytes] = None

    # Internal Files
    file_list: List[str] = field(default_factory=list)

    @property
    def file_size_mb(self) -> float:
        return self.file_size_bytes / (1024 * 1024)

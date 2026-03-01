import os
import zipfile
import json
import tomli
import struct
import shutil
from models import JarData
from utils import format_bytes, is_valid_jar

# Java class magic number
JAVA_MAGIC = 0xCAFEBABE


def get_mc_version_from_pack_format(pack_format: int) -> str:
    """Map Resource Pack format to Minecraft versions."""
    mapping = {
        1: "1.6.1 - 1.8.9",
        2: "1.9 - 1.10.2",
        3: "1.11 - 1.12.2",
        4: "1.13 - 1.14.4",
        5: "1.15 - 1.16.1",
        6: "1.16.2 - 1.16.5",
        7: "1.17 - 1.17.1",
        8: "1.18 - 1.18.1",
        9: "1.18.2",
        10: "1.19 - 1.19.2",
        11: "1.19.3",
        12: "1.19.4",
        13: "1.20 - 1.20.1",
        15: "1.20.2",
        18: "1.20.3 - 1.20.4",
        22: "1.20.5 - 1.20.6",
        32: "1.21 - 1.21.1",
        34: "1.21.2 - 1.21.3",
        42: "1.21.4",
    }
    return mapping.get(pack_format, f"Unknown (Format {pack_format})")


def get_java_version(major_version: int) -> str:
    """Map class major version to Java version."""
    # Java 1.1 is 45. Java 8 is 52. Java 17 is 61. Java 21 is 65.
    if major_version >= 45:
        return f"Java {major_version - 44}"
    return "Unknown Java Version"


def sniff_java_version(jar: zipfile.ZipFile, class_files: list[str]) -> str:
    """Read the first .class file to determine compiled Java version."""
    if not class_files:
        return "Unknown (No .class files)"

    try:
        # Just check the first class file we find
        first_class = class_files[0]
        with jar.open(first_class) as f:
            magic = struct.unpack(">I", f.read(4))[0]
            if magic == JAVA_MAGIC:
                minor = struct.unpack(">H", f.read(2))[0]
                major = struct.unpack(">H", f.read(2))[0]
                return get_java_version(major)
    except Exception as e:
        print(f"Error sniffing java version: {e}")

    return "Unknown"


def extract_fabric_meta(jar: zipfile.ZipFile, data: JarData):
    """Extract metadata from fabric.mod.json"""
    try:
        with jar.open("fabric.mod.json") as f:
            # Use strict=False to handle potential control characters in JSON strings (common in mod descriptions)
            content = f.read().decode("utf-8", errors="ignore")
            meta = json.loads(content, strict=False)
            data.parsed_from.append("fabric.mod.json")
            data.mod_loader = "Fabric"
            data.mod_id = meta.get("id", data.file_name)
            data.mod_name = meta.get("name", data.mod_id)
            data.version = meta.get("version", "Unknown")
            data.description = meta.get("description", "No description provided.")

            # Handle authors which can be a list of strings or dicts
            authors = meta.get("authors", [])
            data.authors = [
                a if isinstance(a, str) else a.get("name", "Unknown") for a in authors
            ]

            # Dependencies
            data.dependencies = []
            depends = meta.get("depends", {})
            if isinstance(depends, dict):
                for dep_id in depends:
                    data.dependencies.append({"id": dep_id, "optional": False})

            recommends = meta.get("recommends", {})
            if isinstance(recommends, dict):
                for dep_id in recommends:
                    data.dependencies.append({"id": dep_id, "optional": True})

            suggests = meta.get("suggests", {})
            if isinstance(suggests, dict):
                for dep_id in suggests:
                    data.dependencies.append({"id": dep_id, "optional": True})

            # Extract Minecraft version if possible
            if isinstance(depends, dict) and "minecraft" in depends:
                data.mc_version = depends["minecraft"]
                if isinstance(data.mc_version, list):
                    data.mc_version = ", ".join(data.mc_version)

            # Try to get icon
            icon_path = meta.get("icon")
            if icon_path:
                if isinstance(
                    icon_path, dict
                ):  # Sometimes icon is an object with resolutions
                    icon_path = list(icon_path.values())[-1]

                # Normalize path structure (remove leading slash)
                if icon_path.startswith("/"):
                    icon_path = icon_path[1:]

                if icon_path in jar.namelist():
                    with jar.open(icon_path) as icon_f:
                        data.icon_bytes = icon_f.read()
    except Exception as e:
        print(f"Failed parsing fabric metadata: {e}")


def extract_quilt_meta(jar: zipfile.ZipFile, data: JarData):
    """Extract metadata from quilt.mod.json"""
    try:
        with jar.open("quilt.mod.json") as f:
            meta = json.load(f)
            quilt_meta = meta.get("quilt_loader", {})
            mod_meta = quilt_meta.get("metadata", {})

            data.parsed_from.append("quilt.mod.json")
            data.mod_loader = "Quilt"
            data.mod_id = quilt_meta.get("id", data.file_name)
            data.mod_name = mod_meta.get("name", data.mod_id)
            data.version = quilt_meta.get("version", "Unknown")
            data.description = mod_meta.get("description", "No description provided.")

            # Contributors in quilt are a dict
            authors = mod_meta.get("contributors", {})
            data.authors = list(authors.keys()) if isinstance(authors, dict) else []

            # Dependencies
            data.dependencies = []
            depends = mod_meta.get("depends", [])
            for d in depends:
                if isinstance(d, dict) and "id" in d:
                    dep_id = d["id"]
                    data.dependencies.append({"id": dep_id, "optional": False})
                    # Use .get since potentially missing
                    if dep_id == "minecraft" and d.get("versions"):
                        data.mc_version = d["versions"]
                        if isinstance(data.mc_version, list):
                            data.mc_version = ", ".join(data.mc_version)
                elif isinstance(d, str):
                    data.dependencies.append({"id": d, "optional": False})

            recommends = mod_meta.get("recommends", [])
            for d in recommends:
                if isinstance(d, dict) and "id" in d:
                    data.dependencies.append({"id": d["id"], "optional": True})
                elif isinstance(d, str):
                    data.dependencies.append({"id": d, "optional": True})

            icon_path = mod_meta.get("icon")
            if icon_path:
                if isinstance(icon_path, dict):
                    icon_path = list(icon_path.values())[-1]
                if icon_path.startswith("/"):
                    icon_path = icon_path[1:]
                if icon_path in jar.namelist():
                    with jar.open(icon_path) as icon_f:
                        data.icon_bytes = icon_f.read()
    except Exception as e:
        print(f"Failed parsing quilt metadata: {e}")


def extract_forge_meta(
    jar: zipfile.ZipFile, data: JarData, toml_path: str, loader_name: str
):
    """Extract metadata from modern Forge/NeoForge mods.toml"""
    try:
        with jar.open(toml_path) as f:
            # Read and decode bytes to string for tomli
            content = f.read().decode("utf-8")
            meta = tomli.loads(content)

            data.parsed_from.append(toml_path)
            data.mod_loader = loader_name

            # Mods are an array in mods.toml
            mods = meta.get("mods", [{}])
            if mods:
                mod = mods[0]
                data.mod_id = mod.get("modId", data.file_name)
                data.mod_name = mod.get("displayName", data.mod_id)
                data.version = mod.get("version", "Unknown")
                data.description = mod.get("description", "No description provided.")
                data.authors = [mod.get("authors", "")]

            # Dependencies are usually in a separate [[dependencies.modId]] array in TOML
            data.dependencies = []
            deps = meta.get("dependencies", {})

            # Forge/NeoForge TOML "dependencies" is usually a dict where keys are modIds and values are lists of dependencies
            if isinstance(deps, dict):
                for dep_target, dep_list in deps.items():
                    if isinstance(dep_list, list):
                        for d in dep_list:
                            if "modId" in d:
                                dep_id = d["modId"]
                                is_mandatory = d.get("mandatory", True)

                                if dep_id not in ("forge", "minecraft", "neoforge"):
                                    data.dependencies.append(
                                        {"id": dep_id, "optional": not is_mandatory}
                                    )

                                if dep_id == "minecraft" and "versionRange" in d:
                                    data.mc_version = d["versionRange"]
            elif isinstance(deps, list):
                # Sometimes it's a flat list of dependency tables
                for d in deps:
                    if isinstance(d, dict) and "modId" in d:
                        dep_id = d["modId"]
                        is_mandatory = d.get("mandatory", True)

                        if dep_id not in ("forge", "minecraft", "neoforge"):
                            data.dependencies.append(
                                {"id": dep_id, "optional": not is_mandatory}
                            )

                        if dep_id == "minecraft" and "versionRange" in d:
                            data.mc_version = d["versionRange"]

            logo_file = mod.get("logoFile")
            if logo_file:
                if logo_file.startswith("/"):
                    logo_file = logo_file[1:]
                if logo_file in jar.namelist():
                    with jar.open(logo_file) as icon_f:
                        data.icon_bytes = icon_f.read()
    except Exception as e:
        print(f"Failed parsing {loader_name} metadata: {e}")


def extract_old_forge_meta(
    jar: zipfile.ZipFile, data: JarData, info_path: str = "mcmod.info"
):
    """Extract metadata from mcmod.info or custom `{modname}.info`.
    Handles both v1 (root array) and v2 ({modListVersion:2, modList:[...]}) formats.
    """
    try:
        with jar.open(info_path) as f:
            try:
                # Strip whitespace + UTF-8 BOM before parsing
                content = (
                    f.read().decode("utf-8", errors="ignore").strip().lstrip("\ufeff")
                )
                # Replace newlines and tabs with spaces to avoid raw control characters breaking the parser
                content = (
                    content.replace("\n", " ").replace("\r", " ").replace("\t", " ")
                )
                meta = json.loads(content, strict=False)

                # Normalise: v2 format wraps the list under a 'modList' key
                if isinstance(meta, dict):
                    mod_list = meta.get("modList") or meta.get("modlist") or []
                elif isinstance(meta, list):
                    mod_list = meta
                else:
                    mod_list = []

                if mod_list and len(mod_list) > 0:
                    mod = mod_list[0]
                    data.parsed_from.append(info_path)
                    data.mod_loader = "Old Forge"
                    data.mod_id = mod.get("modid", data.file_name)
                    data.mod_name = mod.get("name", data.mod_id)
                    data.version = mod.get("version", "Unknown")
                    raw_desc = mod.get("description", "")
                    data.description = raw_desc.strip() if raw_desc else ""
                    data.authors = mod.get("authorList", [])

                    # Try to get MC version (mcversion preferred, fallback acceptedMinecraftVersions)
                    if "mcversion" in mod:
                        data.mc_version = str(mod.get("mcversion", "")).strip()
                    elif "acceptedMinecraftVersions" in mod:
                        data.mc_version = str(
                            mod.get("acceptedMinecraftVersions", "")
                        ).strip()

                    # If we got a real version or mc_version, this definitely IS an MC mod
                    if data.version not in ("Unknown", "Unknown Version", "") or (
                        data.mc_version and data.mc_version not in ("Unknown", "")
                    ):
                        data.is_minecraft_related = True

                    # Dependencies
                    data.dependencies = []
                    for dep_key in ("requiredMods", "dependencies"):
                        deps = mod.get(dep_key, [])
                        for d in deps:
                            d_id = d.strip() if isinstance(d, str) else d.get("id", "")
                            if d_id and d_id.lower() not in ("forge", "minecraft", ""):
                                if not any(x["id"] == d_id for x in data.dependencies):
                                    data.dependencies.append(
                                        {"id": d_id, "optional": False}
                                    )

                    logo_file = mod.get("logoFile", "")
                    if logo_file:
                        logo_file = logo_file.strip()
                        if logo_file in jar.namelist():
                            with jar.open(logo_file) as icon_f:
                                data.icon_bytes = icon_f.read()
            except json.JSONDecodeError as e:
                print(f"Failed parsing {info_path} JSON: {e}")

    except Exception as e:
        print(f"Failed parsing old forge metadata ({info_path}): {e}")


def extract_manifest_meta(jar: zipfile.ZipFile, data: JarData):
    """Extract metadata from META-INF/MANIFEST.MF especially for Tweak/Tweaker mods."""
    manifest_path = "META-INF/MANIFEST.MF"
    # Use a more robust check for the manifest file
    actual_path = None
    for name in jar.namelist():
        if name.upper() == manifest_path:
            actual_path = name
            break

    if not actual_path:
        return

    try:
        with jar.open(actual_path) as f:
            lines = f.read().decode("utf-8", errors="ignore").splitlines()

            manifest = {}
            current_key = None
            for line in lines:
                if not line.strip():
                    continue
                if line.startswith(" "):  # Continuation line
                    if current_key:
                        manifest[current_key] += line.strip()
                elif ":" in line:
                    parts = line.split(":", 1)
                    current_key = parts[0].strip()
                    manifest[current_key] = parts[1].strip()

            tweak_ver = manifest.get("TweakVersion")
            tweak_name = manifest.get("TweakName")
            tweak_author = manifest.get("TweakAuthor")
            tweak_meta = manifest.get("TweakMetaFile")

            # Additional Fallback Manifest Keys
            bundle_ver = manifest.get("Bundle-Version")
            bundle_vendor = manifest.get("Bundle-Vendor")
            impl_title = manifest.get("Implementation-Title")
            impl_ver = manifest.get("Implementation-Version")
            built_by = manifest.get("Built-By")

            if (
                tweak_ver
                or tweak_name
                or tweak_author
                or tweak_meta
                or bundle_ver
                or bundle_vendor
                or impl_title
                or impl_ver
                or built_by
            ):
                if actual_path not in data.parsed_from:
                    data.parsed_from.append(actual_path)

                # Only overwrite loader if it's generic
                if data.mod_loader in (
                    "Unknown Archive",
                    "Vanilla/Library JAR (No Mod Metadata)",
                    "Unknown",
                ):
                    if tweak_meta or tweak_ver:
                        data.mod_loader = "Tweaker Mod"
                    else:
                        data.mod_loader = "Jar Manifest Metadata"

                # Setup Versions and Info
                placeholders = (
                    "unknown",
                    "unknown version",
                    "",
                    "@version@",
                    "${mod_version}",
                    "${version}",
                    "${file.jarversion}",
                    "${file.jar_version}",
                )
                extracted_version = tweak_ver or bundle_ver or impl_ver
                if extracted_version and data.version.lower() in placeholders:
                    data.version = str(extracted_version)

                extracted_name = tweak_name or impl_title or bundle_vendor
                if extracted_name and (
                    data.mod_name == "Unknown"
                    or data.mod_name == data.file_name.replace(".jar", "")
                ):
                    data.mod_name = str(extracted_name)

                extracted_author = tweak_author or built_by or bundle_vendor
                if extracted_author and not data.authors:
                    data.authors = [str(extracted_author)]

                if tweak_meta:
                    # Search for this meta file in the JAR
                    meta_file_path = None
                    for name in jar.namelist():
                        if name == tweak_meta or name.endswith("/" + tweak_meta):
                            meta_file_path = name
                            break

                    if meta_file_path:
                        with jar.open(meta_file_path) as meta_f:
                            try:
                                content = meta_f.read().decode("utf-8", errors="ignore")
                                meta_data = json.loads(content, strict=False)
                                if meta_file_path not in data.parsed_from:
                                    data.parsed_from.append(meta_file_path)

                                # Higher priority than manifest, but only if not empty
                                meta_ver = meta_data.get("version")
                                if meta_ver and str(meta_ver).strip():
                                    data.version = str(meta_ver)

                                meta_id = meta_data.get("id")
                                if (
                                    meta_id
                                    and str(meta_id).strip()
                                    and data.mod_id == "unknown"
                                ):
                                    data.mod_id = str(meta_id)

                                meta_name = meta_data.get("name")
                                if meta_name:
                                    data.mod_name = str(meta_name)

                                meta_author = meta_data.get("author")
                                if meta_author:
                                    data.authors = [str(meta_author)]

                                meta_desc = meta_data.get("description")
                                if meta_desc:
                                    data.description = str(meta_desc)

                                meta_mc = meta_data.get("mcversion")
                                if meta_mc and data.mc_version == "Unknown":
                                    data.mc_version = str(meta_mc)

                            except Exception as e:
                                print(
                                    f"Failed parsing manifest metadata file {meta_file_path}: {e}"
                                )

    except Exception as e:
        print(f"Failed parsing manifest: {e}")


def read_jar_file(
    file_path: str, enable_deep_search: bool = False, progress_callback=None
) -> JarData:
    """Reads a JAR file, determines its loader, metadata, and extracts raw data."""
    if not is_valid_jar(file_path):
        raise ValueError(f"Invalid JAR file: {file_path}")

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    data = JarData(
        file_path=file_path,
        file_name=file_name,
        file_size_bytes=file_size,
        mod_name=file_name.replace(".jar", ""),  # Fallback name
    )

    try:
        with zipfile.ZipFile(file_path, "r") as jar:
            file_list = jar.namelist()
            data.file_list = file_list
            data.total_files = len(file_list)

            # 1. Sniff Java version
            class_files = [f for f in file_list if f.endswith(".class")]
            data.java_version = sniff_java_version(jar, class_files)

            # Check if Minecraft related
            mc_related = False
            for f in file_list:
                f_lower = f.lower()
                if (
                    f_lower.startswith("net/minecraft/")
                    or f_lower.startswith("com/mojang/")
                    or f_lower
                    in (
                        "fabric.mod.json",
                        "quilt.mod.json",
                        "meta-inf/neoforge.mods.toml",
                        "meta-inf/mods.toml",
                        "mcmod.info",
                        "pack.mcmeta",
                    )
                    or "bungee" in f_lower
                    or "spigot" in f_lower
                    or "bukkit" in f_lower
                ):
                    mc_related = True
                    break
            data.is_minecraft_related = mc_related

            # 2. Determine Loader & Extract Metadata
            loaders_found = []
            meta_extracted = False

            if "fabric.mod.json" in file_list:
                loaders_found.append("Fabric")
                if not meta_extracted:
                    extract_fabric_meta(jar, data)
                    meta_extracted = True

            if "quilt.mod.json" in file_list:
                loaders_found.append("Quilt")
                if not meta_extracted:
                    extract_quilt_meta(jar, data)
                    meta_extracted = True

            if "META-INF/neoforge.mods.toml" in file_list:
                loaders_found.append("NeoForge")
                if not meta_extracted:
                    extract_forge_meta(
                        jar, data, "META-INF/neoforge.mods.toml", "NeoForge"
                    )
                    meta_extracted = True

            if "META-INF/mods.toml" in file_list:
                loaders_found.append("Forge")
                if not meta_extracted:
                    extract_forge_meta(jar, data, "META-INF/mods.toml", "Forge")
                    meta_extracted = True
            info_files = [f for f in file_list if f.endswith(".info") and "/" not in f]
            if "mcmod.info" in file_list and "mcmod.info" not in info_files:
                info_files.insert(0, "mcmod.info")

            if info_files:
                loaders_found.append("Forge (Legacy)")
                if not meta_extracted:
                    extract_old_forge_meta(jar, data, info_path=info_files[0])
                    meta_extracted = True

            # --- MANIFEST / TWEAKER FALLBACK ---
            placeholders = (
                "unknown",
                "unknown version",
                "",
                "@version@",
                "${mod_version}",
                "${version}",
                "${file.jarversion}",
                "${file.jar_version}",
            )
            if not meta_extracted or data.version.lower() in placeholders:
                extract_manifest_meta(jar, data)
                if data.mod_loader == "Tweaker Mod":
                    meta_extracted = True
                    # If we got tweaker data, this IS a MC-related file
                    data.is_minecraft_related = True

            if loaders_found:
                data.mod_loader = " / ".join(loaders_found)
            else:
                # It might be an unmodded client jar, server jar, or library jar.
                # Let's check for META-INF/MANIFEST.MF just in case it's a generic Jar
                if "META-INF/MANIFEST.MF" in file_list:
                    data.mod_loader = "Vanilla/Library JAR (No Mod Metadata)"
                else:
                    data.mod_loader = "Unknown Archive"

            if data.mc_version == "${minecraft_version}":
                data.mc_version = "Unknown"

            # --- FINAL MC-RELATED CHECK ---
            # If metadata was successfully parsed and has real version or mc_version data,
            # it's definitely an MC-related file even if it had no MC class paths.
            if not data.is_minecraft_related and data.parsed_from:
                has_real_version = data.version not in (
                    "Unknown",
                    "Unknown Version",
                    "",
                )
                has_real_mc_ver = bool(data.mc_version) and data.mc_version not in (
                    "Unknown",
                    "",
                )
                if has_real_version or has_real_mc_ver:
                    data.is_minecraft_related = True

            # --- DEEP SEARCH FALLBACK ---
            if (
                enable_deep_search
                and (
                    data.mc_version == "Unknown"
                    or data.mod_id == "unknown"
                    or data.version in ("Unknown", "Unknown Version")
                    or not data.parsed_from
                )
                and class_files
            ):
                # 1. Gather likely candidate files to try and extract info from. Limit to 3 files.
                import re, subprocess, tempfile

                candidates = []
                # Attempt to extract a base slug (e.g., 'ae2stuff-0.6.0.9' -> 'ae2stuff')
                raw_name = (
                    data.mod_id
                    if data.mod_id != "unknown"
                    else data.file_name.replace(".jar", "")
                )

                # Strip version numbers nicely by splitting at the first thing that looks like a version (-1.x, -v1.x, -mc1.x)
                name_without_version = re.split(
                    r"[-_]?(?:v?[0-9]+\.[0-9]|mc[0-9])", raw_name, flags=re.IGNORECASE
                )[0]

                base_search = name_without_version.lower()
                base_search_alphanum = re.sub(
                    r"[^a-z0-9]", "", base_search
                )  # Keep numbers for mods like ae2stuff

                perfect_matches = []
                good_matches = []

                for f in class_files:
                    fl = f.lower()
                    filename = os.path.basename(fl)
                    name_only = filename.replace(".class", "")

                    # 1. Perfect matches: slug exactly matches the class name
                    if (
                        name_only == base_search
                        or name_only == base_search_alphanum
                        or name_only == f"{base_search_alphanum}mod"
                        or name_only == f"{base_search_alphanum}core"
                        or name_only == f"{base_search}mod"
                    ):
                        perfect_matches.append(f)
                    # 2. Generic main classes
                    elif name_only in ("main", "plugin", "mod", "core", "base"):
                        good_matches.append(f)
                    # 3. Partial matches
                    elif (
                        len(base_search_alphanum) >= 3
                        and base_search_alphanum in name_only
                    ) or (len(base_search) >= 3 and base_search in name_only):
                        good_matches.append(f)

                # Combine, ensuring perfect exact matches are tested first
                candidates = perfect_matches + good_matches

                # If we haven't found a perfect match by name, let's do a fast byte-scan of all classes
                if not perfect_matches:
                    byte_matches = []
                    mod_annotation_matches = []
                    try:
                        with zipfile.ZipFile(file_path, "r") as zf_fast:
                            for f in class_files:
                                try:
                                    # Read just the first few KB or the whole thing since it's in memory
                                    raw_bytes = zf_fast.read(f)
                                    # Look for the literal string "Lnet/minecraft/fml/common/Mod;" or "@Mod" in the constant pool
                                    if (
                                        b"Lnet/minecraft/fml/common/Mod;" in raw_bytes
                                        or b"Lnet/minecraftforge/fml/common/Mod;"
                                        in raw_bytes
                                    ):
                                        mod_annotation_matches.append(f)
                                    elif b"Lnet/minecraft" in raw_bytes:
                                        byte_matches.append(f)
                                except Exception:
                                    pass
                    except Exception as e:
                        print(f"Fast byte scan failed: {e}")

                    # Prioritize classes that actually contain the @Mod annotation signature
                    candidates = mod_annotation_matches + byte_matches + candidates

                    # Remove duplicates while preserving order
                    seen = set()
                    candidates = [
                        x for x in candidates if not (x in seen or seen.add(x))
                    ]

                # Ensure we don't freeze the app testing 500 files
                candidates = candidates[:3]

                cfr_path = os.path.join(os.path.dirname(__file__), "assets", "cfr.jar")
                if os.path.exists(cfr_path) and shutil.which("java"):
                    success = False
                    total_candidates = len(candidates)
                    for step_idx, class_path in enumerate(candidates):
                        if success:
                            break
                        try:
                            if progress_callback:
                                progress_pct = int((step_idx / total_candidates) * 100)
                                progress_callback(
                                    progress_pct,
                                    f"Deep Scanning: {os.path.basename(class_path)}",
                                )

                            with zipfile.ZipFile(file_path, "r") as zf_deep:
                                content_bytes = zf_deep.read(class_path)

                            with tempfile.NamedTemporaryFile(
                                suffix=".class", delete=False
                            ) as tmp:
                                tmp.write(content_bytes)
                                tmp_path = tmp.name

                            try:
                                # Decompile
                                result = subprocess.run(
                                    ["java", "-jar", cfr_path, tmp_path],
                                    capture_output=True,
                                    text=True,
                                    check=False,
                                )
                                java_code = result.stdout

                                # Search for @Mod annotation start
                                mod_start_idx = java_code.find("@Mod")
                                if mod_start_idx != -1:
                                    # Find the opening parenthesis
                                    paren_start = java_code.find("(", mod_start_idx)
                                    if paren_start != -1:
                                        # Find the balanced closing parenthesis
                                        mod_body = ""
                                        depth = 0
                                        in_quotes = False
                                        for i in range(paren_start, len(java_code)):
                                            char = java_code[i]
                                            if char == '"' and (
                                                i == 0 or java_code[i - 1] != "\\"
                                            ):
                                                in_quotes = not in_quotes

                                            if not in_quotes:
                                                if char == "(":
                                                    depth += 1
                                                elif char == ")":
                                                    depth -= 1
                                                    if depth == 0:
                                                        mod_body = java_code[
                                                            paren_start + 1 : i
                                                        ]
                                                        break

                                        if mod_body:
                                            # Extract fields more leniently
                                            modid_m = re.search(
                                                r'modid\s*=\s*"([^"]+)"', mod_body
                                            )
                                            if modid_m:
                                                data.mod_id = modid_m.group(1)

                                            ver_m = re.search(
                                                r'version\s*=\s*"([^"]+)"', mod_body
                                            )
                                            if ver_m:
                                                data.version = ver_m.group(1)

                                            name_m = re.search(
                                                r'name\s*=\s*"([^"]+)"', mod_body
                                            )
                                            if name_m:
                                                data.mod_name = name_m.group(1)
                                            elif data.mod_name == "Unknown" and modid_m:
                                                data.mod_name = modid_m.group(1)

                                            mc_m = re.search(
                                                r'acceptedMinecraftVersions\s*=\s*"([^"]+)"',
                                                mod_body,
                                            )
                                            if mc_m:
                                                data.mc_version = mc_m.group(1)

                                            url_m = re.search(
                                                r'updateUrl\s*=\s*"([^"]+)"', mod_body
                                            )
                                            if url_m:
                                                data.update_url = url_m.group(1)

                                            url_m2 = re.search(
                                                r'url\s*=\s*"([^"]+)"', mod_body
                                            )
                                            if url_m2:
                                                data.url = url_m2.group(1)

                                            dep_m = re.search(
                                                r'dependencies\s*=\s*"([^"]+)"',
                                                mod_body,
                                            )
                                            if dep_m:
                                                dep_str = dep_m.group(1)
                                                for p in dep_str.split(";"):
                                                    p = p.strip()
                                                    if not p:
                                                        continue
                                                    # forge dependency string e.g., required-after:appliedenergistics2
                                                    parts = p.split(":")
                                                    if len(parts) >= 2:
                                                        dep_type = parts[0]
                                                        dep_id = parts[1].split("@")[0]
                                                        optional = (
                                                            "required"
                                                            not in dep_type.lower()
                                                        )
                                                        # Check if already added to avoid duplicates
                                                        if not any(
                                                            d["id"] == dep_id
                                                            for d in data.dependencies
                                                        ):
                                                            data.dependencies.append(
                                                                {
                                                                    "id": dep_id,
                                                                    "optional": optional,
                                                                }
                                                            )

                                            if ver_m or mc_m or modid_m:
                                                pass  # handled below

                                # Add fallback for standard static final fields
                                fallback_ver_m = re.search(
                                    r'(?:public\s+)?(?:static\s+)?final\s+String\s+VERSION\s*=\s*"([^"]+)"',
                                    java_code,
                                )
                                if fallback_ver_m and data.version in (
                                    "Unknown",
                                    "Unknown Version",
                                    "",
                                ):
                                    data.version = fallback_ver_m.group(1)

                                fallback_mc_m = re.search(
                                    r'(?:public\s+)?(?:static\s+)?final\s+String\s+MC_VERSION\s*=\s*"([^"]+)"',
                                    java_code,
                                )
                                if fallback_mc_m and data.mc_version in ("Unknown", ""):
                                    data.mc_version = fallback_mc_m.group(1)

                                fallback_modid_m = re.search(
                                    r'(?:public\s+)?(?:static\s+)?final\s+String\s+(?:MOD_?ID|ID)\s*=\s*"([^"]+)"',
                                    java_code,
                                )
                                if fallback_modid_m and data.mod_id == "unknown":
                                    data.mod_id = fallback_modid_m.group(1)

                                fallback_name_m = re.search(
                                    r'(?:public\s+)?(?:static\s+)?final\s+String\s+(?:MOD_)?NAME\s*=\s*"([^"]+)"',
                                    java_code,
                                )
                                if fallback_name_m and (
                                    data.mod_name == "Unknown"
                                    or data.mod_name
                                    == data.file_name.replace(".jar", "")
                                ):
                                    data.mod_name = fallback_name_m.group(1)

                                fallback_url_m = re.search(
                                    r'(?:public\s+)?(?:static\s+)?final\s+String\s+UPDATE_URL\s*=\s*"([^"]+)"',
                                    java_code,
                                )
                                if fallback_url_m:
                                    data.update_url = fallback_url_m.group(1)

                                fallback_url_m2 = re.search(
                                    r'(?:public\s+)?(?:static\s+)?final\s+String\s+URL\s*=\s*"([^"]+)"',
                                    java_code,
                                )
                                if fallback_url_m2:
                                    data.url = fallback_url_m2.group(1)

                                has_mod_body_match = False
                                if "ver_m" in locals() and ver_m:
                                    has_mod_body_match = True
                                if "mc_m" in locals() and mc_m:
                                    has_mod_body_match = True
                                if "modid_m" in locals() and modid_m:
                                    has_mod_body_match = True

                                if (
                                    has_mod_body_match
                                    or fallback_ver_m
                                    or fallback_mc_m
                                    or fallback_modid_m
                                    or fallback_name_m
                                ):
                                    parsed_str = f"[Decompiled] {class_path}"
                                    if parsed_str not in data.parsed_from:
                                        data.parsed_from.append(parsed_str)
                                    if data.mod_loader in (
                                        "Unknown Archive",
                                        "Vanilla/Library JAR (No Mod Metadata)",
                                    ):
                                        data.mod_loader = "Forge (Deep Scan)"
                                    data.is_minecraft_related = True
                                    success = True
                            finally:
                                try:
                                    os.remove(tmp_path)
                                except:
                                    pass
                        except Exception as ex:
                            print(f"Deep scan error on {class_path}: {ex}")

            # --- PLACEHOLDER FALLBACKS ---
            placeholders = (
                "@version@",
                "${mod_version}",
                "${version}",
                "${file.jarversion}",
                "${file.jar_version}",
            )
            if data.version.lower() in placeholders:
                import re

                raw_filename = data.file_name.replace(".jar", "")

                # Remove universal/deobf/all etc from the end
                raw_filename = re.sub(
                    r"-(?:universal|all|deobf|api|client|server)$",
                    "",
                    raw_filename,
                    flags=re.IGNORECASE,
                )

                # Try splitting off the part that looks like the mod name
                name_without_version = re.split(
                    r"[-_]?(?:v?[0-9]+\.[0-9]|mc[0-9])",
                    raw_filename,
                    flags=re.IGNORECASE,
                )[0]
                extracted_ver = raw_filename[len(name_without_version) :].lstrip("-_")

                if extracted_ver:
                    # Clean known MC versions from the prefix or suffix
                    if data.mc_version not in (
                        "Unknown",
                        "${minecraft_version}",
                        "",
                        "Unknown Version",
                    ):
                        known_mc_vers = [
                            v.strip()
                            for v in data.mc_version.replace("|", ",")
                            .replace(" ", "")
                            .split(",")
                        ]
                        for mv in known_mc_vers:
                            if mv:
                                if extracted_ver.startswith(mv):
                                    stripped = extracted_ver[len(mv) :].lstrip("-_")
                                    if stripped:
                                        extracted_ver = stripped
                                        break
                                elif extracted_ver.endswith(mv):
                                    stripped = extracted_ver[: -len(mv)].rstrip("-_")
                                    if stripped:
                                        extracted_ver = stripped
                                        break
                    else:
                        # Fallback stripping of generic MC versions like '1.10.2'
                        mc_ver_pattern = r"^(?:1\.[1-9][0-9]?(?:\.[0-9]{1,2})?)[-_]"
                        stripped = re.sub(mc_ver_pattern, "", extracted_ver)
                        if stripped and stripped != extracted_ver:
                            extracted_ver = stripped
                        else:
                            mc_ver_pattern_end = (
                                r"[-_](?:1\.[1-9][0-9]?(?:\.[0-9]{1,2})?)$"
                            )
                            stripped = re.sub(mc_ver_pattern_end, "", extracted_ver)
                            if stripped:
                                extracted_ver = stripped

                    data.version = extracted_ver if extracted_ver else raw_filename
                else:
                    data.version = raw_filename

                if "self" not in data.parsed_from:
                    data.parsed_from.append("self")

    except zipfile.BadZipFile:
        data.mod_loader = "Corrupted/Invalid ZIP"
    except Exception as e:
        data.mod_loader = f"Error reading JAR: {e}"

    return data


def process_jar_folder(
    folder_path: str, enable_deep_search: bool = False, progress_callback=None
) -> list[JarData]:
    """Iterates through a folder and processes all JARs inside."""
    results = []
    if os.path.isdir(folder_path):
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".jar"):
                    full_path = os.path.join(root, file)
                    try:
                        jar_data = read_jar_file(
                            full_path,
                            enable_deep_search=enable_deep_search,
                            progress_callback=progress_callback,
                        )
                        results.append(jar_data)
                    except Exception as e:
                        print(f"Skipping {file}: {e}")
    return results


def read_pack_file(file_path: str, category: str) -> JarData:
    """Reads a .zip resourcepack or shaderpack."""
    if not is_valid_jar(file_path):
        raise ValueError(f"Invalid Pack file: {file_path}")

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    data = JarData(
        file_path=file_path,
        file_name=file_name,
        file_size_bytes=file_size,
        mod_name=file_name.replace(".zip", ""),
        category=category,
        mod_loader=category[:-1],  # "Resourcepack" or "Shaderpack"
    )

    try:
        with zipfile.ZipFile(file_path, "r") as jar:
            file_list = jar.namelist()
            data.file_list = file_list
            data.total_files = len(file_list)

            if category == "Resourcepacks":
                if "pack.mcmeta" in file_list:
                    data.is_minecraft_related = True
                    try:
                        with jar.open("pack.mcmeta") as f:
                            meta = json.load(f)
                            data.parsed_from.append("pack.mcmeta")
                            pack_meta = meta.get("pack", {})
                            desc = pack_meta.get("description", "")

                            if isinstance(desc, dict):
                                data.description = json.dumps(desc)
                            elif isinstance(desc, list):
                                data.description = " ".join(
                                    [
                                        (
                                            str(d.get("text", ""))
                                            if isinstance(d, dict)
                                            else str(d)
                                        )
                                        for d in desc
                                    ]
                                )
                            else:
                                data.description = str(desc)

                            pack_format = pack_meta.get("pack_format", "Unknown")
                            data.version = f"Format {pack_format}"
                            if isinstance(pack_format, int):
                                data.mc_version = get_mc_version_from_pack_format(
                                    pack_format
                                )
                    except Exception as e:
                        print(f"Failed parsing pack.mcmeta: {e}")

                if "pack.png" in file_list:
                    try:
                        with jar.open("pack.png") as f:
                            data.icon_bytes = f.read()
                    except Exception as e:
                        pass

            elif category == "Shaderpacks":
                data.is_minecraft_related = True
                data.description = "A Minecraft Shaderpack."

    except zipfile.BadZipFile:
        data.mod_loader = "Corrupted/Invalid ZIP"
    except Exception as e:
        data.mod_loader = f"Error reading Pack: {e}"

    return data


def process_instance_folder(
    folder_path: str, enable_deep_search: bool = False
) -> list[JarData]:
    """Scans an instance folder for any directories containing jars/zips dynamically."""
    results = []

    # Iterate through all top-level directories in the instance folder
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)

        if os.path.isdir(item_path):
            if item.lower() not in ("mods", "resourcepacks", "shaderpacks"):
                continue

            # Base category name based on the folder name
            base_category = item.capitalize()
            if item.lower() == "mods":
                base_category = "Mods"
            elif item.lower() == "resourcepacks":
                base_category = "Resourcepacks"
            elif item.lower() == "shaderpacks":
                base_category = "Shaderpacks"

            # Deep scan inside this top level folder
            for root, _, files in os.walk(item_path):
                # Sub-category based on sub-directories (e.g. Mods - 1.20)
                rel_path = os.path.relpath(root, item_path)
                category = base_category
                if rel_path != ".":
                    # E.g. "Mods - 1.20.1 / optimizers"
                    sub_label = rel_path.replace(os.sep, " / ")
                    category = f"{base_category} - {sub_label}"

                for file in files:
                    full_path = os.path.join(root, file)
                    if file.lower().endswith(".jar"):
                        try:
                            # Parse jars found anywhere inside these directories
                            jar_data = read_jar_file(
                                full_path, enable_deep_search=enable_deep_search
                            )
                            jar_data.category = category
                            results.append(jar_data)
                        except Exception as e:
                            print(f"Skipping {file}: {e}")

                    elif file.lower().endswith(".zip"):
                        try:
                            # Parse zips found anywhere
                            pack_data = read_pack_file(full_path, category)
                            results.append(pack_data)
                        except Exception as e:
                            print(f"Skipping {file}: {e}")

    return results


def detect_instance_meta(folder_path: str) -> tuple[str | None, str | None]:
    """Attempts to read launcher-specific metadata files to determine exactly what MC version and Loader is used."""
    mc_version = None
    loader = None

    # 1. MultiMC / Prism Launcher (instance.cfg)
    cfg_path = os.path.join(folder_path, "instance.cfg")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("IntendedVersion="):
                        mc_version = line.split("=", 1)[1].strip()
        except:
            pass

    # mmc-pack.json (Prism / MultiMC details)
    mmc_path = os.path.join(folder_path, "mmc-pack.json")
    if os.path.isfile(mmc_path):
        try:
            with open(mmc_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                loaders = []
                for comp in data.get("components", []):
                    uid = comp.get("uid", "")
                    ver = comp.get("version", "")
                    if uid == "net.minecraft":
                        mc_version = ver
                    elif uid == "net.fabricmc.fabric-loader":
                        loaders.append(f"Fabric {ver}")
                    elif uid == "net.minecraftforge":
                        loaders.append(f"Forge {ver}")
                    elif uid == "org.quiltmc.quilt-loader":
                        loaders.append(f"Quilt {ver}")
                    elif uid == "net.neoforged":
                        loaders.append(f"NeoForge {ver}")
                if loaders:
                    loader = " / ".join(loaders)
        except:
            pass

    # 2. CurseForge (minecraftinstance.json)
    cf_path = os.path.join(folder_path, "minecraftinstance.json")
    if os.path.isfile(cf_path):
        try:
            with open(cf_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not mc_version:
                    mc_version = data.get("gameVersion", mc_version)

                if not loader:
                    base_loader = data.get("baseModLoader", {})
                    loader_name = base_loader.get("name", "")
                    if loader_name:
                        if "forge" in loader_name.lower():
                            loader = "Forge"
                        elif "fabric" in loader_name.lower():
                            loader = "Fabric"
                        elif "quilt" in loader_name.lower():
                            loader = "Quilt"
                        elif "neoforge" in loader_name.lower():
                            loader = "NeoForge"
                        else:
                            loader = loader_name
                        loader = f"{loader} ({loader_name})"
        except:
            pass

    return mc_version, loader

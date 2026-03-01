import re


def clean_ver(raw_filename, mc_version):
    # Remove universal/deobf/all etc from the end
    raw_filename = re.sub(
        r"-(?:universal|all|deobf|api|client|server)$",
        "",
        raw_filename,
        flags=re.IGNORECASE,
    )

    # Try splitting off the part that looks like the mod name
    # We find the first chunk that looks like a version block: "-1.", "-mc", "-v1."
    name_without_version = re.split(
        r"[-_]?(?:v?[0-9]+\.[0-9]|mc[0-9])", raw_filename, flags=re.IGNORECASE
    )[0]
    extracted_ver = raw_filename[len(name_without_version) :].lstrip("-_")

    if not extracted_ver:
        return raw_filename

    # Clean known MC versions from the prefix or suffix
    if mc_version not in ("Unknown", "${minecraft_version}", "", "Unknown Version"):
        known_mc_vers = [
            v.strip() for v in mc_version.replace("|", ",").replace(" ", "").split(",")
        ]
        for mv in known_mc_vers:
            if mv:
                # e.g., if extracted_ver "1.10.2-5.0.0" starts with "1.10.2"
                if extracted_ver.startswith(mv):
                    stripped = extracted_ver[len(mv) :].lstrip("-_")
                    if stripped:
                        extracted_ver = stripped
                        break
                # e.g., if extracted_ver "5.0.0-1.10.2" ends with "1.10.2"
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
            mc_ver_pattern_end = r"[-_](?:1\.[1-9][0-9]?(?:\.[0-9]{1,2})?)$"
            stripped = re.sub(mc_ver_pattern_end, "", extracted_ver)
            if stripped:
                extracted_ver = stripped

    return extracted_ver


print("Lockdown:", clean_ver("Lockdown-1.10.2-5.0.0-universal", "1.10.2"))
print("Foamfix:", clean_ver("foamfix-0.7.5", "Unknown"))
print("SomeMod:", clean_ver("SomeMod-5.0.0-1.10.2", "1.10.2"))
print("AnotherMod:", clean_ver("AnotherMod-1.12.2-v1.4", "Unknown"))

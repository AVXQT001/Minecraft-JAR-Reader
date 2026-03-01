# 🎮 Minecraft JAR Reader

A premium, high-performance tool for analyzing Minecraft mod JARs and instance directories. Built for modders and players who need deep insights into their modded environments.

---

## ✨ Features

### 🔍 Deep Metadata Extraction

- **Multi-Loader Support**: Seamlessly reads `fabric.mod.json`, `quilt.mod.json`, and `mods.toml`.
- **Legacy Forge Support**: "Deep Search" mode scans `.class` files for `@Mod` annotations (requires Java).
- **Resource & Shader Packs**: Detects `pack.mcmeta` and maps internal formats to Minecraft versions.

### 📂 Instance Intelligence

- **One-Click Loading**: Select a Minecraft instance folder and let the app categorize `mods`, `resourcepacks`, and `shaderpacks`.
- **Auto-Detection**: Identifies the primary Minecraft version and mod loader of the instance.
- **Dependency Tracking**: Visualizes required vs. optional dependencies with interactive links to jump between mods.
- **Compatibility Guard**: Flags mods that don't match the instance's target Minecraft version or loader.

### 🎨 Premium UI Experience

- **Modern Aesthetics**: Sleek dark mode with customizable transparency (Glassmorphism).
- **Minecraft Auth**: Features authentic Minecraft sound effects (`.wav`) for interactive elements.
- **Internal Explorer**: Browse the internal structure of any JAR and decompile Java classes on the fly.
- **Syntax Highlighting**: Built-in highlighters for `JSON`, `TOML`, `Java`, and more.

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **[uv](https://github.com/astral-sh/uv)** (Recommended for dependency management)

### Installation

Clone the repository and install dependencies:

```bash
uv pip install -r requirements.txt
```

### Running the App

```bash
uv run main.py
```

Or use the provided `start.bat`.

---

## 🛠️ Building to Executable

The project uses **Nuitka** for high-performance, standalone compilation.

### Build Steps

Run the included build script:

```bash
build.bat
```

### Build Config Details

- **Standalone**: Compiled without needing a local Python installation.
- **Optimization**: Uses the Nuitka PyQt6 plugin for correct asset/plugin inclusion.
- **Console-less**: The final executable runs without a background command prompt.
- **Multimedia**: Includes necessary Qt6 Multimedia backends for sound support.

---

## 🛠️ Technical Stack

- **Language**: Python 3.12
- **UI Framework**: PyQt6
- **Architecture**: Multi-threaded JAR processing with a custom Metadata engine.
- **Compiler**: Nuitka

---

## 📜 License

_Distributed under the MIT License. See `LICENSE` for more information._

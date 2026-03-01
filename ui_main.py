import os
from collections import defaultdict
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTreeView,
    QListWidget,
    QSplitter,
    QLabel,
    QFileDialog,
    QListWidgetItem,
    QTabWidget,
    QScrollArea,
    QApplication,
    QSlider,
    QSizePolicy,
    QMessageBox,
    QLineEdit,
    QCheckBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QComboBox,
    QTextEdit,
    QDialog,
    QProgressBar,
    QStackedWidget,
)
from PyQt6.QtCore import Qt, QSize, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import (
    QIcon,
    QPixmap,
    QStandardItemModel,
    QStandardItem,
    QImage,
    QColor,
    QTextDocument,
    QAbstractTextDocumentLayout,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
    QFont,
    QPainter,
)
from PyQt6.QtMultimedia import QSoundEffect
import semantic_version
import re

from models import JarData
from core_reader import (
    read_jar_file,
    process_jar_folder,
    process_instance_folder,
    detect_instance_meta,
)
from theme_manager import apply_theme


class ConfigHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        def fmt(color, bold=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            return f

        self.rules.append((re.compile(r'".*?"|\'.*?\''), fmt("#6A8759")))
        self.rules.append(
            (re.compile(r"\b[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\b"), fmt("#6897BB"))
        )
        self.rules.append(
            (re.compile(r"\b(true|false|null|None|True|False)\b"), fmt("#CC7832", True))
        )
        self.rules.append((re.compile(r'".*?"\s*:'), fmt("#9876AA")))
        self.rules.append((re.compile(r"\[.*?\]"), fmt("#E8BF6A", True)))
        self.rules.append((re.compile(r"#.*|//.*"), fmt("#808080")))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class JavaHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        def fmt(color, bold=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            return f

        keyword_fmt = fmt("#CC7832", True)
        keywords = [
            "abstract",
            "assert",
            "boolean",
            "break",
            "byte",
            "case",
            "catch",
            "char",
            "class",
            "const",
            "continue",
            "default",
            "do",
            "double",
            "else",
            "enum",
            "extends",
            "final",
            "finally",
            "float",
            "for",
            "goto",
            "if",
            "implements",
            "import",
            "instanceof",
            "int",
            "interface",
            "long",
            "native",
            "new",
            "package",
            "private",
            "protected",
            "public",
            "return",
            "short",
            "static",
            "strictfp",
            "super",
            "switch",
            "synchronized",
            "this",
            "throw",
            "throws",
            "transient",
            "try",
            "void",
            "volatile",
            "while",
            "true",
            "false",
            "null",
        ]

        for word in keywords:
            self.rules.append((re.compile(r"\b" + word + r"\b"), keyword_fmt))

        self.rules.append((re.compile(r'".*?"|\'.*?\''), fmt("#6A8759")))
        self.rules.append(
            (re.compile(r"\b[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\b"), fmt("#6897BB"))
        )
        self.rules.append((re.compile(r"@[a-zA-Z_][a-zA-Z0-9_]*"), fmt("#BBB529")))
        self.rules.append((re.compile(r"//.*"), fmt("#808080")))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class HTMLDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if not painter:
            return
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)

        painter.save()
        doc = QTextDocument()
        doc.setHtml(options.text)
        doc.setDefaultFont(options.font)

        options.text = ""
        style = options.widget.style() if options.widget else QApplication.style()
        if style:
            style.drawControl(style.ControlElement.CE_ItemViewItem, options, painter)

            ctx = QAbstractTextDocumentLayout.PaintContext()

            # Adjust text position based on icon size
            textRect = style.subElementRect(
                style.SubElement.SE_ItemViewItemText, options
            )
            painter.translate(textRect.topLeft())
            painter.setClipRect(textRect.translated(-textRect.topLeft()))

            # If item is selected, we might want to change text color to white, or keep as HTML
            if option.state & style.StateFlag.State_Selected:
                ctx.palette.setColor(
                    QPalette.ColorRole.Text,
                    option.palette.color(
                        QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText
                    ),
                )

            layout = doc.documentLayout()
            if hasattr(layout, "draw"):
                layout.draw(painter, ctx)  # type: ignore
        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        doc = QTextDocument()
        doc.setHtml(options.text)
        doc.setDefaultFont(options.font)
        return QSize(
            int(doc.idealWidth()) + 40, int(doc.size().height()) + 8
        )  # Add space for icon


class JarLoaderWorker(QThread):
    jar_loaded = pyqtSignal(object)  # Emit JarData individually
    progress = pyqtSignal(int, str)
    finished_loading = pyqtSignal(list, str, str)  # results, mc_ver, loader

    def __init__(self, mode, paths, enable_deep_search):
        super().__init__()
        self.mode = mode  # 'file', 'folder', 'instance'
        self.paths = paths  # string or list of strings
        self.enable_deep_search = enable_deep_search

    def run(self):
        results = []
        mc_ver = None
        loader = None

        try:
            if self.mode == "file":
                for i, fp in enumerate(self.paths):
                    self.progress.emit(0, f"Loading {os.path.basename(fp)}...")
                    jar_data = read_jar_file(
                        fp,
                        enable_deep_search=self.enable_deep_search,
                        progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
                    )
                    self.jar_loaded.emit(jar_data)
                    results.append(jar_data)

            elif self.mode == "folder":
                for fld in self.paths:
                    self.progress.emit(0, f"Scanning folder {os.path.basename(fld)}...")
                    # Have to inline the loop to emit dynamically
                    if os.path.isdir(fld):
                        files_to_scan = []
                        for root, _, files in os.walk(fld):
                            for file in files:
                                if file.lower().endswith(".jar"):
                                    files_to_scan.append(os.path.join(root, file))

                        total = len(files_to_scan)
                        for i, full_path in enumerate(files_to_scan):
                            self.progress.emit(
                                int((i / total) * 100),
                                f"({i}/{total}) {os.path.basename(full_path)}",
                            )
                            try:
                                jar_data = read_jar_file(
                                    full_path,
                                    enable_deep_search=self.enable_deep_search,
                                    progress_callback=lambda pct, msg: self.progress.emit(
                                        pct, msg
                                    ),
                                )
                                self.jar_loaded.emit(jar_data)
                                results.append(jar_data)
                            except Exception as e:
                                print(f"Worker skip {full_path}: {e}")

            elif self.mode == "instance":
                fld = self.paths[0]
                self.progress.emit(0, "Analyzing Instance Folders...")
                mc_ver, loader = detect_instance_meta(fld)

                # Inline process_instance_folder for dynamic signals
                folders_to_check = {
                    "mods": os.path.join(fld, "mods"),
                    "resourcepacks": os.path.join(fld, "resourcepacks"),
                    "shaderpacks": os.path.join(fld, "shaderpacks"),
                }

                all_files = []
                for category, path in folders_to_check.items():
                    if os.path.exists(path):
                        for root_dir, _, items in os.walk(path):
                            for item in items:
                                if item.lower().endswith(
                                    ".jar"
                                ) or item.lower().endswith(".zip"):
                                    all_files.append(
                                        (category, os.path.join(root_dir, item))
                                    )

                total = len(all_files)
                for i, (cat, full_path) in enumerate(all_files):
                    self.progress.emit(
                        int((i / total) * 100),
                        f"({i}/{total}) [{cat.upper()}] {os.path.basename(full_path)}",
                    )
                    if full_path.lower().endswith(".jar"):
                        try:
                            jar_data = read_jar_file(
                                full_path,
                                enable_deep_search=self.enable_deep_search,
                                progress_callback=lambda pct, msg: self.progress.emit(
                                    pct, msg
                                ),
                            )
                            jar_data.category = cat.capitalize()
                            self.jar_loaded.emit(jar_data)
                            results.append(jar_data)
                        except Exception as e:
                            print(e)
                    elif full_path.lower().endswith(".zip"):
                        from core_reader import read_pack_file

                        try:
                            jar_data = read_pack_file(
                                full_path, category=cat.capitalize()
                            )
                            self.jar_loaded.emit(jar_data)
                            results.append(jar_data)
                        except Exception as e:
                            print(e)
        except Exception as e:
            print(f"Worker thread error: {e}")

        self.finished_loading.emit(results, mc_ver, loader)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MC-JAR-Reader")

        # App Icon
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "ui_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "ui_icon.png")

        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1000, 600)

        # Apply the aesthetic
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app)

        # Audio Setup (Native WAV playback)
        self.click_sound = QSoundEffect()
        sound_path = os.path.join(
            os.path.dirname(__file__), "assets", "audio", "minecraft_click.wav"
        )
        self.click_sound.setSource(QUrl.fromLocalFile(sound_path))
        self.click_sound.setVolume(1.0)

        # Data store
        self.loaded_jars: list[JarData] = []
        self.current_loaded_type = None
        self.current_loaded_path = None

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # --- Top Button Bar ---
        top_bar = QHBoxLayout()
        btn_load_file = QPushButton("Load JAR File")
        btn_load_folder = QPushButton("Load Folder")
        btn_load_instance = QPushButton("Load Instance Dir")
        btn_clear = QPushButton("Clear All")
        btn_delete = QPushButton("Delete Selected")

        # Prevent buttons from stretching too long and bind clicks
        for btn in (
            btn_load_file,
            btn_load_folder,
            btn_load_instance,
            btn_clear,
            btn_delete,
        ):
            btn.pressed.connect(self.play_click_sound)

        btn_load_file.clicked.connect(self.load_single_jar)
        btn_load_folder.clicked.connect(self.load_folder)
        btn_load_instance.clicked.connect(self.load_instance_dir)
        btn_clear.clicked.connect(self.clear_list)
        btn_delete.clicked.connect(self.delete_selected)

        top_bar.addWidget(btn_load_file)
        top_bar.addWidget(btn_load_folder)
        top_bar.addWidget(btn_load_instance)
        top_bar.addWidget(btn_clear)
        top_bar.addWidget(btn_delete)

        self.chk_deep_search = QCheckBox("Deep Search")
        self.chk_deep_search.setToolTip("Enable deep scanning inside .class files")
        top_bar.addWidget(self.chk_deep_search)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumWidth(150)
        self.progress_bar.setFixedHeight(12)
        top_bar.addWidget(self.progress_bar)

        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        # --- Top Info Bar ---
        self.lbl_global_status = QLabel("No mods loaded.")
        self.lbl_global_status.setObjectName("headerLabel")
        self.lbl_global_status.setStyleSheet(
            "color: #DDDDDD; font-size: 14px; padding: 5px;"
        )
        main_layout.addWidget(self.lbl_global_status)

        # --- Main Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel: List of loaded JARs
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Search & Sort Area
        search_sort_container = QVBoxLayout()
        search_sort_container.setSpacing(5)

        # 1. Search Row
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search mods...")
        self.search_box.textChanged.connect(self.filter_list)
        search_layout.addWidget(self.search_box)
        search_sort_container.addLayout(search_layout)

        # 2. Filter & Sort Row
        filter_sort_layout = QHBoxLayout()

        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["All Categories", "Mods", "Resourcepacks", "Shaderpacks"]
        )
        self.category_combo.currentIndexChanged.connect(self.update_list_and_filter)
        self.category_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        filter_sort_layout.addWidget(self.category_combo)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(
            [
                "Sort by Mod Name",
                "Sort by File Name",
                "Sort by Author",
                "Sort by Loader",
                "Sort by Size",
                "Sort by Version",
                "Sort by Dependents",
            ]
        )
        self.sort_combo.currentIndexChanged.connect(self.update_list_and_filter)
        self.sort_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        filter_sort_layout.addWidget(self.sort_combo)

        search_sort_container.addLayout(filter_sort_layout)

        # 3. Dependency Filter Row
        dep_filter_layout = QHBoxLayout()
        self.dep_filter_combo = QComboBox()
        self.dep_filter_combo.addItem("All Mods (No Library Filter)")
        self.dep_filter_combo.currentIndexChanged.connect(self.update_list_and_filter)
        self.dep_filter_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        dep_filter_layout.addWidget(self.dep_filter_combo)

        self.btn_toggle_hierarchy = QPushButton("Show Hierarchy")
        self.btn_toggle_hierarchy.setCheckable(True)
        self.btn_toggle_hierarchy.toggled.connect(self.update_list_and_filter)
        self.btn_toggle_hierarchy.setFixedWidth(120)
        dep_filter_layout.addWidget(self.btn_toggle_hierarchy)

        search_sort_container.addLayout(dep_filter_layout)

        left_layout.addLayout(search_sort_container)

        self.jar_list = QListWidget()
        self.jar_list.setIconSize(QSize(32, 32))
        self.jar_list.setItemDelegate(HTMLDelegate())
        self.jar_list.itemSelectionChanged.connect(self.on_jar_selected)
        left_layout.addWidget(self.jar_list)

        splitter.addWidget(left_panel)

        # Right Panel: Details Tabs (Meta & File Tree)
        self.tabs = QTabWidget()

        # Meta Tab
        self.meta_tab = QScrollArea()
        self.meta_tab.setWidgetResizable(True)
        self.meta_widget = QWidget()
        self.meta_layout = QVBoxLayout(self.meta_widget)
        self.meta_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Meta Fields
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(64, 64)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setStyleSheet("border: 2px solid #555; background-color: #000;")

        self.lbl_title = QLabel("Select a JAR")
        self.lbl_title.setObjectName("titleLabel")

        self.lbl_file_name = QLabel("File: ")
        self.lbl_file_name.setWordWrap(True)
        self.lbl_file_name.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_file_name.setObjectName("infoLabel")

        self.lbl_loader = QLabel("Loader: ")
        self.lbl_loader.setWordWrap(True)
        self.lbl_loader.setObjectName("infoLabel")
        self.lbl_loader.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_version = QLabel("Version: ")
        self.lbl_version.setObjectName("infoLabel")
        self.lbl_version.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_mc_version = QLabel("MC Version: ")
        self.lbl_mc_version.setObjectName("infoLabel")
        self.lbl_mc_version.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_java = QLabel("Java Version: ")
        self.lbl_java.setWordWrap(True)
        self.lbl_java.setObjectName("infoLabel")
        self.lbl_java.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_authors = QLabel("Authors: ")
        self.lbl_authors.setWordWrap(True)
        self.lbl_authors.setObjectName("infoLabel")
        self.lbl_authors.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_parsed_from = QLabel("Parsed From: None")
        self.lbl_parsed_from.setWordWrap(True)
        self.lbl_parsed_from.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_parsed_from.setOpenExternalLinks(False)
        self.lbl_parsed_from.linkActivated.connect(self.open_parsed_file)
        self.lbl_parsed_from.setObjectName("infoLabel")
        self.lbl_parsed_from.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_depends = QLabel("Dependencies: None")
        self.lbl_depends.setWordWrap(True)
        self.lbl_depends.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_depends.setOpenExternalLinks(False)
        self.lbl_depends.linkActivated.connect(self.jump_to_dependency)
        self.lbl_depends.setObjectName("infoLabel")
        self.lbl_depends.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_required_by = QLabel("Required By: None")
        self.lbl_required_by.setWordWrap(True)
        self.lbl_required_by.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_required_by.setOpenExternalLinks(False)
        self.lbl_required_by.linkActivated.connect(self.jump_to_dependency)
        self.lbl_required_by.setObjectName("infoLabel")
        self.lbl_required_by.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_desc = QLabel("Description: ")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setObjectName("infoLabel")
        self.lbl_desc.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_file_count = QLabel("Files: 0")
        self.lbl_file_count.setObjectName("infoLabel")
        self.lbl_file_count.setTextFormat(Qt.TextFormat.RichText)

        # Add to meta layout
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.lbl_icon)

        titles_layout = QVBoxLayout()
        titles_layout.addWidget(self.lbl_title)
        titles_layout.addWidget(self.lbl_version)
        titles_layout.addWidget(self.lbl_mc_version)
        header_layout.addLayout(titles_layout)
        header_layout.addStretch()

        self.meta_layout.addLayout(header_layout)
        self.meta_layout.addWidget(self.create_header_label("Mod Info"))
        self.meta_layout.addWidget(self.lbl_loader)
        self.meta_layout.addWidget(self.lbl_authors)
        self.meta_layout.addWidget(self.lbl_depends)
        self.meta_layout.addWidget(self.lbl_required_by)
        self.meta_layout.addWidget(self.lbl_desc)

        self.meta_layout.addWidget(self.create_header_label("Technical Details"))
        self.meta_layout.addWidget(self.lbl_file_name)
        self.meta_layout.addWidget(self.lbl_java)
        self.meta_layout.addWidget(self.lbl_file_count)
        self.meta_layout.addWidget(self.lbl_parsed_from)

        self.meta_tab.setWidget(self.meta_widget)
        self.tabs.addTab(self.meta_tab, "Metadata")

        # Files Tab — uses a QStackedWidget for inline file viewing
        self.file_stack = QStackedWidget()

        # Page 0: File Tree
        self.file_tree = QTreeView()
        self.file_model = QStandardItemModel()
        self.file_model.setHorizontalHeaderLabels(["Filename"])
        self.file_tree.setModel(self.file_model)
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.file_tree.doubleClicked.connect(self.on_file_double_clicked)
        self.file_stack.addWidget(self.file_tree)  # index 0

        # Page 1: Inline File Viewer (built on-demand, placeholder widget)
        self.file_viewer_page = QWidget()
        self.file_viewer_layout = QVBoxLayout(self.file_viewer_page)
        self.file_viewer_layout.setContentsMargins(0, 0, 0, 0)
        self.file_stack.addWidget(self.file_viewer_page)  # index 1

        self.tabs.addTab(self.file_stack, "Archive Contents")

        # Settings Tab
        self.settings_tab = QWidget()
        settings_layout = QVBoxLayout(self.settings_tab)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lbl_opacity = QLabel("Window Opacity: 100%")
        self.lbl_opacity.setObjectName("headerLabel")

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(20, 100)  # Min 20% opacity, Max 100%
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self.on_opacity_changed)

        self.chk_blur = QCheckBox("Enable Window Blur (Requires Restart/Supported OS)")
        self.chk_blur.setObjectName("infoLabel")
        self.chk_blur.stateChanged.connect(self.on_blur_toggled)

        settings_layout.addWidget(self.create_header_label("Appearance"))
        settings_layout.addWidget(self.chk_blur)
        settings_layout.addWidget(self.lbl_opacity)
        settings_layout.addWidget(self.slider_opacity)

        btn_save_settings = QPushButton("Save Settings")
        btn_save_settings.clicked.connect(self.save_settings)
        btn_save_settings.pressed.connect(self.play_click_sound)
        settings_layout.addWidget(btn_save_settings)

        self.tabs.addTab(self.settings_tab, "Settings")

        splitter.addWidget(self.tabs)
        splitter.setSizes([300, 700])

        main_layout.addWidget(
            splitter, 1
        )  # '1' stretch factor allows this to fill the rest of the window screen

        # Keep track of individual jar files and folders loaded
        self.history_files = set()
        self.history_folders = set()

        self.load_settings()

    def create_header_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("headerLabel")
        return lbl

    def play_click_sound(self):
        self.click_sound.play()

    def check_mc_compatibility(self):
        """Cross-checks all loaded mods to find a common Minecraft version and flags incompatible ones."""
        # 1. Collect all explicit MC versions and loaders
        mc_versions_found = []
        loaders_found = set()

        for jar in self.loaded_jars:
            jar.is_mc_compatible = True  # Reset

            # Track loaders from mods with an explicit known version or metadata
            if jar.mod_loader and jar.mod_loader not in (
                "Unknown",
                "Unknown Archive",
                "Vanilla/Library JAR (No Mod Metadata)",
            ):
                for spl in jar.mod_loader.split("/"):
                    loaders_found.add(spl.strip())

            if jar.mc_version and jar.mc_version != "Unknown":
                # Basic cleanup of versions like "1.20.1", ">=1.19", "~1.20", "1.19.x"
                ver_str = str(jar.mc_version)
                # Split arrays/ranges if any
                parts = re.split(r"[,|\||\s]+", ver_str)
                for part in parts:
                    part = part.strip(" []()")
                    if not part:
                        continue
                    try:
                        # Convert 1.19.x to ~1.19.0 for semantic version checking
                        if ".x" in part.lower():
                            part = part.lower().replace(".x", ".0")
                            part = f"~{part}"

                        spec = semantic_version.NpmSpec(part)
                        mc_versions_found.append(spec)
                    except:
                        pass  # Ignore unparseable versions

        # 2. Find the most frequently required explicit MC version and Loader
        from collections import Counter

        mc_counts = Counter()
        loader_counts = Counter()

        for jar in self.loaded_jars:
            if jar.mc_version and jar.mc_version != "Unknown":
                # Split comma/pipe-separated version lists into individual versions
                # so "1.9.4,1.10,1.10.2" contributes to each version's count separately
                raw_ver = str(jar.mc_version)
                ver_parts = re.split(r"[,|\|]+", raw_ver)
                for vp in ver_parts:
                    vp = vp.strip(" []()")
                    if vp:
                        mc_counts[vp] += 1

            if jar.mod_loader and jar.mod_loader not in (
                "Unknown",
                "Unknown Archive",
                "Vanilla/Library JAR (No Mod Metadata)",
            ):
                for spl in jar.mod_loader.split("/"):
                    loader_counts[spl.strip()] += 1

        # Determine base MC version by highest count
        base_mc_ver = None
        if mc_counts:
            most_frequent_mc = mc_counts.most_common(1)[0][0]
            # Try to parse it cleanly for compatibility checking
            ver_clean = re.split(r"[,|\||\s]+", most_frequent_mc)[0].strip(" []()")
            ver_clean = ver_clean.replace(".x", ".0")
            if ver_clean.startswith((">=", "~", "^")):
                ver_clean = ver_clean.lstrip(">=").lstrip("~").lstrip("^")
            try:
                base_mc_ver = semantic_version.Version.coerce(ver_clean)
            except:
                self.current_base_mc = (
                    most_frequent_mc  # Fallback to raw string if coerce fails
                )

        if base_mc_ver:
            self.current_base_mc = base_mc_ver
        else:
            self.current_base_mc = None

        # Determine base Loader by highest count
        if loader_counts:
            self.current_base_loader = loader_counts.most_common(1)[0][0]
        else:
            self.current_base_loader = "Unknown"

        if base_mc_ver:
            # Flag mods that explicitly do not support this base_mc_ver
            for jar in self.loaded_jars:
                if jar.mc_version and jar.mc_version != "Unknown":
                    ver_str = str(jar.mc_version)
                    try:
                        # Use NpmSpec for loose matching logic (supports ^, ~, >=, etc.)
                        # Fabric uses NPM style ranges, Forge uses Maven style (harder to parse cleanly with semantic_version alone, but we try)
                        ver_str_clean = ver_str.replace(".x", ".0")

                        # Simple maven range conversion to npm for basic checks: [1.19, 1.20) -> >=1.19.0 <1.20.0
                        if "[" in ver_str_clean or "(" in ver_str_clean:
                            # Very basic maven range parsing fallback
                            if base_mc_ver.major != 1:
                                continue  # Give up if not MC formatting
                        else:
                            spec = semantic_version.NpmSpec(
                                ver_str_clean.replace(",", " || ")
                            )
                            if base_mc_ver not in spec:
                                jar.is_mc_compatible = False
                    except Exception as e:
                        print(
                            f"Could not check compatibility for {jar.file_name} against {base_mc_ver}: {e}"
                        )

    def update_list_and_filter(self):
        self.update_list()

    def update_global_status_ui(self):
        # Update Top Global Status Label
        mc_ver_text = (
            str(self.current_base_mc)
            if hasattr(self, "current_base_mc") and self.current_base_mc
            else "Unknown/Mixed"
        )
        base_loader_text = (
            str(self.current_base_loader)
            if hasattr(self, "current_base_loader") and self.current_base_loader
            else "Unknown"
        )

        status_parts = []
        if hasattr(self, "current_instance_mc") and getattr(
            self, "current_instance_mc", None
        ):
            status_parts.append(
                f"<b>Instance MC Version:</b> <span style='color: #55FFFF;'>{self.current_instance_mc}</span>"
            )
            status_parts.append(
                f"<b>Instance Loader:</b> <span style='color: #FF55FF;'>{self.current_instance_loader}</span>"
            )
            status_parts.append(f"<b>|</b>")

        status_parts.append(
            f"<b>Base MC Version:</b> <span style='color: #55FF55;'>{mc_ver_text}</span>"
        )
        status_parts.append(
            f"<b>Majority Loader:</b> <span style='color: #FFAA00;'>{base_loader_text}</span>"
        )

        total_found = len(self.loaded_jars)
        status_parts.append(f"|  <b>Total Tracked Items:</b> {total_found}")

        if self.current_loaded_type == "instance":
            status_parts.insert(0, f"<b>[INSTANCE]</b>")

        self.lbl_global_status.setText("   ".join(status_parts))

    def on_worker_progress(self, val, txt):
        if val > 0:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(val)
        self.lbl_global_status.setText(f"<span style='color: #FFFF55;'>{txt}</span>")

    def on_worker_jar_loaded(self, jar_data: JarData):
        self.loaded_jars.append(jar_data)
        self.check_mc_compatibility()
        self.update_list()
        self.update_global_status_ui()

    def on_worker_finished(self, results, mc_ver, loader):
        self.progress_bar.setVisible(False)
        self.lbl_global_status.setText("Processing finished.")

        if self.current_loaded_type == "instance":
            self.current_instance_mc = mc_ver
            self.current_instance_loader = loader

        self.check_mc_compatibility()
        self.update_list()
        self.update_global_status_ui()

    def update_list(self):
        self.jar_list.clear()

        # Check compatibility first
        self.check_mc_compatibility()

        # Build reverse dependency map
        self.reverse_deps = defaultdict(list)
        for jar in self.loaded_jars:
            for dep in jar.dependencies or []:
                dep_id = dep["id"]
                # Don't track generic system deps like minecraft/java
                if dep_id.lower() not in ("minecraft", "java", "fabricloader"):
                    self.reverse_deps[dep_id].append(jar)

        # Update dependency filter combo
        current_dep_filter_id = self.dep_filter_combo.currentData()
        self.dep_filter_combo.blockSignals(True)
        self.dep_filter_combo.clear()
        self.dep_filter_combo.addItem("All Mods (No Library Filter)", None)

        # Only show mods that HAVE dependents as "Libraries/Main Mods"
        main_mods = []
        for mod_id, dependents in self.reverse_deps.items():
            # Try to find the display name of this library mod among loaded jars
            lib_mod = next((j for j in self.loaded_jars if j.mod_id == mod_id), None)
            display_name = lib_mod.mod_name if lib_mod else mod_id
            main_mods.append((display_name, mod_id, len(dependents)))

        # Sort main mods by number of dependents descending
        main_mods.sort(key=lambda x: x[2], reverse=True)
        for name, mid, count in main_mods:
            self.dep_filter_combo.addItem(f"{name} ({count} deps)", mid)

        # Restore selection by Mod ID
        idx = -1
        for i in range(self.dep_filter_combo.count()):
            if self.dep_filter_combo.itemData(i) == current_dep_filter_id:
                idx = i
                break
        if idx >= 0:
            self.dep_filter_combo.setCurrentIndex(idx)
        else:
            self.dep_filter_combo.setCurrentIndex(0)
        self.dep_filter_combo.blockSignals(False)

        # Determine sorting preference BEFORE grouping
        sort_mode = self.sort_combo.currentText()
        if sort_mode == "Sort by Mod Name":
            self.loaded_jars.sort(key=lambda x: str(x.mod_name).lower())
        elif sort_mode == "Sort by File Name":
            self.loaded_jars.sort(key=lambda x: str(x.file_name).lower())
        elif sort_mode == "Sort by Author":
            self.loaded_jars.sort(
                key=lambda x: str(x.authors[0]).lower() if x.authors else "zzzz"
            )
        elif sort_mode == "Sort by Loader":
            self.loaded_jars.sort(key=lambda x: str(x.mod_loader).lower())
        elif sort_mode == "Sort by Size":
            self.loaded_jars.sort(key=lambda x: x.file_size_bytes, reverse=True)
        elif sort_mode == "Sort by Dependents":
            self.loaded_jars.sort(
                key=lambda x: len(self.reverse_deps.get(x.mod_id, [])), reverse=True
            )
        elif sort_mode == "Sort by Version":

            def version_sort_key(jar):
                v_str = str(jar.version).lower()
                # 1. First, not MC mods
                if not jar.is_minecraft_related:
                    return (5, v_str)
                # 2. Then, mods with version but no numbers
                is_unknown_ver = v_str in ("unknown", "unknown version", "")
                has_nums = any(c.isdigit() for c in v_str)
                if not is_unknown_ver and not has_nums:
                    return (4, v_str)
                # 3. Then, non compatible mods
                if not getattr(jar, "is_mc_compatible", True):
                    return (3, v_str)
                # 4. Then, mods which don't show MC version
                mc_v = str(jar.mc_version).lower() if jar.mc_version else ""
                if not mc_v or mc_v in ("unknown", "unknown version"):
                    return (2, v_str)
                # 5. Then, other mods
                return (1, v_str)

            self.loaded_jars.sort(key=version_sort_key, reverse=True)
        # Duplicate detection (compare versions)
        # Assuming higher alphabetic/numeric sorts later. Python handles semver poorly without extra libraries,
        # so we'll do basic sorting. Let's group by mod_id
        mod_versions = defaultdict(list)
        for i, jar in enumerate(self.loaded_jars):
            mod_versions[jar.mod_id].append(jar)

        for _id, jars in mod_versions.items():
            jars.sort(key=lambda x: x.version)

        # Group by category
        categories = defaultdict(list)

        # Apply filters
        search_text = self.search_box.text().lower()
        cat_filter = self.category_combo.currentText()
        dep_filter_id = self.dep_filter_combo.currentData()

        for jar in self.loaded_jars:
            # 1. Search Filter
            if (
                search_text
                and search_text not in str(jar.mod_name).lower()
                and search_text not in str(jar.file_name).lower()
                and search_text not in str(jar.mod_id).lower()
            ):
                continue

            # 2. Category Filter
            if cat_filter != "All Categories" and jar.category != cat_filter:
                continue

            # 3. Dependency Filter
            if dep_filter_id:
                # Show mods that depend on dep_filter_id
                dependency_ids = [d["id"] for d in jar.dependencies or []]
                if dep_filter_id not in dependency_ids:
                    continue

            categories[jar.category].append(jar)

        # Update category_combo dynamically based on loaded content
        current_cat = self.category_combo.currentText()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        unique_cats = set(jar.category for jar in self.loaded_jars)
        all_cats = ["All Categories"] + sorted(list(unique_cats))
        self.category_combo.addItems(all_cats)

        idx = self.category_combo.findText(current_cat)
        if idx >= 0:
            self.category_combo.setCurrentIndex(idx)
        else:
            self.category_combo.setCurrentIndex(0)
        self.category_combo.blockSignals(False)

        # Display each category with Mods prioritized
        all_cats_found = list(categories.keys())
        priority = {"Mods": 0, "Resourcepacks": 1, "Shaderpacks": 2}
        sorted_categories = sorted(
            all_cats_found,
            key=lambda x: (
                priority.get(x.split(" - ")[0], 99)
                if " - " in x
                else priority.get(x, 10)
            ),
        )

        is_hierarchy = (
            hasattr(self, "btn_toggle_hierarchy")
            and self.btn_toggle_hierarchy.isChecked()
        )

        for cat_name in sorted_categories:
            header_item = QListWidgetItem()
            header_item.setData(Qt.ItemDataRole.UserRole, "HEADER")
            header_item.setText(
                f"<div align='center' style='color: #55FFFF; font-size: 14pt; font-weight: bold; padding: 5px; background-color: #333;'>--- {cat_name} ---</div>"
            )
            self.jar_list.addItem(header_item)

            cat_jars = categories[cat_name]
            # If hierarchy is enabled, we need to order them differently
            display_queue = []  # list of (JarData, level)

            if is_hierarchy:
                shown_this_cat = set()

                # 1. Identify "Libraries" in this category (any mod that HAS dependents in this category)
                cat_mod_ids = {j.mod_id for j in cat_jars}
                libs_in_cat = []
                for j in cat_jars:
                    dependents_in_cat = [
                        d for d in self.reverse_deps.get(j.mod_id, []) if d in cat_jars
                    ]
                    if dependents_in_cat:
                        libs_in_cat.append((j, dependents_in_cat))

                # Sort libs by number of dependents in this category
                libs_in_cat.sort(key=lambda x: len(x[1]), reverse=True)

                for lib_jar, dependents in libs_in_cat:
                    if lib_jar.file_path not in shown_this_cat:
                        display_queue.append((lib_jar, 0))
                        shown_this_cat.add(lib_jar.file_path)
                        # Add dependents immediately after
                        for dep in sorted(dependents, key=lambda x: x.mod_name.lower()):
                            if dep.file_path not in shown_this_cat:
                                display_queue.append((dep, 1))
                                shown_this_cat.add(dep.file_path)

                # 2. Add remaining standalone jars
                for j in cat_jars:
                    if j.file_path not in shown_this_cat:
                        display_queue.append((j, 0))
                        shown_this_cat.add(j.file_path)
            else:
                for j in cat_jars:
                    display_queue.append((j, 0))

            for jar, level in display_queue:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, jar)

                # Load Icon
                if jar.icon_bytes:
                    image = QImage.fromData(jar.icon_bytes)
                    pixmap = QPixmap.fromImage(image)
                else:
                    icon_path = os.path.join(
                        os.path.dirname(__file__), "assets", "ui_icon.png"
                    )
                    pixmap = QPixmap(icon_path)

                if not pixmap.isNull():
                    pixmap = pixmap.scaled(
                        32,
                        32,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation,
                    )

                    if level > 0:
                        indent_px = level * 30
                        new_pixmap = QPixmap(
                            pixmap.width() + indent_px, pixmap.height()
                        )
                        new_pixmap.fill(Qt.GlobalColor.transparent)
                        p = QPainter(new_pixmap)
                        p.drawPixmap(indent_px, 0, pixmap)
                        p.end()
                        pixmap = new_pixmap

                    icon = QIcon(pixmap)
                    # Keep original color even when selected
                    icon.addPixmap(pixmap, QIcon.Mode.Normal, QIcon.State.On)
                    icon.addPixmap(pixmap, QIcon.Mode.Selected, QIcon.State.On)
                    item.setIcon(icon)

                # If there's multiple of this mod_id, and this isn't the highest version, paint it red
                is_old_version = False
                if len(mod_versions[jar.mod_id]) > 1 and jar.mod_id not in (
                    "unknown",
                    jar.file_name,
                ):
                    if jar != mod_versions[jar.mod_id][-1]:
                        is_old_version = True

                # Base text format using HTML for colors/sizes
                title = f"<span style='font-size: 11pt;'>{jar.file_name}</span>"

                mc_color = "#55FF55" if jar.is_mc_compatible else "red"
                mc_info = (
                    f"MC {jar.mc_version} | "
                    if jar.mc_version and jar.mc_version != "Unknown"
                    else ""
                )

                subtitle = f"<span style='font-size: 9pt; color: {mc_color};'>{mc_info}</span><span style='font-size: 9pt; color: #FFAA00;'>v{jar.version}</span> <span style='font-size: 9pt; color: #AAAAAA;'>- {jar.file_size_mb:.2f} MB</span>"

                if not jar.is_minecraft_related:
                    item.setText(
                        f"{title} <span style='color: gray;'>[NOT MC]</span><br>{subtitle}"
                    )
                elif not jar.is_mc_compatible:
                    item.setText(
                        f"{title} <span style='color: red;'>[MC INCOMPATIBLE]</span><br>{subtitle}"
                    )
                elif is_old_version:
                    item.setText(
                        f"{title} <span style='color: red;'>[OLD VERSION]</span><br>{subtitle}"
                    )
                elif jar.version in ("Unknown", "Unknown Version"):
                    item.setText(
                        f"{title} <span style='color: #FFD700;'>[NO VERSION]</span><br>{subtitle}"
                    )
                else:
                    item.setText(f"{title}<br>{subtitle}")

                # Apply Indentation / Branch marker
                if level > 0:
                    # Use a nice Unicode branch symbol - each level gets more &nbsp;
                    indent = "&nbsp;" * (level * 8)
                    branch = f"{indent}└─&nbsp;"
                    curr_text = item.text()
                    item.setText(f"{branch}{curr_text}")

                self.jar_list.addItem(item)

        # Update Top Global Status Label
        mc_ver_text = (
            str(self.current_base_mc)
            if hasattr(self, "current_base_mc") and self.current_base_mc
            else "Unknown/Mixed"
        )
        base_loader_text = (
            str(self.current_base_loader)
            if hasattr(self, "current_base_loader") and self.current_base_loader
            else "Unknown"
        )

        status_parts = []
        if hasattr(self, "current_instance_mc") and getattr(
            self, "current_instance_mc", None
        ):
            status_parts.append(
                f"<b>Instance MC Version:</b> <span style='color: #55FFFF;'>{self.current_instance_mc}</span>"
            )
        else:
            status_parts.append(
                f"<b>Focused MC Version:</b> <span style='color: #55FF55;'>{mc_ver_text}</span>"
            )

        if hasattr(self, "current_instance_loader") and getattr(
            self, "current_instance_loader", None
        ):
            status_parts.append(
                f"<b>Instance Loader:</b> <span style='color: #FF55FF;'>{self.current_instance_loader}</span>"
            )
        else:
            status_parts.append(
                f"<b>Focused Loader:</b> <span style='color: #FF55FF;'>{base_loader_text}</span>"
            )

        if (
            self.current_loaded_type in ("instance", "folder")
            and self.current_loaded_path
        ):
            folder_name = os.path.basename(self.current_loaded_path.rstrip("/\\"))
            type_label = (
                "Instance" if self.current_loaded_type == "instance" else "Folder"
            )
            status_parts.append(f"<b>{type_label}:</b> {folder_name}")

        stats = []
        if "Mods" in categories:
            stats.append(f"{len(categories['Mods'])} Mods")
        if "Resourcepacks" in categories:
            stats.append(f"{len(categories['Resourcepacks'])} Resourcepacks")
        if "Shaderpacks" in categories:
            stats.append(f"{len(categories['Shaderpacks'])} Shaderpacks")

        stats_line = ""
        if stats:
            stats_line = "<b>Loaded:</b> " + ", ".join(stats)
        elif not self.loaded_jars:
            stats_line = "No items loaded."

        # Combine the main parts with a pipe, then put the stats line below it
        main_line = " | ".join(status_parts)
        if stats_line:
            self.lbl_global_status.setText(f"{main_line}<br>{stats_line}")
        else:
            self.lbl_global_status.setText(main_line)

        # Filter logic is already handled inside update_list loops
        pass

    def filter_list(self, text: str):
        # Center list update on search change
        self.update_list()

    def load_single_jar(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Minecraft JAR", "", "Java Archive (*.jar)"
        )
        if file_path:
            self.clear_list()
            self.current_loaded_type = "file"
            self.current_loaded_path = file_path

            # Update history
            self.history_files.add(file_path)
            self.save_settings()

            self.worker = JarLoaderWorker(
                mode="file",
                paths=[file_path],
                enable_deep_search=self.chk_deep_search.isChecked(),
            )
            self.worker.progress.connect(self.on_worker_progress)
            self.worker.jar_loaded.connect(self.on_worker_jar_loaded)
            self.worker.finished_loading.connect(self.on_worker_finished)
            self.worker.start()

    def load_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Folder containing JARs"
        )
        if folder_path:
            self.clear_list()
            self.current_loaded_type = "folder"
            self.current_loaded_path = folder_path

            # Update history
            self.history_folders.add(folder_path)
            self.save_settings()

            self.worker = JarLoaderWorker(
                mode="folder",
                paths=[folder_path],
                enable_deep_search=self.chk_deep_search.isChecked(),
            )
            self.worker.progress.connect(self.on_worker_progress)
            self.worker.jar_loaded.connect(self.on_worker_jar_loaded)
            self.worker.finished_loading.connect(self.on_worker_finished)
            self.worker.start()

    def load_instance_dir(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Minecraft Instance Directory"
        )
        if folder_path:
            # Clear previous loading items
            self.clear_list()

            self.current_loaded_type = "instance"
            self.current_loaded_path = folder_path

            # Update history
            if not hasattr(self, "history_instances"):
                self.history_instances = set()
            self.history_instances.add(folder_path)
            self.save_settings()

            self.worker = JarLoaderWorker(
                mode="instance",
                paths=[folder_path],
                enable_deep_search=self.chk_deep_search.isChecked(),
            )
            self.worker.progress.connect(self.on_worker_progress)
            self.worker.jar_loaded.connect(self.on_worker_jar_loaded)
            self.worker.finished_loading.connect(self.on_worker_finished)
            self.worker.start()

    def clear_list(self):
        self.loaded_jars.clear()
        self.current_loaded_type = None
        self.current_loaded_path = None
        self.current_instance_mc = None
        self.current_instance_loader = None
        self.current_base_mc = None
        self.current_base_loader = None

        # Clear history
        self.history_files.clear()
        self.history_folders.clear()
        if hasattr(self, "history_instances"):
            self.history_instances.clear()
        self.save_settings()

        self.update_list()
        self.clear_details()

    def delete_selected(self):
        selected = self.jar_list.selectedItems()
        if not selected:
            return

        data = selected[0].data(Qt.ItemDataRole.UserRole)
        if data == "HEADER":
            return
        jar: JarData = data

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete {jar.file_name} from the file system?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # Attempt to delete file from OS
        try:
            os.remove(jar.file_path)
        except Exception as e:
            print(f"Failed to delete {jar.file_path}: {e}")

        if jar in self.loaded_jars:
            self.loaded_jars.remove(jar)

        # Also sync with history if it was explicitly loaded as a file
        if jar.file_path in self.history_files:
            self.history_files.remove(jar.file_path)
            self.save_settings()

        self.update_list()
        self.clear_details()

    def clear_details(self):
        self.lbl_title.setText("Select a JAR")
        self.lbl_file_name.setText("File: ")
        self.lbl_loader.setText("Loader: ")
        self.lbl_version.setText("Version: ")
        self.lbl_mc_version.setText("MC Version: ")
        self.lbl_java.setText("Java Version: ")
        self.lbl_authors.setText("Authors: ")
        self.lbl_parsed_from.setText("Parsed From: None")
        self.lbl_depends.setText("Dependencies: None")
        self.lbl_required_by.setText("Required By: None")
        self.lbl_desc.setText("Description: ")
        self.lbl_file_count.setText("Files: 0")
        self.lbl_icon.setPixmap(QPixmap())
        self.file_model.clear()
        # Reset file viewer back to tree if viewing a file
        if self.file_stack.currentIndex() == 1:
            self.go_back_from_file_view()

    def on_jar_selected(self):
        selected = self.jar_list.selectedItems()
        if not selected:
            return

        data = selected[0].data(Qt.ItemDataRole.UserRole)

        # Helper function for coloring labels
        def color_txt(label, val, color="#55FFFF"):
            return f"{label} <span style='color: {color};'>{val}</span>"

        if data == "HEADER":
            header_text = selected[0].text()
            import re

            m = re.search(r"--- (.*?) ---", header_text)
            cat_name = m.group(1) if m else "Unknown Category"

            jars_in_cat = [j for j in self.loaded_jars if j.category == cat_name]
            total_size_mb = sum(j.file_size_mb for j in jars_in_cat)
            mc_versions = sorted(
                list(
                    set(
                        j.mc_version
                        for j in jars_in_cat
                        if j.mc_version and j.mc_version != "Unknown"
                    )
                )
            )

            # Extract unique loaders specifically
            loader_set = set()
            for jar in jars_in_cat:
                if jar.mod_loader and jar.mod_loader not in (
                    "Unknown",
                    "Unknown Archive",
                    "Vanilla/Library JAR (No Mod Metadata)",
                ):
                    for subloader in jar.mod_loader.split("/"):
                        loader_set.add(subloader.strip())
            loaders = sorted(list(loader_set))

            self.lbl_title.setText(
                f"<span style='color: #FF55FF; font-size: 16px; font-weight: bold;'>Category: {cat_name}</span>"
            )
            self.lbl_file_name.setText(
                color_txt(
                    "Total Items:",
                    f"{len(jars_in_cat)} ({total_size_mb:.2f} MB)",
                    "#FFAA00",
                )
            )

            loader_str = ", ".join(loaders) if loaders else "N/A"
            self.lbl_loader.setText(color_txt("Loaders Found:", loader_str, "#55FF55"))
            self.lbl_version.setText(color_txt("Version:", "Select a Mod", "#AAAAAA"))

            mc_versions_set = set()
            for jar in jars_in_cat:
                if jar.mc_version and jar.mc_version != "Unknown":
                    # Clean version explicitly to avoid '1.10.2' and '[1.10.2]' counting as two distinct strings
                    clean_v = str(jar.mc_version).strip("[]() ")
                    mc_versions_set.add(clean_v)

            if mc_versions_set:
                # Sort versions basically
                sorted_mcs = sorted(list(mc_versions_set), reverse=True)
                # Join with commas, but if there's more than 5, truncate
                if len(sorted_mcs) > 5:
                    mcs_str = (
                        ", ".join(sorted_mcs[:5]) + f", and {len(sorted_mcs)-5} more..."
                    )
                else:
                    mcs_str = ", ".join(sorted_mcs)
                self.lbl_mc_version.setText(
                    color_txt("MC Versions Found:", mcs_str, "#55FFFF")
                )
            else:
                self.lbl_mc_version.setText(
                    color_txt("MC Versions:", "Select a Mod", "#AAAAAA")
                )

            self.lbl_java.setText(
                color_txt("Compiled with:", "Select a Mod", "#AAAAAA")
            )

            authors_count = len(set(a for j in jars_in_cat for a in j.authors))
            self.lbl_authors.setText(
                color_txt("Authors:", f"{authors_count} Unique Authors", "#AA00AA")
            )
            self.lbl_parsed_from.setText(
                "Parsed From:<br><span style='color: #AAAAAA;'>Select an individual item.</span>"
            )
            self.lbl_depends.setText(
                "Dependencies:<br><span style='color: #AAAAAA;'>Select an individual item to view dependencies.</span>"
            )
            self.lbl_required_by.setText(
                "Required By:<br><span style='color: #AAAAAA;'>Select an individual item to view exact requirements.</span>"
            )
            self.lbl_desc.setText(
                f"Description:<br><span style='color: #DDDDDD;'>Select a mod to view its description.</span>"
            )
            self.lbl_file_count.setText(
                "Files:<br><span style='color: #AAAAAA;'>Select an individual item.</span>"
            )

            icon_name = "ui_icon.png"
            if "Resourcepack" in cat_name:
                icon_name = "ui_icon.png"  # Placeholder or themed if available
            elif "Shaderpack" in cat_name:
                icon_name = "ui_icon.png"

            icon_path = os.path.join(os.path.dirname(__file__), "assets", icon_name)
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    64,
                    64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
                self.lbl_icon.setPixmap(pixmap)

            # Additional category-wide stats in description
            stats_info = f"This category contains {len(jars_in_cat)} items totaling {total_size_mb:.2f} MB.<br>"
            if mc_versions_set:
                stats_info += f"Compatible versions: {', '.join(sorted_mcs[:10])}"
                if len(sorted_mcs) > 10:
                    stats_info += "..."

            self.lbl_desc.setText(
                f"Category Info:<br><span style='color: #DDDDDD;'>{stats_info}</span>"
            )
            return

        jar: JarData = data

        # Check if it's an old version
        is_old_version = False
        mod_versions = defaultdict(list)
        for j in self.loaded_jars:
            mod_versions[j.mod_id].append(j)

        if len(mod_versions[jar.mod_id]) > 1 and jar.mod_id not in (
            "unknown",
            jar.file_name,
        ):
            mod_versions[jar.mod_id].sort(key=lambda x: x.version)
            if jar != mod_versions[jar.mod_id][-1]:
                is_old_version = True
                highest_ver = mod_versions[jar.mod_id][-1].version

        # Update Meta
        if is_old_version:
            self.lbl_title.setText(
                f"<span style='color: #FF55FF; font-size: 16px; font-weight: bold;'>{jar.mod_name}</span> <span style='color: red; font-weight: bold;'>(OLDER VERSION - Latest: {highest_ver})</span>"
            )
        else:
            self.lbl_title.setText(
                f"<span style='color: #FF55FF; font-size: 16px; font-weight: bold;'>{jar.mod_name}</span>"
            )

        self.lbl_file_name.setText(
            color_txt(
                "File Path:", f"{jar.file_path} ({jar.file_size_mb:.2f} MB)", "#FFAA00"
            )
        )

        # Color loaders differently based on their names
        loader_text = jar.mod_loader
        if loader_text:
            loader_text = loader_text.replace(
                "Fabric",
                "<span style='color: #F8CB43; font-weight: bold;'>Fabric</span>",
            )
            loader_text = loader_text.replace(
                "Quilt", "<span style='color: #8D51D5; font-weight: bold;'>Quilt</span>"
            )
            loader_text = loader_text.replace(
                "Forge (Legacy)",
                "<span style='color: #DF803E; font-weight: bold;'>Forge (Legacy)</span>",
            )
            loader_text = loader_text.replace(
                "NeoForge",
                "<span style='color: #E25D1D; font-weight: bold;'>NeoForge</span>",
            )
            # Only replace standalone Forge, not the NeoForge substring natively
            import re

            loader_text = re.sub(
                r"(?<!Neo)Forge",
                "<span style='color: #DF803E; font-weight: bold;'>Forge</span>",
                loader_text,
            )
        self.lbl_loader.setText(f"Loader: {loader_text}")

        self.lbl_version.setText(color_txt("Version:", jar.version, "#FFFF55"))
        mc_color = "#55FF55" if jar.is_mc_compatible else "red"
        self.lbl_mc_version.setText(color_txt("MC Version:", jar.mc_version, mc_color))
        self.lbl_java.setText(color_txt("Compiled with:", jar.java_version, "#FF5555"))
        self.lbl_authors.setText(
            color_txt(
                "Authors:",
                ", ".join(jar.authors) if jar.authors else "Unknown",
                "#AA00AA",
            )
        )

        if jar.parsed_from:
            parsed_links = []
            for parsed_file in jar.parsed_from:
                parsed_links.append(
                    f'<a href="{parsed_file}" style="color: #55FFFF; font-weight: bold;">{parsed_file}</a>'
                )
            self.lbl_parsed_from.setText(f"Parsed From:<br>{', '.join(parsed_links)}")
        else:
            self.lbl_parsed_from.setText(
                f"Parsed From:<br><span style='color: #AAAAAA;'>None</span>"
            )

        # Pre-calculate installed mod IDs and file names for dependency checking
        installed_ids = {j.mod_id for j in self.loaded_jars}
        installed_files = {j.file_name for j in self.loaded_jars}

        # Link dependencies
        # unique_deps is now list of dicts: {"id": str, "optional": bool}
        unique_deps_map = {}
        for dep in jar.dependencies or []:
            dep_id = dep["id"]
            if dep_id not in unique_deps_map or (
                unique_deps_map[dep_id]["optional"] and not dep["optional"]
            ):
                unique_deps_map[dep_id] = dep

        unique_deps = list(unique_deps_map.values())

        # Sort dependencies: "minecraft" and "java" (or similar) first
        def dep_sort_key(d_obj):
            d = d_obj["id"]
            dl = d.lower()
            if dl in ("minecraft", "java", "fabricloader"):
                return (0, dl)
            return (1, dl)

        unique_deps.sort(key=dep_sort_key)

        if unique_deps:
            links = []
            for dep_obj in unique_deps:
                dep = dep_obj["id"]
                is_optional = dep_obj.get("optional", False)
                opt_label = " (optional)" if is_optional else ""

                if dep.lower() in ("minecraft", "java", "fabricloader"):
                    # Default/Base dependencies treated as system/base (Cyan), no underline
                    links.append(
                        f'<a href="{dep}" style="color: #55FFFF; font-weight: bold; text-decoration: none;">{dep}</a>{opt_label}'
                    )
                elif dep in installed_ids or dep in installed_files:
                    # Installed normal dependencies (Green)
                    links.append(
                        f'<a href="{dep}" style="color: #55FF55; font-weight: bold;">{dep}</a>{opt_label}'
                    )
                else:
                    # Missing dependency
                    links.append(
                        f'<span style="color: red; font-weight: bold;" title="Not Installed">{dep}</span>{opt_label}'
                    )
            self.lbl_depends.setText(f"Dependencies:<br>{', '.join(links)}")
        else:
            self.lbl_depends.setText(
                "Dependencies:<br><span style='color: #AAAAAA;'>None</span>"
            )

        # Find other jars that depend on this one
        unique_dependents = {}
        for other_jar in self.loaded_jars:
            # Check if current jar.mod_id is in other_jar's dependencies list of dicts
            is_dependent = False
            for dep_obj in other_jar.dependencies:
                if (
                    jar.mod_id != "unknown"
                    and jar.mod_id != jar.file_name
                    and dep_obj["id"] == jar.mod_id
                ):
                    is_dependent = True
                    break

            if is_dependent:
                link_target = (
                    other_jar.mod_id
                    if other_jar.mod_id not in ("unknown", other_jar.file_name)
                    else other_jar.file_name
                )
                if link_target not in unique_dependents:
                    unique_dependents[link_target] = other_jar.mod_name

        if unique_dependents:
            links = []
            for link_target, display_name in unique_dependents.items():
                links.append(
                    f'<a href="{link_target}" style="color: #55FF55; font-weight: bold;">{display_name}</a>'
                )
            self.lbl_required_by.setText(f"Required By:<br>{', '.join(links)}")
        else:
            self.lbl_required_by.setText(
                "Required By:<br><span style='color: #AAAAAA;'>None</span>"
            )

        desc = jar.description
        if (
            not desc
            or not desc.strip()
            or desc.strip() in ("No description provided.", "No description.")
        ):
            self.lbl_desc.setText(
                "Description:<br><span style='color: #777777; font-style: italic;'>(Empty description)</span>"
            )
        else:
            self.lbl_desc.setText(
                f"Description:<br><span style='color: #DDDDDD;'>{desc}</span>"
            )
        self.lbl_file_count.setText(
            color_txt("Total Files Inside:", jar.total_files, "#55FFFF")
        )

        # Load Icon
        if jar.icon_bytes:
            image = QImage.fromData(jar.icon_bytes)
            pixmap = QPixmap.fromImage(image)
        else:
            # Fallback to the default app icon
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "ui_icon.png")
            pixmap = QPixmap(icon_path)

        if not pixmap.isNull():
            # Scale it blocky (fast transformation keeps hard edges)
            pixmap = pixmap.scaled(
                64,
                64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.lbl_icon.setPixmap(pixmap)
        else:
            self.lbl_icon.setText("No\nIcon")

        # Update File Tree
        self.populate_file_tree(jar.file_list)

    def populate_file_tree(self, file_list: list[str]):
        self.file_model.clear()
        root = self.file_model.invisibleRootItem()

        # A simple tree builder based on path separation
        nodes = {"": root}

        for file_path in sorted(file_list):
            parts = file_path.strip("/").split("/")
            current_path = ""

            for i, part in enumerate(parts):
                parent_path = current_path
                current_path = f"{current_path}/{part}" if current_path else part

                if current_path not in nodes:
                    item = QStandardItem(part)
                    item.setEditable(False)
                    item.setData(current_path, Qt.ItemDataRole.UserRole)
                    parent_item = nodes.get(parent_path)
                    if isinstance(parent_item, QStandardItem):
                        parent_item.appendRow(item)
                    elif parent_item:
                        parent_item.appendRow(item)  # type: ignore
                    nodes[current_path] = item

        self.file_tree.expandToDepth(0)  # Expand root folders

    def on_file_double_clicked(self, index):
        item = self.file_model.itemFromIndex(index)
        if not item:
            return

        internal_path = item.data(Qt.ItemDataRole.UserRole)
        # Verify it's not a directory node
        if not internal_path or item.hasChildren():
            return

        self.open_parsed_file(internal_path)

    def go_back_from_file_view(self):
        """Switch back from the inline file viewer to the file tree."""
        self.file_stack.setCurrentIndex(0)
        # Update the tab label back
        tab_idx = self.tabs.indexOf(self.file_stack)
        if tab_idx >= 0:
            self.tabs.setTabText(tab_idx, "Archive Contents")

    def keyPressEvent(self, event):
        """Handle backspace to go back from file viewer."""
        if event.key() == Qt.Key.Key_Backspace and self.file_stack.currentIndex() == 1:
            self.go_back_from_file_view()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse back button (XButton1) to go back from file viewer."""
        if (
            event.button() == Qt.MouseButton.BackButton
            and self.file_stack.currentIndex() == 1
        ):
            self.go_back_from_file_view()
            return
        super().mousePressEvent(event)

    def open_parsed_file(self, internal_path: str):
        selected = self.jar_list.selectedItems()
        if not selected:
            return
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        # Ensure it's not a category header
        if data == "HEADER" or not hasattr(data, "file_path") or not data.file_path:
            return

        jar: JarData = data

        import zipfile
        import tempfile
        import subprocess

        try:
            # Strip '[Decompiled] ' prefix if it exists to retrieve the raw path
            if internal_path.startswith("[Decompiled] "):
                internal_path = internal_path.replace("[Decompiled] ", "").strip()

            is_image = internal_path.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
            )
            is_class = internal_path.lower().endswith(".class")

            with zipfile.ZipFile(jar.file_path, "r") as zf:
                try:
                    content_bytes = zf.read(internal_path)
                except KeyError:
                    QMessageBox.critical(
                        self,
                        "Extraction Error",
                        f"File not found in archive: {internal_path}",
                    )
                    return

            # Clear previous viewer content
            while self.file_viewer_layout.count():
                child = self.file_viewer_layout.takeAt(0)
                w = child.widget() if child else None
                if w:
                    w.deleteLater()

            # Top bar with back button and path info
            top_bar = QWidget()
            top_bar_layout = QHBoxLayout(top_bar)
            top_bar_layout.setContentsMargins(4, 4, 4, 4)

            btn_back = QPushButton("◀ Back")
            btn_back.setFixedWidth(80)
            btn_back.setStyleSheet("font-weight: bold; font-size: 11px;")
            btn_back.clicked.connect(self.go_back_from_file_view)
            btn_back.pressed.connect(self.play_click_sound)
            top_bar_layout.addWidget(btn_back)

            lbl = QLabel(
                f"<b>Path:</b> {internal_path} inside <b>{os.path.basename(jar.file_path)}</b>"
            )
            lbl.setStyleSheet("color: #DDDDDD; font-size: 11px; padding-left: 6px;")
            lbl.setWordWrap(True)
            top_bar_layout.addWidget(lbl, 1)

            self.file_viewer_layout.addWidget(top_bar)

            if is_image:
                image_lbl = QLabel()
                image_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

                img = QImage.fromData(content_bytes)
                pixmap = QPixmap.fromImage(img)

                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(
                        760,
                        540,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation,
                    )
                    image_lbl.setPixmap(scaled_pixmap)
                else:
                    image_lbl.setText("< Could not decode image data >")
                self.file_viewer_layout.addWidget(image_lbl)

            elif is_class:
                cfr_path = os.path.join(os.path.dirname(__file__), "assets", "cfr.jar")
                is_valid = False
                text = ""
                if not os.path.exists(cfr_path):
                    text = "< Error: CFR decompiler not found in assets folder >"
                else:
                    with tempfile.NamedTemporaryFile(
                        suffix=".class", delete=False
                    ) as tmp:
                        tmp.write(content_bytes)
                        tmp_path = tmp.name
                    try:
                        result = subprocess.run(
                            ["java", "-jar", cfr_path, tmp_path],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        text = result.stdout if result.stdout else result.stderr
                        is_valid = True
                    except Exception as e:
                        text = f"< Error running CFR decompiler: {e} >"
                    finally:
                        try:
                            os.remove(tmp_path)
                        except:
                            pass

                text_edit = QTextEdit()
                text_edit.setReadOnly(True)
                font = text_edit.font()
                font.setFamily("Consolas")
                font.setPointSize(10)
                text_edit.setFont(font)

                if not is_valid:
                    text_edit.setStyleSheet("color: red;")
                    text_edit.setPlainText(text)
                else:
                    text_edit.setPlainText(text)
                    self.highlighter = JavaHighlighter(text_edit.document())
                    text_edit.setStyleSheet(
                        "color: #A9B7C6; background-color: #2B2B2B;"
                    )
                self.file_viewer_layout.addWidget(text_edit)

            else:
                text = None
                is_valid = False
                # Check if binary
                if b"\x00" in content_bytes[:1024]:
                    text = "< Binary File / Unsupported Format >"
                else:
                    try:
                        text = content_bytes.decode("utf-8")
                        is_valid = True
                    except UnicodeDecodeError:
                        text = "< Unsupported or Unknown Text Encoding >"

                text_edit = QTextEdit()
                text_edit.setReadOnly(True)

                # Fixed width font
                font = text_edit.font()
                font.setFamily("Consolas")
                font.setPointSize(10)
                text_edit.setFont(font)

                if not is_valid:
                    text_edit.setStyleSheet("color: red;")
                    text_edit.setPlainText(text)
                else:
                    text_edit.setPlainText(text)
                    self.highlighter = ConfigHighlighter(text_edit.document())
                    text_edit.setStyleSheet(
                        "color: #A9B7C6; background-color: #2B2B2B;"
                    )

                self.file_viewer_layout.addWidget(text_edit)

            # Switch to the viewer page and update tab label
            self.file_stack.setCurrentIndex(1)
            tab_idx = self.tabs.indexOf(self.file_stack)
            if tab_idx >= 0:
                short_name = os.path.basename(internal_path)
                self.tabs.setTabText(tab_idx, f"Viewing: {short_name}")

            # Ensure the Archive Contents tab is active
            self.tabs.setCurrentWidget(self.file_stack)

        except Exception as e:
            QMessageBox.critical(
                self, "Extraction Error", f"Could not read internal file: {e}"
            )

    def on_opacity_changed(self, value: int):
        opacity_float = value / 100.0
        self.lbl_opacity.setText(f"Window Opacity: {value}%")

        # 1. Base Qt window opacity
        self.setWindowOpacity(opacity_float)

        # 2. Re-apply theme dynamically with CSS alpha channels
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, opacity=opacity_float)

    def on_blur_toggled(self, state):
        if state == Qt.CheckState.Checked.value:
            # Enable translucent background for OS compositor blur
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # The window needs to be repainted/re-shown for the flag to take full effect on some OS
        self.repaint()

    def jump_to_dependency(self, target_mod_id: str):
        """Called when a dependency hyperlink is clicked. Finds the mod and selects it."""
        matches = []
        for i in range(self.jar_list.count()):
            item = self.jar_list.item(i)
            if not item:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, str) or not data:
                continue  # Skip headers
            jar: JarData = data
            if jar.mod_id == target_mod_id or jar.file_name == target_mod_id:
                matches.append((i, jar))

        if matches:
            # Sort by version to get latest
            matches.sort(key=lambda x: x[1].version)
            self.jar_list.setCurrentRow(matches[-1][0])

    def save_settings(self):
        settings = {
            "opacity": self.slider_opacity.value(),
            "blur_enabled": self.chk_blur.isChecked(),
            "deep_search": self.chk_deep_search.isChecked(),
            "history_files": list(self.history_files),
            "history_folders": list(self.history_folders),
            "history_instances": list(getattr(self, "history_instances", set())),
        }
        with open("settings.json", "w") as f:
            import json

            json.dump(settings, f, indent=4)

    def load_settings(self):
        if os.path.exists("settings.json"):
            try:
                import json

                with open("settings.json", "r") as f:
                    settings = json.load(f)
                    val = settings.get("opacity", 100)
                    self.slider_opacity.setValue(val)

                    # Load history
                    saved_blur = settings.get("blur_enabled", False)
                    self.chk_blur.setChecked(saved_blur)

                    saved_deep = settings.get("deep_search", False)
                    self.chk_deep_search.setChecked(saved_deep)

                    saved_files = settings.get("history_files", [])
                    saved_folders = settings.get("history_folders", [])
                    saved_instances = settings.get("history_instances", [])

                    if not hasattr(self, "history_instances"):
                        self.history_instances = set()

                    # Auto-load the latest instance if it exists, otherwise fall back to everything else
                    if saved_instances:
                        fld = saved_instances[-1]
                        if os.path.exists(fld):
                            self.history_instances.add(fld)

                            self.clear_list()
                            # Instead of blocking here, kick the worker load off
                            self.current_loaded_type = "instance"
                            self.current_loaded_path = fld
                            self.worker = JarLoaderWorker(
                                mode="instance",
                                paths=[fld],
                                enable_deep_search=self.chk_deep_search.isChecked(),
                            )
                            self.worker.progress.connect(self.on_worker_progress)
                            self.worker.jar_loaded.connect(self.on_worker_jar_loaded)
                            self.worker.finished_loading.connect(
                                self.on_worker_finished
                            )
                            self.worker.start()

                    else:
                        if saved_files:
                            self.worker_files = JarLoaderWorker(
                                mode="file",
                                paths=saved_files,
                                enable_deep_search=self.chk_deep_search.isChecked(),
                            )
                            self.worker_files.progress.connect(self.on_worker_progress)
                            self.worker_files.jar_loaded.connect(
                                self.on_worker_jar_loaded
                            )
                            self.worker_files.finished_loading.connect(
                                self.on_worker_finished
                            )
                            self.worker_files.start()

                        if saved_folders:
                            self.worker_folders = JarLoaderWorker(
                                mode="folder",
                                paths=saved_folders,
                                enable_deep_search=self.chk_deep_search.isChecked(),
                            )
                            self.worker_folders.progress.connect(
                                self.on_worker_progress
                            )
                            self.worker_folders.jar_loaded.connect(
                                self.on_worker_jar_loaded
                            )
                            self.worker_folders.finished_loading.connect(
                                self.on_worker_finished
                            )
                            self.worker_folders.start()

            except Exception as e:
                print(f"Failed to load settings: {e}")

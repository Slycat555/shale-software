"""pacman backend: Arch repository packages.

Takes the place of Mint's apt backend. The package list and the preview of what an
install or removal would change come straight from pacman (no root needed). The change
itself runs in pacman-helper as root, through pkexec, which reports progress as JSON
lines.

Display info (names, icons, screenshots, categories) comes from Arch's AppStream
catalogue in /usr/share/swcatalog (the archlinux-appstream-data package), read with the
same code that reads Flathub's.
"""

import json
import os
import re
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Xmlb', '2.0')
from gi.repository import Gtk, GLib, Gio, Xmlb

from .pkgInfo import PacmanPkgInfo
from .dialogs import ChangesConfirmDialog
from .misc import warn, debug
from . import appstream_pool

HELPER = "/usr/lib/shale-software/pacman-helper"
SWCATALOG = "/usr/share/swcatalog"
REPOS = ("core", "extra", "multilib")

# Never offered for removal, on top of everything the base package needs: without these
# the computer doesn't start or has no desktop.
CRITICAL_PACKAGES = {"base", "linux", "linux-lts", "linux-zen", "linux-firmware", "pacman", "sudo",
                     "polkit", "systemd", "sddm", "plasma-desktop", "plasma-workspace", "kwin",
                     "networkmanager", "mesa", "pipewire", "python", "python-gobject", "flatpak"}

# Freedesktop categories -> the section names mintinstall builds its categories from
# (Debian's sections, see Application.build_categories). First match wins.
SECTION_FOR_CATEGORY = (
    ("WebBrowser", "web"), ("Email", "mail"), ("InstantMessaging", "net"), ("Chat", "net"),
    ("IRCClient", "net"), ("FileTransfer", "net"), ("P2P", "net"), ("Game", "games"),
    ("Music", "sound"), ("Audio", "sound"), ("Video", "video"), ("AudioVideo", "video"),
    ("Photography", "graphics"), ("Graphics", "graphics"), ("WordProcessor", "office"),
    ("Spreadsheet", "office"), ("Office", "office"), ("TextEditor", "editors"),
    ("Math", "math"), ("Science", "science"), ("Electronics", "electronics"),
    ("Education", "education"), ("Development", "devel"), ("Network", "net"),
    ("Settings", "system"), ("System", "system"), ("Utility", "utils"),
)
FONT_PREFIXES = ("ttf-", "otf-", "noto-fonts", "adobe-source-", "cantarell-fonts", "gnu-free-fonts")


class PacmanError(Exception):
    pass


def capitalize(string):
    if len(string) > 1:
        return (string[0].upper() + string[1:])

    return (string)


def run_pacman(*args):
    return subprocess.run(["pacman", *args], capture_output=True, text=True,
                          env={**os.environ, "LC_ALL": "C"})


def add_prefix(name):
    return "pacman:%s" % (name)


def make_pkg_hash(pac_pkg):
    return add_prefix(pac_pkg.name)


class PacmanPkg:
    """One package in the sync databases, with its AppStream component if it has one."""
    __slots__ = ("name", "repo", "version", "desc", "installed_version", "component", "url")

    def __init__(self, name, repo, version, installed_version):
        self.name = name
        self.repo = repo
        self.version = version
        self.installed_version = installed_version
        self.desc = ""
        self.component = None
        self.url = None

    def get_url(self):
        if self.url is None:
            m = re.search(r"^URL\s*: (\S+)", run_pacman("-Si", f"{self.repo}/{self.name}").stdout, re.M)
            self.url = m.group(1) if m and m.group(1) != "None" else ""
        return self.url


# ── AppStream catalogue ──────────────────────────────────────────────────────────

class _SwcatalogRemote:
    """Stands in for a Flatpak remote so appstream_pool can read an Arch repository."""
    def __init__(self, repo):
        self.repo = repo

    def get_name(self):
        return self.repo

    def get_appstream_dir(self):
        return Gio.File.new_for_path(SWCATALOG)

    def get_disabled(self):
        return False


class _SwcatalogPackage(appstream_pool.Package):
    __slots__ = ()

    def get_icon(self, size=64):
        # Arch keeps cached icons per repository, not next to the catalogue like Flathub.
        best = None
        try:
            icons = self.xbnode.query("icon", 0)
        except GLib.Error:
            return None
        for icon in icons:
            kind = icon.get_attr("type")
            text = icon.get_text()
            if kind == "stock":
                best = best or text
            elif kind == "cached":
                height = int(icon.get_attr("height") or 64)
                path = f"{SWCATALOG}/icons/archlinux-arch-{self.remote_name}/{height}x{height}/{text}"
                if os.path.exists(path):
                    if height >= size:
                        return path
                    best = path
        return best


class _SwcatalogPool(appstream_pool.Pool):
    def _load_xmlb_silo(self):
        xml = Gio.File.new_for_path(f"{SWCATALOG}/xml/{self.remote.get_name()}.xml.gz")
        if not xml.query_exists(None):
            self.xmlb_silo = None
            return
        cache_dir = os.path.join(GLib.get_user_cache_dir(), "shale-software")
        os.makedirs(cache_dir, exist_ok=True)
        source = Xmlb.BuilderSource()
        try:
            source.load_file(xml, Xmlb.BuilderSourceFlags.NONE, None)
            builder = Xmlb.Builder()
            for locale in self.locale_variants:
                builder.add_locale(locale)
            builder.import_source(source)
            # Compiled once and kept, so later starts don't parse the XML again.
            blob = Gio.File.new_for_path(os.path.join(cache_dir, f"swcatalog-{self.remote.get_name()}.xb"))
            self.xmlb_silo = builder.ensure(
                blob, Xmlb.BuilderCompileFlags.SINGLE_LANG | Xmlb.BuilderCompileFlags.SINGLE_ROOT, None)
        except GLib.Error as e:
            warn("Could not load the AppStream catalogue for '%s': %s" % (self.remote.get_name(), e.message))
            self.xmlb_silo = None

    def components_by_pkgname(self):
        """{pkgname: (Package, [categories])} for every desktop app in this repository."""
        found = {}
        if self.xmlb_silo is None:
            return found
        try:
            nodes = self.xmlb_silo.query("components/component", 0)
        except GLib.Error:
            return found
        for node in nodes:
            try:
                pkgname = node.query_text("pkgname")
            except GLib.Error:
                continue
            if not pkgname or pkgname in found:
                continue
            try:
                categories = [c.get_text() for c in node.query("categories/category", 0)]
            except GLib.Error:
                categories = []
            found[pkgname] = (_SwcatalogPackage(pkgname, self.remote, node), categories)
        return found


_components = None


def get_components():
    """{pkgname: (Package, [categories])} across the Arch repositories."""
    global _components
    if _components is None:
        components = {}
        for repo in REPOS:
            for name, value in _SwcatalogPool(_SwcatalogRemote(repo)).components_by_pkgname().items():
                components.setdefault(name, value)
        _components = components
        debug("Installer: %d Arch packages have AppStream data" % len(components))
    return _components


def section_for(name, categories):
    if name.startswith(FONT_PREFIXES):
        return "fonts"
    for category, section in SECTION_FOR_CATEGORY:
        if category in categories:
            return section
    return None


# ── Package database ─────────────────────────────────────────────────────────────

_SS_HEADER = re.compile(r"^(\S+)/(\S+) (\S+)(?: \([^)]*\))?(?: \[installed(?:: ([^\]]+))?\])?$")

_pacman_db = None
_pacman_db_lock = threading.Lock()


def _load_db():
    db = {}
    current = None
    for line in run_pacman("-Ss", "").stdout.splitlines():
        if line.startswith(" "):
            if current is not None:
                current.desc = line.strip()
            continue
        m = _SS_HEADER.match(line)
        if not m:
            current = None
            continue
        repo, name, version, installed = m.groups()
        if "[installed" in line and installed is None:
            installed = version
        if name in db:  # same name in two repositories: pacman uses the first
            current = None
            continue
        current = db[name] = PacmanPkg(name, repo, version, installed)

    components = get_components()
    for name, pkg in db.items():
        if name in components:
            pkg.component = components[name][0]
    return db


def get_pacman_db(full=False):
    global _pacman_db

    if full or (not _pacman_db):
        with _pacman_db_lock:
            _pacman_db = _load_db()

    return _pacman_db


def _hidden(name):
    """Libraries and other packages nobody installs on their own."""
    if name.startswith(("lib", "lib32-", "python-", "perl-", "haskell-", "ruby-", "nodejs-",
                        "texlive-", "linux-api-headers")) and \
            not name.startswith(("libreoffice", "librewolf", "libresprite")):
        return True
    return name.endswith(("-docs", "-doc", "-debug", "-headers", "-devel", "-i18n"))


def process_full_pacman_db(cache):
    db = get_pacman_db(full=True)
    components = get_components()

    sections = {}

    for name, pkg in db.items():
        if _hidden(name) and name not in components:
            continue

        pkg_hash = make_pkg_hash(pkg)
        section = section_for(name, components[name][1] if name in components else [])
        if section:
            sections.setdefault(section, []).append(pkg_hash)

        cache[pkg_hash] = PacmanPkgInfo(pkg_hash, pkg)

    return cache, sections


def search_for_pkginfo_pacman_pkg(pkginfo):
    return get_pacman_db().get(pkginfo.name)


def pkginfo_is_installed(pkginfo):
    pkg = get_pacman_db().get(pkginfo.name)
    return pkg is not None and pkg.installed_version is not None


def sync_cache_installed_states():
    get_pacman_db(full=True)


# ── Working out a change ─────────────────────────────────────────────────────────

class Change:
    """A package an install or removal touches (what the confirm dialog lists)."""
    __slots__ = ("name", "version")

    def __init__(self, name, version):
        self.name = name
        self.version = version

    def get_name(self):
        return self.name


_SIZE_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3}


def _installed_sizes(flag, names):
    """Installed size of each package, from pacman -Si (repository) or -Qi (local)."""
    if not names:
        return {}
    sizes, name = {}, None
    for line in run_pacman(flag, *names).stdout.splitlines():
        if line.startswith("Name "):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("Installed Size") and name:
            value, unit = line.split(":", 1)[1].split()
            sizes.setdefault(name, int(float(value) * _SIZE_UNITS.get(unit, 1)))
    return sizes


def _targets(*args):
    """The packages a transaction would touch, as (name, version, download size)."""
    r = run_pacman(*args, "--print-format", "%n %v %s")
    if r.returncode != 0:
        lines = [l.strip(": ") for l in (r.stderr + r.stdout).splitlines() if l.strip()]
        raise PacmanError("\n".join(lines) or "pacman could not work out the changes.")
    targets = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and not line.startswith((":", "warning")):
            targets.append((parts[0], parts[1], int(parts[2]) if parts[2].isdigit() else 0))
    return targets


_critical = None


def critical_packages():
    global _critical
    if _critical is None:
        m = re.search(r"^Depends On\s*: (.*)$", run_pacman("-Qi", "base").stdout, re.M)
        deps = {re.split(r"[<>=]", d)[0] for d in m.group(1).split()} if m else set()
        _critical = CRITICAL_PACKAGES | deps
    return _critical


def select_packages(task):
    debug("Installer: Calculating changes required for pacman package: %s" % task.pkginfo.name)
    threading.Thread(target=_calculate_changes, args=(task,), daemon=True).start()


def _calculate_changes(task):
    name = task.pkginfo.name

    try:
        if task.type == task.INSTALL_TASK:
            # -u as well: on Arch, installing on top of an out-of-date system can break it,
            # so the helper brings everything up to date in the same transaction.
            db = get_pacman_db()
            for target, version, size in _targets("-Sup", "--needed", name):
                change = Change(target, version)
                if target in db and db[target].installed_version:
                    task.to_update.append(change)
                else:
                    task.to_install.append(change)
                task.download_size += size

            new = _installed_sizes("-Si", [c.name for c in task.to_install + task.to_update])
            old = _installed_sizes("-Qi", [c.name for c in task.to_update])
            space = sum(new.values()) - sum(old.values())
        else:
            if name in critical_packages():
                task.info_ready_status = task.STATUS_FORBIDDEN
            else:
                task.to_remove = [Change(t, v) for t, v, _ in _targets("-Rsp", name)]
                if any(c.name in critical_packages() for c in task.to_remove):
                    task.info_ready_status = task.STATUS_FORBIDDEN
            space = -sum(_installed_sizes("-Qi", [c.name for c in task.to_remove]).values())
    except PacmanError as e:
        message = str(e)
        needed_by = re.findall(r"breaks dependency '[^']+' required by (\S+)", message)
        if needed_by:
            task.info_ready_status = task.STATUS_BROKEN
            message = ("%s can't be removed on its own because other software needs it: %s"
                       % (task.pkginfo.get_display_name(), ", ".join(sorted(set(needed_by)))))
        elif task.info_ready_status == task.STATUS_NONE:
            task.info_ready_status = task.STATUS_UNKNOWN
        GLib.idle_add(task.handle_error, message, True)
        return

    if space < 0:
        task.freed_size = -space
        task.install_size = 0
    else:
        task.freed_size = 0
        task.install_size = space

    if task.info_ready_status not in (task.STATUS_FORBIDDEN, task.STATUS_BROKEN):
        task.info_ready_status = task.STATUS_OK
        task.confirm = lambda: _confirm_transaction(task)
        task.cancel = task.cancellable.cancel
        task.execute = lambda: _execute_transaction(task)

    GLib.idle_add(task.call_info_ready_callback)


def _confirm_transaction(task):
    if len(task.to_install) > 1 or len(task.to_remove) > 1 or len(task.to_update) > 0:
        dia = ChangesConfirmDialog(None, task, parent=task.parent_window)
        res = dia.run()
        dia.hide()
        dia.destroy()

        return res == Gtk.ResponseType.OK
    else:
        return True


# ── Running it ───────────────────────────────────────────────────────────────────

def _execute_transaction(task):
    if task.cancellable.is_cancelled():
        return

    if task.client_progress_cb is not None:
        task.has_window = True
    else:
        from .dialogs import FlatpakProgressWindow
        FlatpakProgressWindow(task, parent=task.parent_window).show()

    threading.Thread(target=_run_helper, args=(task,), daemon=True).start()


def _report(task, progress, text):
    if task.client_progress_cb:
        GLib.idle_add(task.client_progress_cb, task.pkginfo, progress, False, text,
                      priority=GLib.PRIORITY_DEFAULT)


def _run_helper(task):
    op = "install" if task.type == task.INSTALL_TASK else "remove"
    error = None

    try:
        proc = subprocess.Popen(["pkexec", HELPER, op, task.pkginfo.name],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("type") == "progress":
                _report(task, int(msg.get("progress", 0) * 100), msg.get("text", ""))
            elif msg.get("type") == "error":
                error = msg.get("text")
        rc = proc.wait()
    except OSError as e:
        error, rc = str(e), 1

    if rc in (126, 127) and error is None:
        # The password dialog was dismissed: nothing happened, nothing to report.
        GLib.idle_add(task.call_error_cleanup_callback)
    elif rc != 0 or error:
        task.handle_error(error or "The software could not be changed.")
        GLib.idle_add(task.call_error_cleanup_callback)
    else:
        GLib.idle_add(task.call_finished_cleanup_callback)

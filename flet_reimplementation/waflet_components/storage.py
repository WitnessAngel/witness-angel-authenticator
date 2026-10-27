"""Storage roots, folder-access probes and authenticator location discovery (01 §4, §4.4)."""
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AUTHENTICATOR_DIRNAME = "authenticator.keystore"
LEGACY_INTERNAL_AUTHENTICATOR_DIRNAME = "authenticator"


class LocationType:
    USER_PROFILE = "USER_PROFILE"
    CUSTOM_FOLDER = "CUSTOM_FOLDER"
    USB_DEVICE = "USB_DEVICE"


@dataclass
class StorageRoots:
    platform: str  # "android", "ios" or "desktop"
    internal_app_root: Path
    internal_cache_dir: Path
    external_app_root: Optional[Path]
    external_app_root_prefix: Optional[Path] = None  # Only used for "<sdcard>/..." display
    home_dir: Optional[Path] = None

    @property
    def internal_authenticator_dir(self):
        return self.internal_app_root / AUTHENTICATOR_DIRNAME

    @property
    def exports_dir(self):
        return self.external_app_root / "exports" if self.external_app_root else None

    @property
    def logs_dir(self):
        return self.internal_app_root / "logs"

    # ---- Recorder paths (recorder 01 §7); same names as the Kivy app, shared by GUI and service
    @property
    def keystore_pool_dir(self):
        return self.internal_app_root / "keystore_pool"

    @property
    def default_cryptainers_dir(self):
        return self.internal_app_root / "cryptainers"

    @property
    def recording_marker(self):
        return self.internal_app_root / "recording_in_progress"

    @property
    def preview_image(self):
        return self.internal_cache_dir / "video_preview_image.jpg"

    @property
    def device_uid_file(self):
        return self.internal_app_root / ".wa_device_uid.json"

    def osc_socket_path(self, socket_index):
        """Unix datagram socket of the GUI (0) or of the service (1); Windows uses UDP ports instead."""
        return self.internal_app_root / (".witnessangel%d.sock" % socket_index)


def detect_platform():
    flet_platform = os.getenv("FLET_PLATFORM", "")  # Set by Flet's mobile embedding
    return flet_platform if flet_platform in ("android", "ios") else "desktop"


def compute_storage_roots(platform, home_dir, app_support_dir=None, external_files_dir=None,
                          documents_dir=None, cache_dir=None, sdcard_root=None) -> StorageRoots:
    """Pure mapping of 01 §4. On mobile, the OS dirs come from Flet's StoragePaths service
    (path_provider): getApplicationSupportDirectory == Context.getFilesDir() on Android and
    Library/Application Support on iOS, so existing 1.5 authenticators are found."""
    home_dir = Path(home_dir)
    if platform == "android":
        return StorageRoots(platform, Path(app_support_dir), Path(cache_dir or app_support_dir),
                            Path(external_files_dir) if external_files_dir else None,
                            Path(sdcard_root) if sdcard_root else None, home_dir)
    if platform == "ios":
        return StorageRoots(platform, Path(app_support_dir or home_dir / "Library" / "Application Support"),
                            Path(cache_dir or home_dir / "tmp"), Path(documents_dir or home_dir / "Documents"),
                            None, home_dir)
    root = home_dir / ".witnessangel"
    return StorageRoots("desktop", root, root / "cache", root / "external", None, home_dir)


async def discover_storage_roots(page) -> StorageRoots:
    """Ask the OS for its folders (async Flet services) on mobile; plain home paths elsewhere."""
    platform = detect_platform()
    if platform == "desktop":
        return compute_storage_roots(platform, Path.home())
    import flet as ft

    paths = ft.StoragePaths()
    kwargs = dict(app_support_dir=await paths.get_application_support_directory(),
                  cache_dir=await paths.get_application_cache_directory())
    if platform == "android":
        kwargs["external_files_dir"] = await paths.get_external_storage_directory()  # getExternalFilesDir(null)
        sdcards = await paths.get_external_storage_directories() or []
        # ponytail: derive "/storage/emulated/0" from ".../Android/data/<pkg>/files" for display only
        if kwargs["external_files_dir"] and "/Android/data/" in kwargs["external_files_dir"]:
            kwargs["sdcard_root"] = kwargs["external_files_dir"].split("/Android/data/")[0]
        elif sdcards:
            kwargs["sdcard_root"] = sdcards[0]
    else:
        kwargs["documents_dir"] = await paths.get_application_documents_directory()
    return compute_storage_roots(platform, Path.home(), **kwargs)


def bootstrap_storage(roots: StorageRoots):
    """Create the app dirs (01 §4 "Directory creation") and rename the legacy internal folder."""
    roots.internal_app_root.mkdir(parents=True, exist_ok=True)
    roots.logs_dir.mkdir(exist_ok=True)
    legacy_dir = roots.internal_app_root / LEGACY_INTERNAL_AUTHENTICATOR_DIRNAME
    if legacy_dir.is_dir() and not roots.internal_authenticator_dir.exists():
        logger.info("Renaming legacy authenticator folder %s", legacy_dir)
        legacy_dir.rename(roots.internal_authenticator_dir)
    for folder in (roots.external_app_root, roots.exports_dir):
        if folder:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # Best effort only
                logger.warning("Could not create %s: %r", folder, exc)


def bootstrap_recorder_storage(roots: StorageRoots):
    """Directories of the recorder (01 §7): app root + logs + external dirs, then cache, keystore pool, cryptainers."""
    bootstrap_storage(roots)
    for folder in (roots.internal_cache_dir, roots.keystore_pool_dir, roots.default_cryptainers_dir):
        folder.mkdir(parents=True, exist_ok=True)


_RASPBERRY_PI_SOCS = ("BCM2708", "BCM2709", "BCM2835", "BCM2836", "BCM2711")


def is_raspberry_pi(cpuinfo_path="/proc/cpuinfo", device_tree_model_path="/proc/device-tree/model") -> bool:
    """01 §8.2 plus OI-43: the 1.0 SoC whitelist, or else the device-tree model (Pi 5 and newer SoCs)."""
    try:
        for line in Path(cpuinfo_path).read_text(errors="ignore").splitlines():
            if line.startswith("Hardware") and line.split(":", 1)[-1].strip() in _RASPBERRY_PI_SOCS:
                return True
        return b"Raspberry Pi" in Path(device_tree_model_path).read_bytes()
    except OSError:
        return False


def get_wait_time_multiplier(is_pi: bool) -> int:
    return 4 if is_pi else 1


def is_folder_writable(path: Path) -> bool:
    """Really create and delete a temp folder + file: os.access() is unreliable on Windows."""
    test_folder = Path(path) / ("~test-folder-%d" % random.randint(0, 100000))
    try:
        test_folder.mkdir()
        test_file = test_folder / "~test-file.tmp"
        test_file.touch(exist_ok=False)
        test_file.unlink()
        test_folder.rmdir()
    except OSError:
        return False
    return True


def is_folder_readable(path: Path) -> bool:
    try:
        list(Path(path).iterdir())
    except OSError:
        return False
    return True


def is_folder_accessible(path, require_writable=False) -> bool:
    """False means the toast "External storage is not accessible" (01 §4)."""
    if not path:
        return False
    path = Path(path)
    return path.is_dir() and is_folder_readable(path) and (not require_writable or is_folder_writable(path))


def migrate_custom_dir(value: str, roots: StorageRoots) -> str:
    """01 §4.4 migration rule for the stored `custom_authenticator_dir` (absolute path written by 1.5)."""
    if not value:
        return ""  # Empty means "none", never the current directory
    path = Path(value).absolute()
    if roots.platform == "android":
        if roots.external_app_root and roots.external_app_root in (path, *path.parents):
            return str(path)
        return ""  # No access grant for other paths: the user must pick the folder again
    if roots.platform == "ios":
        parts = value.split("/Documents/", 1)
        if len(parts) == 2 and roots.external_app_root:
            return str(roots.external_app_root / parts[1])  # Container UUID changes across installs (OI-16)
        if value.rstrip("/").endswith("/Documents") and roots.external_app_root:
            return str(roots.external_app_root)
        return ""
    return str(path)


def list_usb_authdevices(platform):
    """Desktop only (OI-24): mobile users reach removable media through the folder picker."""
    if platform != "desktop":
        return []
    try:
        from wacryptolib.authdevice import list_available_authdevices

        return list_available_authdevices()
    except Exception as exc:  # Missing pyudev/wmi, no udev in container, unsupported OS...
        logger.warning("USB authdevice discovery failed: %r", exc)
        return []


def list_authenticator_locations(roots: StorageRoots, custom_folder, authdevices=None):
    """Fixed order of 02 §3.2: user profile, custom folder, then one entry per USB partition."""
    if authdevices is None:
        authdevices = list_usb_authdevices(roots.platform)
    locations = [
        dict(location_type=LocationType.USER_PROFILE, authenticator_dir=roots.internal_authenticator_dir),
        dict(location_type=LocationType.CUSTOM_FOLDER,
             authenticator_dir=(Path(custom_folder) / AUTHENTICATOR_DIRNAME) if custom_folder else None,
             custom_folder=custom_folder or None),
    ]
    for authdevice in authdevices:
        locations.append(dict(location_type=LocationType.USB_DEVICE, authenticator_dir=Path(authdevice["authenticator_dir"]),
                              authdevice=authdevice))
    return locations


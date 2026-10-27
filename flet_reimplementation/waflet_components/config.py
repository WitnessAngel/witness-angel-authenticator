"""INI config seeded from shipped defaults. No interpolation (OI-32), atomic whole-file save (OI-33).

Usable from several processes: `reload()` re-reads the file (the recorder service calls it at each start request).
"""
import configparser
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class AppConfig:
    def __init__(self, config_path: Path, defaults_path: Path):
        self.path = Path(config_path)
        self.defaults_path = Path(defaults_path)
        self._parser = self._load()

    def _load(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(self.defaults_path, encoding="utf8")  # Missing keys silently take defaults
        for attempt in (1, 2):  # A writer in another process may be mid-way (OI-33): retry once
            try:
                parser.read(self.path, encoding="utf8")
                break
            except configparser.Error as exc:
                if attempt == 2:
                    logger.error("Ignoring corrupted config file %s: %r", self.path, exc)
                    parser = configparser.ConfigParser(interpolation=None)
                    parser.read(self.defaults_path, encoding="utf8")
                else:
                    time.sleep(0.2)
        return parser

    def reload(self):
        """Forget in-memory values and re-read defaults + user file."""
        self._parser = self._load()

    def get(self, section, key, fallback=""):
        return self._parser.get(section, key, fallback=fallback)

    def getboolean(self, section, key):
        return self._parser.getboolean(section, key)  # "0/1", "true/false"...; ValueError if garbage

    def getint(self, section, key):
        return self._parser.getint(section, key)

    def getfloat(self, section, key):
        return self._parser.getfloat(section, key)

    def set(self, section, key, value, save=True):
        if not self._parser.has_section(section):
            self._parser.add_section(section)
        self._parser.set(section, key, str(value))
        if save:
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        with open(tmp_path, "w", encoding="utf8") as f:
            self._parser.write(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.path)

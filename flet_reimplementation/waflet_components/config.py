"""INI config seeded from shipped defaults, whole-file rewrite on save (01 §3)."""
import configparser
from pathlib import Path


class AppConfig:
    def __init__(self, config_path: Path, defaults_path: Path):
        self.path = Path(config_path)
        self._parser = configparser.ConfigParser(interpolation=None)
        self._parser.read(defaults_path, encoding="utf8")  # Missing keys silently take defaults
        self._parser.read(self.path, encoding="utf8")

    def get(self, section, key, fallback=""):
        return self._parser.get(section, key, fallback=fallback)

    def set(self, section, key, value, save=True):
        if not self._parser.has_section(section):
            self._parser.add_section(section)
        self._parser.set(section, key, str(value))
        if save:
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf8") as f:
            self._parser.write(f)

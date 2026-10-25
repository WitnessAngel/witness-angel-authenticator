"""Minimal i18n: English msgids, chained per-language catalogs (01 §2.6).

ponytail: catalogs are plain Python dicts instead of gettext .po/.mo, no compile step needed;
switch to gettext if translators need .po tooling.
"""
import locale
import logging
import os
import warnings

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "fr")
LANGUAGE_NAMES = {"en": "English", "fr": "Français"}  # Always shown in their native names


def detect_language(environ=None, os_language=None):
    """01 §2.6: LANG exactly "en"/"fr", else the OS language; anything starting with "fr" is French."""
    environ = os.environ if environ is None else environ
    forced = environ.get("LANG", "").strip().lower()
    if forced in SUPPORTED_LANGUAGES:
        return forced
    if os_language is None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                os_language = locale.getdefaultlocale()[0]
        except Exception:  # getdefaultlocale may vanish in future Pythons
            os_language = locale.getlocale()[0]
    return "fr" if (os_language or "").lower().startswith("fr") else "en"


class Translator:
    def __init__(self):
        self.lang = "en"
        self._catalogs = []  # Ordered: first registered catalog wins (app catalog, then components)
        self._listeners = []

    def add_catalog(self, catalog: dict, first=False):
        """`catalog` maps a language code to a {msgid: msgstr} dict; `first` catalogs take precedence."""
        if catalog not in self._catalogs:
            self._catalogs.insert(0 if first else len(self._catalogs), catalog)

    def _(self, msgid: str) -> str:
        if self.lang != "en":
            for catalog in self._catalogs:
                msgstr = catalog.get(self.lang, {}).get(msgid)
                if msgstr:
                    return msgstr
        return msgid

    def f(self, msgid: str, **kwargs) -> str:
        """Translate then interpolate named placeholders."""
        return self._(msgid).format(**kwargs)

    def switch_lang(self, lang: str):
        assert lang in SUPPORTED_LANGUAGES, lang
        self.lang = lang
        for listener in list(self._listeners):
            listener(lang)

    def add_listener(self, callback):
        self._listeners.append(callback)


tr = Translator()
tr.add_catalog(__import__("waflet_components.locale_fr", fromlist=["CATALOG"]).CATALOG)  # Components catalog, last

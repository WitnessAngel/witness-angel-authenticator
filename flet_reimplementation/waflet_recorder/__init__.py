from waflet_components.i18n import tr

from . import locale_fr

PROGRAM_VERSION = "1.0"
tr.add_catalog(locale_fr.CATALOG, first=True)  # App catalog before the components one

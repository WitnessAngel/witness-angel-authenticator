"""Containers screen (02 §6): list, select, details, delete, hand over to decryption and requests."""
import logging

import flet as ft

from waflet_components.app_base import Screen
from waflet_components.formatting import COLON, convert_bytes_to_human_representation, format_trustee_label
from waflet_components.i18n import tr
from waflet_components.widgets import top_bar, icon_action, empty_state, banner, selectable_row

from .. import cryptainers as cryptainer_logic

logger = logging.getLogger(__name__)


class ContainersScreen(Screen):
    name = "cryptainer_storage_management"
    title = "Containers"
    top_level = True

    def __init__(self, app):
        super().__init__(app)
        self.entries = []  # Newest first
        self.storage_error = None  # OI-80: shown instead of a silent stale list

    def build(self):
        self.banner = banner("")
        self.list_view = ft.ListView(expand=True, spacing=0)
        self._render()
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            self.banner, self.list_view,
            ft.Row([
                ft.Button(content=tr._("Delete"), icon=ft.Icons.DELETE_FOREVER, expand=True,
                          on_click=lambda e: self.app.guarded(self.ask_delete)()),
                ft.Button(content=tr._("Prepare decryption"), icon=ft.Icons.REMOVE_RED_EYE_OUTLINED, expand=True,
                          on_click=lambda e: self.app.guarded(self.prepare_decryption)()),
                ft.Button(content=tr._("All authorization requests"), icon=ft.Icons.FORMAT_LIST_BULLETED, expand=True,
                          on_click=lambda e: self.app.go("claimant_revelation_request_management"))])])

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), menu=True, actions=[
            icon_action(ft.Icons.SELECT_ALL, "Select all", lambda e: self.app.guarded(self.select_all)()),
            icon_action(ft.Icons.DESELECT, "Select none", lambda e: self.app.guarded(self.select_none)()),
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.refresh)()),
            icon_action(ft.Icons.HOME, "Back to home", lambda e: self.app.go("recorder_homepage")),
        ])

    def on_enter(self):
        self.refresh()

    # ------------------------------------------------------------ list

    @property
    def selection(self):
        return self.app.selected_cryptainers

    def refresh(self):
        def _list():
            storage = self.app.open_cryptainer_storage()
            return storage, cryptainer_logic.list_cryptainers(storage)

        def _done(result):
            storage, self.entries = result
            self.storage_error = None if storage is not None else \
                tr.f('Invalid container storage: "{cryptainer_dir}"', cryptainer_dir=self.app.settings.cryptainer_dir)
            self.selection.intersection_update(e["name"] for e in self.entries)  # Vanished containers leave the selection
            self._render()
            self.app.page.update()
            self.app.toast(tr._("Refreshed local containers"))

        self.app.run_in_background(_list, _done)

    def _render(self):
        self.banner.content.value = tr.f("View and manage encrypted containers (selected: {count})", count=len(self.selection))
        if self.storage_error:
            self.list_view.controls = [ft.Container(ft.Text(self.storage_error, color=ft.Colors.RED_700),
                                                    alignment=ft.Alignment.CENTER, padding=40)]
        elif not self.entries:
            self.list_view.controls = [empty_state()]
        else:
            self.list_view.controls = [self._row(index, e) for index, e in enumerate(self.entries, 1)]  # OI-89: from 1

    def _row(self, index, entry):
        size = tr._("missing") if entry["size"] is None else convert_bytes_to_human_representation(entry["size"])
        return selectable_row("N° %d: %s (%s)" % (index, entry["name"], size), entry["name"] in self.selection,
                              lambda value, name=entry["name"]: self.guarded_toggle(name, value),
                              lambda name=entry["name"]: self.app.guarded(self.show_details)(name))

    def guarded_toggle(self, name, value):
        (self.selection.add if value else self.selection.discard)(name)
        self.banner.content.value = tr.f("View and manage encrypted containers (selected: {count})", count=len(self.selection))
        self.app.page.update()

    def select_all(self):
        self.selection.update(e["name"] for e in self.entries)  # OI-79: a no-op, not an error, without storage
        self._render()
        self.app.page.update()

    def select_none(self):
        self.selection.clear()
        self._render()
        self.app.page.update()

    def selected_names(self):
        """Newest first, the order of the list."""
        return [e["name"] for e in self.entries if e["name"] in self.selection]

    # ------------------------------------------------------------ details (02 §6.3, OI-88)

    def show_details(self, name):
        def _load():
            return cryptainer_logic.get_cryptainer_details(self.app.open_cryptainer_storage(), name)

        def _done(details):
            lines = [tr._("Container ID") + COLON() + str(details["cryptainer_uid"]), "", tr._("Key Guardians used") + COLON(), ""]
            lines += ["N° %d%s%s" % (i, COLON(), format_trustee_label(t["owner"], t["keystore_uid"], t["trustee_type"]))
                      for i, t in enumerate(details["trustees"], 1)]
            self.app.show_dialog(name, "\n".join(lines))

        def _error(exc):
            logger.warning("Cannot load cryptainer %s: %r", name, exc)
            self.app.show_dialog(name, tr._("This container cannot be read") + COLON() + (str(exc) or type(exc).__name__)[:300])
            return True

        self.app.run_in_background(_load, _done, _error)

    # ------------------------------------------------------------ buttons (02 §6.4)

    def ask_delete(self):
        names = self.selected_names()
        if not names:
            return self.app.toast(tr._("Please select containers to delete"))
        self.app.show_dialog(
            tr._("Container deletion confirmation"), tr.f("Are you sure you want to delete {count} container(s)?", count=len(names)),
            actions=[self.app.action_button(tr._("Confirm deletion"), lambda: self.delete(names))], close_label=tr._("Cancel"))

    def delete(self, names):
        def _done(count):
            self.selection.difference_update(names)
            self.refresh()
        self.app.run_in_background(
            lambda: cryptainer_logic.delete_cryptainers(self.app.open_cryptainer_storage(read_only=False), names), _done)

    def prepare_decryption(self):
        if not self.selected_names():
            return self.app.toast(tr._("Please select containers to decrypt"))
        self.app.go("cryptainer_decryption_process")

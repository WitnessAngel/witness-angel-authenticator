find . -type f \( -name '*.py' -or -name '*.kv' \)  -print > __translatable_files
xgettext --from-code=UTF-8 --files-from=__translatable_files -Lpython -o locale/_messages.pot
msgmerge --update --backup=off locale/fr/LC_MESSAGES/witnessangel.po locale/_messages.pot
msgfmt -c -o locale/fr/LC_MESSAGES/witnessangel.mo locale/fr/LC_MESSAGES/witnessangel.po



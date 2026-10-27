"""French catalog of the recorder (texts of spec 02 §3.3 and others; OI-85 typos fixed).

Strings marked NEW do not exist in 1.0 (fixed/decided open issues); their French is ours.
"""

CATALOG = {"fr": {
    # Checkup (02 §3.3)
    "Sensors: {titles}": "Capteurs : {titles}",
    "local camera": "caméra locale",
    "local microphone": "microphone local",
    "IP camera {url}": "Caméra IP {url}",
    "Local microphone not found": "Microphone local non trouvé",
    'Wrong IP camera url: "{camera_url}"': 'Mauvaise url de caméra IP : "{camera_url}"',
    "No sensors are enabled": "Aucun capteur n'est activé",
    "{keyguardian_count} key guardian(s) selected, {keyguardian_threshold} of which necessary for decryption":
        "{keyguardian_count} gardien(s) de clés configuré(s), dont {keyguardian_threshold} nécessaire(s) pour le déchiffrement",
    "({dropped} selected key guardian(s) not found were ignored)":
        "({dropped} gardien(s) de clés sélectionné(s) introuvable(s) ignoré(s))",  # NEW (OI-36)
    "Container storage: {cryptainer_dir}": "Stockage des conteneurs : {cryptainer_dir}",
    'Invalid container storage: "{cryptainer_dir}"': 'Stockage des conteneurs invalide : "{cryptainer_dir}"',
    'Container storage is not writable: "{cryptainer_dir}"':
        'Stockage des conteneurs non accessible en écriture : "{cryptainer_dir}"',  # NEW (OI-34)
    "Each container stores {recording_duration_mn} mn(s) of video":
        "Chaque conteneur stocke {recording_duration_mn} mn(s) de vidéo",
    "Containers are kept for {max_cryptainer_age_day} day(s)":
        "Les conteneurs sont gardés {max_cryptainer_age_day} jour(s)",
    "Ffmpeg module is installed with a compatible {ffmpeg_version} version":
        "Module ffmpeg installé avec une version {ffmpeg_version} compatible",
    "Ffmpeg module not found, please ensure it is in your PATH":
        "Module ffmpeg non trouvé, veuillez vérifier qu'il est dans votre PATH",
    "Ffmpeg module is installed, but beware its version couldn't be determined":
        "Module ffmpeg installé, mais attention sa version n'a pas pu être déterminée",
    "Ffmpeg module is installed but this {ffmpeg_version} version is below required {min_ffmpeg_version}":
        "Module ffmpeg installé mais sa version {ffmpeg_version} est inférieure à {min_ffmpeg_version} requise",
    "Ffmpeg module is not required by the enabled sensors":
        "Le module ffmpeg n'est pas requis par les capteurs activés",  # NEW (OI-39)
    'Invalid value for setting "{key}"': 'Valeur invalide pour le paramètre "{key}"',  # NEW (OI-35)
    # Errors and results (msgids of ServiceError subclasses)  # NEW: all French below is ours
    "This key guardian is used by the ongoing recording and cannot be removed":
        "Ce gardien de clés est utilisé par l'enregistrement en cours et ne peut pas être supprimé",
    "Authenticator does not exist": "L'authentifieur n'existe pas",
    "Badly formed hexadecimal UUID string": "Chaîne UUID hexadécimale mal formée",
    "A selected key guardian has no usable public key": "Un gardien de clés sélectionné n'a pas de clé publique utilisable",
    "Not enough free space in the container storage": "Pas assez d'espace libre dans le stockage des conteneurs",
    "No sensor could be started": "Aucun capteur n'a pu être démarré",
    "Please select authenticators": "Veuillez sélectionner un authentifieur",
    "Description must be at least 10 characters long.": "La description doit faire au moins 10 caractères de long.",
    "Network error, please check the gateway url": "Erreur de réseau, veuillez vérifier l'url de la passerelle",
    "Info": "Info",
}}

# GUI (phase 2), texts of spec 02. OI-85 typos fixed; OI-86: "authorization request" everywhere. Entries marked NEW are ours.
CATALOG["fr"].update({
    # Shell, drawer, toolbar
    "Recorder": "Enregistreur", "Key Guardians": "Gardiens des Clés", "Containers": "Conteneurs",
    "Menu": "Menu", "About": "À propos", "Details": "Détails", "Information": "Information",  # NEW
    "Back to home": "Accueil",  # OI-85: no longer the same word as Back
    "Reset background service": "Réinitialiser le service en fond", "Select all": "Sélectionner tout",
    "Select none": "Sélectionner rien", "Yes": "Oui", "No": "Non", "Delete": "Supprimer",
    "Logs are stored in {path}": "Les journaux sont dans {path}",  # NEW
    "Recorder settings": "Paramètres d'enregistrement",
    # Homepage
    "Start Recording": "Lancer Enregistrement", "Stop Recording": "Arrêter Enregistrement",
    "Configuration errors prevent recording": "Des erreurs de configuration empêchent l'enregistrement",
    "Some configuration changes might only apply at next recording restart":
        "Certains changements de configuration pourraient ne s'appliquer qu'au redémarrage de l'enregistrement",
    "Recording could not start": "L'enregistrement n'a pas pu démarrer",  # NEW (OI-15)
    "Recording (degraded): {sensors}": "Enregistrement (dégradé) : {sensors}",  # NEW (OI-16)
    "running": "en cours", "restarting": "redémarrage", "failed": "en échec",  # NEW
    "Container storage is almost full": "Le stockage des conteneurs est presque plein",  # NEW (OI-44)
    "This stops the background service, and the recording in progress if any. It is restarted automatically within seconds. Continue?":
        "Ceci arrête le service en fond, et l'enregistrement en cours s'il y en a un. Il est relancé "
        "automatiquement en quelques secondes. Continuer ?",  # NEW (OI-13)
    "Last preview, taken {age} ago": "Dernier aperçu, pris il y a {age}",  # NEW (OI-31)
    "{count} s": "{count} s", "{count} mn": "{count} mn", "{count} h": "{count} h",
    # Settings (02 §4.2)
    "Sensors": "Capteurs", "Key guardians": "Gardiens de Clés", "Storage": "Stockage", "Peripherals": "Périphériques",
    "Network": "Réseau", "Advanced": "Avancé", "(none)": "(aucun)",
    "Local camera": "Caméra locale", "Enable attached camera": "Activer la caméra attachée",
    "Local camera rotation": "Rotation de caméra locale",
    "Rotation angle of camera (Picamera only)": "Angle de rotation de caméra (Picamera uniquement)",
    "Local microphone": "Microphone local", "Enable attached microphone": "Activer le microphone attaché",
    "Compress audio": "Compresser l'audio", "Encode audio recording": "Encoder l'enregistrement audio",
    "Mux recordings": "Muxer l'enregistrement",
    "Merge local video and audio (requires libcamera)": "Fusionner vidéo et audio locaux (requiert libcamera)",
    "IP camera": "Caméra IP", "Enable network camera": "Activer la caméra réseau",
    "IP Camera URL": "URL Caméra IP", "RTSP stream address": "Adresse de flux RTSP",
    "Media recording duration (mn)": "Durée des enregistrements média (mn)",
    "How long each audio/video clip must last": "Combien de temps chaque clip audio/vidéo doit durer",
    "Key guardian threshold": "Seuil de gardiens de clés",
    "Count of key guardians required to decrypt data": "Nombre de gardiens de clés requis pour déchiffrer les données",
    "Container folder": "Dossier des conteneurs",
    "Folder to store containers (defaults to user profile)": "Dossier de stockage des conteneurs (par défaut, le profil utilisateur)",
    "Max retention period (days)": "Période de rétention max (jours)",
    "For how long to keep a container before deletion": "Combien de temps garder les conteneurs avant suppression",
    "E-paper type": "Type d'E-paper", "Optional E-ink display": "Affichage E-ink optionnel",
    "LCD type": "Type de LCD", "Optional LCD display": "Affichage LCD optionnel",
    "Screen buttons": "Boutons d'écran", "Enable epaper/lcd screen buttons": "Activer boutons d'écran epaper/lcd",  # OI-85
    "5 buttons shim": "Carte à 5 boutons",
    "Enable Pimoroni buttonshim device (requires e-paper too)": "Activer le buttonshim de Pimoroni (nécessite E-paper aussi)",
    "Witness Angel Gateway URL": "URL de la Passerelle Witness Angel", "Registry of key guardians": "Registre des gardiens de clés",
    "Live preview interval": "Intervalle de preview live",  # OI-85
    "How many seconds between live previews of Picamera (0 to disable)":
        "Combien de secondes entre les aperçus de Picamera (0 pour désactiver)",
    "Libcameravid video params": "Params vidéo libcameravid", "Replace libcameravid video parameters": "Remplacer les paramètres vidéo de libcameravid",
    "Libcameravid audio params": "Params audio libcameravid", "Replace libcameravid audio parameters": "Remplacer les paramètres audio de libcameravid",
    "Raspivid params": "Params raspivid", "Replace raspivid parameters": "Remplacer les paramètres raspivid",
    "Picamera params": "Paramètres picamera", "Json object to replace picamera parameters": "Objet Json pour remplacer les paramètres picamera",
    "Arecord params": "Params arecord", "Replace arecord parameters": "Remplacer les paramètres arecord",
    "Arecord format": "Format arecord", "Replace arecord output format (default: wav)": "Remplace le format de sortie arecord (défaut : wav)",
    "Ffmpeg alsa params": "Params ffmpeg alsa", "Replace ffmpeg alsa parameters": "Remplacer les paramètres ffmpeg alsa",
    "Ffmpeg alsa format": "Format ffmpeg alsa", "Replace ffmpeg alsa output format (default: mp3)": "Remplacer le format de sortie ffmpeg alsa (défaut : mp3)",
    "FFmpeg rtsp params": "Params ffmpeg rtsp", "Replace ffmpeg rtsp audio/video parameters": "Remplacer les paramètres ffmpeg rtsp audio/vidéo",
    "Ffmpeg rtsp format": "Format ffmpeg rtsp", "Replace ffmpeg rtsp output format (default: mp4)": "Remplacer le format de sortie ffmpeg rtsp (défaut : mp4)",
    "Please enter a whole number": "Veuillez saisir un nombre entier",  # NEW (OI-35)
    "Please enter a number": "Veuillez saisir un nombre",
    "The value must be greater than {limit}": "La valeur doit être supérieure à {limit}",
    "The value must be {limit} or more": "La valeur doit être d'au moins {limit}",
    "The gateway URL must start with http:// or https://": "L'URL de la passerelle doit commencer par http:// ou https://",  # NEW (OI-41)
    # Key guardians (02 §5)
    "Please select the key guardians used to secure recordings":
        "Veuillez sélectionner les gardiens de clés utilisés pour sécuriser les enregistrements",
    "Import from USB": "Importer depuis USB", "Import from Web": "Importer depuis Web",
    "Refreshed imported key guardians": "Les gardiens de clé importés ont été rafraîchis",
    "Key Guardian {owner}": "Gardien de Clés {owner}", "Type": "Type", "Key n°": "Clé n°",
    "(private key present)": "(clé privée présente)", "(private key not present)": "(clé privée non présente)",
    "corrupted": "corrompu", "This key guardian is corrupted": "Ce gardien de clés est corrompu",  # NEW (OI-51)
    "No connected authentication devices found": "Aucun périphérique d'authentification trouvé",
    "No initialized authentication devices found": "Aucun périphérique d'authentification initialisé trouvé",
    "Import keys from USB drives": "Import de clés depuis les stockages USB",
    "Do you want to import the private keys (passphrase-protected) as well?":
        "Voulez-vous aussi importer les clés privées (protégées par phrase secrète) ?",
    "{count} new authenticators imported, {updated} updated, {corrupted} skipped because corrupted":
        "{count} nouveaux authentifieurs importés avec succès, {updated} mis à jour, {corrupted} ignoré(s) car corrompu(s)",
    "Import keys from web gateway": "Import de clés depuis la passerelle web",
    "Enter the ID of the authenticator:": "Entrez l'ID de l'authentifieur :", "Authenticator ID": "ID d'authentifieur",
    "Import result: {result}": "Résultat de l'import : {result}",
    "Authentication device(s) updated": "Périphérique(s) d'authentification mis à jour",  # OI-82
    "Authenticator has been imported successfully": "L'authentifieur a été importé avec succès",
    "Please select key guardians to remove": "Veuillez sélectionner les gardiens de clé à supprimer",
    "Key guardian removal confirmation": "Confirmation de suppression de gardiens de clé",
    "Are you sure you want to remove {count} key guardian(s)?": "Êtes-vous sûr de vouloir supprimer {count} gardien(s) de clé ?",  # OI-85
    "Confirm removal": "Confirmer suppression",
    "Selected imported authentication devices were deleted": "Les périphériques d'authentification sélectionnés ont été supprimés",  # OI-82
    # Containers (02 §6)
    "View and manage encrypted containers (selected: {count})": "Voir et gérer les conteneurs chiffrés (Sélectionné: {count})",
    "Refreshed local containers": "Conteneurs locaux rafraichis", "missing": "manquant",
    "Container ID": "ID de conteneur", "Key Guardians used": "Gardiens de Clés utilisés", "type {trustee_type}": "type {trustee_type}",
    "This container cannot be read": "Ce conteneur ne peut pas être lu",  # NEW (OI-88)
    "Please select containers to delete": "Veuillez sélectionner les conteneurs à supprimer",
    "Container deletion confirmation": "Confirmation de suppression de conteneur",
    "Are you sure you want to delete {count} container(s)?": "Êtes-vous sûr de vouloir supprimer {count} conteneur(s) ?",
    "Confirm deletion": "Confirmer suppression", "Prepare decryption": "Préparer le déchiffrement",
    "Please select containers to decrypt": "Veuillez sélectionner les conteneurs à déchiffrer",
    "All authorization requests": "Toutes les demandes d'autorisation",
    # Decryption (02 §7)
    "Containers selected for decryption": "Conteneurs sélectionnés pour le déchiffrement",
    "Summary of related key guardians": "Résumé des gardiens de clés concernés",
    "Refreshed concerned containers": "Liste des conteneurs concernés rafraichie",
    "Key guardian": "Gardien de clés",
    "Status: {found}, passphrase: {passphrase}": "Statut : {found}, phrase secrète : {passphrase}",
    "FOUND": "TROUVÉ", "NOT FOUND": "NON TROUVÉ", "SET": "RENSEIGNÉE", "NOT SET": "NON RENSEIGNÉE",
    "Private keys needed for decryption are present": "Les clés privées nécessaires au déchiffrement sont présentes",
    "Private key(s) missing locally": "Clé(s) privée(s) manquant localement",
    "Private keys needed were not found": "Les clés privées nécessaires sont introuvables",
    "Keypairs used": "Paires de clés utilisées", "Keypair n°{index}": "Paire n°{index}",
    "Add a passphrase": "Ajouter une phrase secrète", "Attempt decryption": "Tenter le déchiffrement",
    "Request remote authorization": "Demander l'autorisation à distance",
    "Last decryption report": "Dernier rapport de déchiffrement", "Add passphrase": "Ajouter une phrase secrète",
    "Enter the passphrase for one of the key guardians": "Entrez la phrase secrète pour l'un des gardiens de clés",
    "Check": "Vérifier", "Validation result: {result}": "Résultat de validation : {result}",
    "Passphrase recognized": "Phrase secrète reconnue",
    "Passphrase doesn't match any relevant private key": "La phrase secrète ne correspond à aucune clé privée pertinente",
    "This passphrase was already entered": "Cette phrase secrète a déjà été saisie",  # NEW (OI-66)
    "No export folder is available on this device": "Aucun dossier d'export n'est disponible sur cet appareil",  # NEW
    "All decryptions failed, see reports": "Tous les déchiffrements ont échoué, voir les rapports",
    "Export folder": "Dossier d'export",
    "{count} out of {total} container(s) have been decrypted": "{count} sur {total} conteneur(s) ont été déchiffrés",
    "Decryption status for {name}: {status}": "Statut du déchiffrement de {name} : {status}",
    "SUCCESS": "SUCCÈS", "FAILURE": "ÉCHEC",
    "No errors/warnings when decrypting the container": "Aucune erreur/avertissement lors du déchiffrement du conteneur",
    "Message": "Message", "Report saved to {path}": "Rapport enregistré dans {path}",  # NEW (OI-71)
    # Remote authorization (02 §8)
    "Send an authorization request to remote key guardian": "Envoyer une demande d'autorisation au gardien de clés distant",
    "Summary": "Résumé", "Container(s) selected": "Conteneur(s) sélectionné(s)", "Gateway url": "Url de la passerelle",
    "Select key guardian(s) to query": "Sélectionnez les gardiens de clé à solliciter",
    "Justify the authorization request": "Entrez le motif de la demande d'autorisation",  # OI-85/86
    "Enter a description (minimum 10 characters):": "Entrez une description (minimum 10 caractères) :",
    "Send my authorization request": "Envoyer ma demande d'autorisation",
    "Operation Report": "Rapport d'Opération", "Successful requests: {ok} out of {total}": "Demandes réussies: {ok} sur {total}",
    "Error Report": "Rapport d'erreurs",
    "Authenticator {uid} does not exist in sql storage": "L'authentifieur {uid} n'existe pas dans le stockage",  # NEW (OI-84)
    "Public key needed does not exist in key storage in {uid} authenticator":
        "La clé publique requise n'existe pas dans le stockage des clés de l'authentifieur {uid}.",
    "View authorization requests submitted for each container": "Voir les demandes d'autorisation soumises pour chaque conteneur",
    "Refreshed authorization requests": "Demandes d'autorisation rafraichies",
    "Container": "Conteneur",  # OI-85: singular
    "for {owner}": "pour {owner}", "Authenticator key": "Clé de l'authentifieur",
    "Authorization request summary": "Résumé de la demande d'autorisation",
    "Symkey decryption status": "Statut de déchiffrement de la Symkey",
    "Submit authorization request": "Envoyer la demande d'autorisation",
    "Decryption report": "Rapport de déchiffrement",
})

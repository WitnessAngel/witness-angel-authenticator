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
}}

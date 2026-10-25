"""French catalog of the components (texts from spec 02; OI-51 typos fixed).

Strings marked NEW do not exist in 1.5 (fixed/decided open issues); their French is ours.
"""

CATALOG = {"fr": {
    # Shell, feedback, top bars
    ": ": " : ",
    "at": "à",
    "Back": "Retour",
    "Refresh": "Rafraîchir",
    "Language": "Langue",
    "Help": "Aide",
    "Settings": "Paramètres",
    "Close": "Fermer",
    "Cancel": "Annuler",
    "Confirm": "Confirmer",
    "OK": "OK",
    "Abnormal error caught: {error}": "Erreur anormale détectée : {error}",
    "Validation error": "Erreur de validation",
    "Success": "Succès",
    "Failure": "Échec",
    "Unknown": "Inconnu(e)",
    "Empty": "Vide",
    "Passphrase": "Phrase secrète",
    "No information available": "Aucune information disponible",
    "External storage is not accessible": "Stockage externe non accessible",
    "Select a folder": "Sélectionner un dossier",  # NEW (in-app browser)
    "Select a file": "Sélectionner un fichier",  # NEW
    "Select this folder": "Sélectionner ce dossier",  # NEW
    "(missing private key)": "(clé privée manquante)",
    'Request "{description}" ({date})': 'Demande "{description}" ({date})',
    # Main screen
    "Authenticators": "Authentifieurs",
    "Please select an authenticator location": "Veuillez sélectionner un emplacement d'authentifieur",
    "User profile": "Profil utilisateur",
    "Stored inside system disk": "Stocké dans le disque système",
    "Custom location": "Emplacement personnalisé",
    "Please select a folder": "Veuillez sélectionner un dossier",
    "Drive {drive} ({label})": "Disque {drive} ({label})",
    "no name": "sans nom",
    "Size: {size}, Filesystem: {filesystem}": "Taille : {size}, Format : {filesystem}",
    "Refreshed authenticator locations": "Emplacements d'authentifieurs rafraichis",
    "No valid location selected": "Aucun emplacement valide sélectionné",
    "Authenticator not initialized": "Authentifieur non initialisé",
    "Authenticator initialized": "Authentifieur initialisé",
    "Please select an authenticator folder": "Veuillez sélectionner un dossier d'authentifieur",
    "Path": "Chemin",
    "Selected folder is invalid!": "Le dossier sélectionné est invalide !",
    "Beware, parent folder is NOT writable!": "Attention, le dossier parent n'est PAS accessible en écriture !",
    "Beware, this is not a folder!": "Attention, ce n'est pas un dossier !",
    "Beware, this folder is NOT writable!": "Attention, ce dossier n'est PAS accessible en écriture !",
    "Invalid authenticator data in {path}": "Données d'authentifieur invalides dans {path}",
    "User": "Utilisateur",
    "Password hint": "Indice de phrase secrète",
    "Creation date": "Date de création",
    "ID": "ID",
    "Keypairs": "Paires de clés",
    "Initialize": "Initialiser",
    "Import": "Importer",
    "Export": "Exporter",
    "Check": "Vérifier",
    "Destroy": "Détruire",
    "Publish": "Publier",
    "Authorizations": "Autorisations",
    "Authenticator management page": "Page de gestion des authentifieurs",
    "On this page, you can manage your authenticators, which are actually digital keychains identified by unique IDs.":
        "Sur cette page, vous pouvez gérer vos authentifieurs, qui sont en fait des trousseaux de clés numériques identifiés par des ID uniques.",
    "These keychains contain both public keys, which can be freely shared, and their corresponding private keys, protected by passphrases, which must be kept hidden.":
        "Ces trousseaux contiennent à la fois des clés publiques, qui peuvent être partagées librement, et les clés privées correspondantes, protégées par des phrases secrètes, qui doivent rester cachées.",
    "Authenticators can be stored in your user profile or in a custom folder, especially at the root of removable devices.":
        "Les authentifieurs peuvent être stockés dans votre profil utilisateur ou dans un dossier personnalisé, notamment à la racine des périphériques amovibles.",
    "You can initialize new authenticators from scratch, import/export them from/to ZIP archives, or check their integrity by providing their passphrases.":
        "Vous pouvez initialiser de nouveaux authentifieurs à partir de zéro, les importer/exporter depuis/vers des archives ZIP, ou vérifier leur intégrité en fournissant leurs phrases secrètes.",
    "Note that if you destroy an authenticator, or lose its passphrase, the WitnessAngel recordings which used it as a trusted third party might not be decryptable anymore.":
        "Notez que si vous détruisez un authentifieur, ou perdez sa phrase secrète, les enregistrements WitnessAngel qui l'utilisaient en tant que tiers de confiance risquent de ne plus pouvoir être déchiffrés.",
    "Export authenticator": "Exporter l'authentifieur",
    "The exported archive should be kept in a secure place.": "L'archive exportée doit être gardée en lieu sûr.",
    "It contains the gateway secret, which gives access to the authorization requests of this authenticator.":  # NEW (OI-21)
        "Elle contient le secret de passerelle, qui donne accès aux demandes d'autorisation de cet authentifieur.",
    "Export successful": "Exportation réussie",
    "Authenticator archive exported to {path}": "L'archive de l'authentifieur a été exportée vers {path}",
    "Import successful": "Importation réussie",
    "Authenticator archive unpacked from {archive}, its integrity has not been checked though.":
        "L'archive d'authentifieur a été décompressée depuis {archive}, son intégrité n'a cependant pas été vérifiée.",
    "The archive does not contain a valid authenticator": "L'archive ne contient pas d'authentifieur valide",  # NEW (OI-20)
    "The target folder is not empty": "Le dossier cible n'est pas vide",  # NEW (OI-20)
    "Sanity check": "Contrôle d'intégrité",
    "Test integrity and passphrase of authenticator": "Tester l'intégrité et la phrase secrète de l'authentifieur",
    "Checkup result: {result}": "Résultat du contrôle : {result}",
    "Keypairs successfully tested: {count}": "Paires de clés testées avec succès : {count}",
    "Keypairs tested: {keypair_count}\nMissing private keys: {missing_private_keys}\nWrong passphrase for keys:  {undecodable_private_keys}":
        "Paires de clés testées : {keypair_count}\nClés privées manquantes : {missing_private_keys}\nMauvaise phrase secrète pour les clés :  {undecodable_private_keys}",
    "Destroy authenticator": "Détruire l'authentifieur",
    "Beware, this might make encrypted data using these keys impossible to decrypt.":
        "Attention, cela peut rendre impossible le déchiffrement des données chiffrées utilisant ces clés.",
    "Deletion is over": "Destruction terminée",
    "Folder {path} has been properly removed.": "Le dossier {path} a été correctement supprimé.",
    "Deletion failed: {error}": "La suppression a échoué : {error}",  # NEW (OI-19)
    "No authenticator found in this folder": "Aucun authentifieur trouvé dans ce dossier",  # NEW (OI-19)
    "This authenticator has no gateway secret and cannot be published or receive requests":  # NEW (OI-17)
        "Cet authentifieur n'a pas de secret de passerelle et ne peut pas être publié ni recevoir de demandes",
    # Creation form
    "Create Authenticator": "Créer un Authentifieur",
    "Authenticator": "Authentifieur",
    "User name": "Utilisateur",
    "Passphrase hint": "Indice de phrase secrète",
    "Please enter a username, passphrase and passphrase hint.":
        "Veuillez entrer un nom d'utilisateur, une phrase secrète et son indice.",
    "Username, passphrase and passphrase hint must not exceed 100 characters":
        "Le nom d'utilisateur, la phrase secrète et son indice ne doivent pas dépasser 100 caractères.",
    "Passphrase must be at least 20 characters long.": "La phrase secrète doit faire au moins 20 caractères de long.",
    "Please wait, generation of cryptographic keys might take a few minutes.":
        "Veuillez attendre, la génération des clés cryptographiques peut prendre quelques minutes.",
    "Initialization successfully completed.": "Initialisation complétée avec succès.",
    "Operation failed, check logs.": "Opération échouée, vérifiez les logs.",
    "Authenticator creation page": "Page de création d'authentifieur",
    "On this page, you can initialize an authenticator inside an empty folder; this authenticator actually consists in metadata files as well as a set of asymmetric keypairs.":
        "Sur cette page, vous pouvez initialiser un authentifieur dans un dossier vide ; cet authentifieur consiste en réalité en des fichiers de métadonnées, ainsi qu'en un ensemble de paires de clés asymétriques.",
    "To proceed, you have to input your user name or pseudo, a long passphrase (e.g. consisting of 4 different words), and a public hint to help your remember your passphrase later.":
        "Pour procéder, vous devez entrer votre nom d'utilisateur ou pseudo, une longue phrase secrète (par exemple, composée de 4 mots différents), et un indice public pour vous aider à vous souvenir de votre phrase secrète plus tard.",
    "You should keep your passphrase somewhere safe (in a digital password manager, on a paper in a vault...), because if you forget any of its aspects (upper/lower case, accents, spaces...), there is no way to recover it.":
        "Vous devez conserver votre phrase secrète en lieu sûr (dans un gestionnaire de mots de passe numérique, sur un papier dans un coffre-fort...), car si vous oubliez l'un de ses aspects (majuscules/minuscules, accents, espaces...), il n'y a aucun moyen de la récupérer.",
    # Publication
    "Publish authenticator": "Publier l'authentifieur",
    "Authenticator path": "Chemin d'authentifieur",
    "Gateway": "Passerelle",
    "Remote status": "Statut distant",
    "Message": "Message",
    "PUBLISHED": "PUBLIÉ",
    "NOT PUBLISHED": "NON PUBLIÉ",
    "The local authenticator does not exist in the remote repository.": "L'authentifieur local n'existe pas dans le dépôt distant.",
    "The remote authenticator is up to date.": "L'authentifieur distant est à jour.",
    "An inconsistency has been detected between the local and remote authenticator.":
        "Une incohérence a été détectée entre l'authentifieur local et distant",
    "Provide the Authenticator ID to users wanting to rely on you as a Key Guardian":
        "Fournissez l'ID d'Authentifieur aux utilisateurs désirant vous ajouter comme Gardien de Clés",
    "Error details": "Détails d'erreurs",
    "Exceeding key(s) in remote": "Clés en excès côté distant",
    "Missing key(s) in remote": "Clés manquantes côté distant",
    "Remote authenticator status has been updated": "Le statut de l'authentifieur distant a été actualisé",
    "Error querying gateway server, please check its url and your connectivity":
        "Erreur lors de l'appel au serveur gateway, veuillez vérifier son url et votre connectivité",
    "This authenticator ID is already published with another secret":  # NEW (OI-29)
        "Cet ID d'authentifieur est déjà publié avec un autre secret",
    "Some private keys are missing, publication is refused (run a Check first)":  # NEW (OI-28)
        "Des clés privées sont manquantes, la publication est refusée (lancez d'abord une Vérification)",
    "This authenticator has no keypair and cannot be published":  # NEW (OI-32)
        "Cet authentifieur n'a aucune paire de clés et ne peut pas être publié",
    "Publish the public keys of this authenticator to {gateway}? A published authenticator can't be modified or deleted.":  # NEW (OI-26)
        "Publier les clés publiques de cet authentifieur sur {gateway} ? Un authentifieur publié ne peut pas être modifié ou supprimé.",
    "Authenticator publishing": "Publication de l'authentifieur",
    "This page allows to publish the PUBLIC part of an authenticator to a remote Witness Angel Gateway, so that other users may import it to secure their recordings.":
        "Cette page permet de publier la partie PUBLIC d'un authentifieur sur une passerelle Witness Angel distante, afin que d'autres utilisateurs puissent l'importer pour sécuriser leurs enregistrements.",
    "For now, a published authenticator can't be modified or deleted.":
        "Pour l'instant, un authentifieur publié ne peut pas être modifié ou supprimé.",
    "In case of incoherences between the keys locally and remotely stored, these errors are displayed here.":
        "En cas d'incohérences entre les clés stockées localement et à distance, ces erreurs sont affichées ici.",
    # Revelation requests
    "Authorization requests": "Demandes d'autorisation",
    "Pending": "En cours",
    "Accepted": "Accepté",
    "Rejected": "Rejeté",
    "Decrypted": "Déchiffré",  # NEW (OI-51, translated statuses)
    "Private key missing": "Clé privée manquante",  # NEW
    "Corrupted": "Corrompu",  # NEW
    "Metadata mismatch": "Métadonnées incohérentes",  # NEW
    "Symkey decryption requests: {count}": "Requêtes de déchiffrement de symkey : {count}",
    "Authorization requests were updated": "Requêtes d'autorisation mises à jour",
    "Authenticator does not exist in remote registry": "L'authentifieur n'existe pas dans le registre distant",
    "The keystore secret of authenticator is not valid": "Le secret de keystore de l'authentifieur n'est pas valide",
    "Authorization requests page": "Page de demandes d'autorisation",
    "This page summarizes the authorization requests that have been sent to the selected authenticator, by people wishing to decrypt some of their containers.":
        "Cette page résume les demandes d'autorisation qui ont été envoyées à l'authentifieur sélectionné, par des personnes souhaitant déchiffrer certains de leurs conteneurs.",
    "These requests can be freely rejected. Else, to accept them, you must input your passphrase, which will be used to load your private keys and generate authorization tokens for the requester.":
        "Les demandes peuvent être librement rejetées. Sinon, pour les accepter, vous devez saisir votre phrase secrète, qui sera utilisée pour charger vos clés privées et générer des jetons d'autorisation pour le demandeur.",
    "For now, it is not possible to change the status of a request which has been accepted or rejected.":
        "Pour l'instant, il n'est pas possible de modifier le statut d'une demande qui a été acceptée ou rejetée.",
    "Authorization request details": "Détails des demandes d'autorisation",
    "Status": "Statut",
    "Description": "Description",
    "Local key for response": "Clé locale pour la réponse",
    "Key of container {uid}": "Clé du conteneur {uid}",
    "Symkey decryption request": "Requête de déchiffrement de la Symkey",
    "Concerned authenticator key": "Clé d'authentifieur concernée",
    "Cryptainer metadata": "Metadata du cryptainer",
    "Decryption status": "Statut de déchiffrement",
    "Accept": "Accepter",
    "Reject": "Rejeter",
    "Enter your authenticator passphrase": "Entrez votre phrase secrète d'authentifieur",
    "This will allow unmasking the requested Symkey parts": "Cela permettra de révéler les morceaux de Symkey requis",
    "Loading of authenticator private key failed (wrong passphrase?)":
        "Le chargement de la clé privée d'authentifieur a échoué (mauvaise phrase secrète ?)",
    "The decryption request was accepted": "La demande de déchiffrement a été acceptée",
    "Do you want to reject this request?": "Voulez-vous rejeter cette requête ?",
    "The authorization request was rejected": "La demande d'autorisation a été rejetée",
    "Unsupported algorithm in this request": "Algorithme non supporté dans cette demande",  # NEW (OI-03)
    "This request contains no key to decrypt": "Cette demande ne contient aucune clé à déchiffrer",  # NEW (OI-03)
    "Only pending requests can be accepted or rejected": "Seules les demandes en cours peuvent être acceptées ou rejetées",  # NEW
}}

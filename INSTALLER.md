# Installer PrépaPilot sur Windows

PrépaPilot 2.26.0, livraison finale préparée le 28 octobre 2026, est prévu pour **Windows 10 (1809 ou ultérieur) et Windows 11, 64 bits**. L’application fonctionne sans installer Python. Les sources sont sur [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot) ; les fichiers seront proposés dans **Releases** après publication de la première version.

Si tu as reçu **PrepaPilot-2.26.0-Setup.exe** directement, ouvre ce fichier puis suis l’installation. Au premier lancement, choisis ta langue et configure ton espace. **Ctrl+F** recherche dans tes documents, notes et repères, **Ctrl+K** ouvre les actions rapides et **F1** affiche l’aide. Une séance reste accessible depuis tous les espaces.

Dans la version 2.26, les reflets et les illustrations suivent la souris depuis toute leur carte, dans chaque espace. Les couleurs et dégradés de Progression sont conservés. Les boutons et champs restent à leur place ; **Réglages → Réduire les animations** arrête ces mouvements.

## Ranger tes cours avec une IA

Dans **Documents → Ranger avec une IA**, clique sur **Préparer un nouvel espace**. L’application crée des copies lisibles, un inventaire avec les chemins exacts, une notice pour ton assistant et un fichier de proposition. **Copier la consigne pour mon IA** fournit le chemin et les instructions à coller dans l’assistant de ton choix. Pour ajouter des cours extérieurs, celui-ci copie les nouveaux fichiers dans `A-importer` et complète la proposition.

Reviens ensuite dans le dialogue : **Lire la proposition** affiche les changements ; **Appliquer le classement** les enregistre après ta vérification. Les originaux sont conservés. PrépaPilot ne fournit pas de moteur IA et ne transmet aucun cours : l’assistant choisi détermine si son modèle fonctionne sur ton ordinateur ou à distance. Le guide `Documentation/Rangement-IA.md` du projet et l’aide **F1** expliquent cette fonction.

## Installation conseillée

1. Ouvre la page GitHub de PrépaPilot, puis **Releases**.
2. Ouvre la dernière version et déplie **Assets** si nécessaire.
3. Télécharge **`PrepaPilot-2.26.0-Setup.exe`**, ou le fichier **`-Setup.exe`** de la version plus récente affichée.
4. Double-clique sur le fichier téléchargé et suis les étapes.
5. Lance **PrépaPilot** depuis le menu Démarrer. Au premier lancement, configure ton espace.

L’installation concerne uniquement ton compte Windows et ne demande pas de droits administrateur. Un raccourci sur le Bureau peut être proposé pendant l’installation.

L’installateur n’est pas signé avec un certificat d’éditeur. Windows peut donc afficher un avertissement. Vérifie que le fichier provient bien de la Release publiée par le propriétaire du projet avant de décider de l’ouvrir.

**Ne choisis pas « Source code (zip) » :** ce téléchargement est destiné au développement et ne contient pas l’application Windows prête à lancer.

## Version portable

La Release propose aussi une archive ZIP portable :

1. Télécharge **`PrepaPilot-2.26.0-Windows-portable.zip`**, ou le ZIP portable de la version plus récente affichée.
2. Dans l’Explorateur Windows, clique droit sur le ZIP, puis **Extraire tout**.
3. Ouvre le dossier extrait et double-clique sur **`PrepaPilot.exe`**.

Conserve tout le dossier avec l’exécutable et **`_internal`**. Lancer l’exécutable depuis l’aperçu du ZIP ne suffit pas. Place le dossier extrait dans un emplacement où ton compte peut écrire, par exemple Documents.

## Sauvegarder et transférer ses données

| Version utilisée | Emplacement des données |
| --- | --- |
| Installée | `%LOCALAPPDATA%\PrepaPilot\data` |
| Portable | Dossier `data` à côté de `PrepaPilot.exe` |

Pour ouvrir l’emplacement installé, colle **`%LOCALAPPDATA%\PrepaPilot`** dans la barre d’adresse de l’Explorateur Windows.

Pour changer de PC ou passer d’un mode à l’autre :

1. Dans l’ancienne version, mets une séance en cours en pause, puis ouvre **Réglages → Exporter toutes mes données**.
2. Conserve le fichier **`.prepapilot`** obtenu et ferme l’application.
3. Installe et ouvre la nouvelle version. Pour un transfert, utilise la même version sur les deux installations.
4. Choisis **Réglages → Importer mes données** et sélectionne le fichier exporté.
5. Lis le récapitulatif avant de confirmer : l’import complet remplace l’espace de destination. Vérifie ensuite tes notes, documents et réglages.

Garde l’ancienne copie et l’export jusqu’à avoir vérifié le transfert. Les fichiers `.prepapilot` contiennent tes données personnelles ; ne les joins pas à une publication GitHub.

## Mettre à jour

La livraison finale est reliée au dépôt public `clmtxx/PrepaPilot`. PrépaPilot recherche les nouvelles versions au démarrage, au plus une fois par jour, et affiche une notification lorsqu’une mise à jour est disponible. Tu peux aussi ouvrir **Réglages → Mises à jour** et lancer une recherche manuelle. Une première Release publique stable est nécessaire pour proposer un téléchargement.

Avec la version installée, clique sur **Télécharger et installer**. Le programme récupère l’installateur de la Release, vérifie son empreinte SHA-256, puis te propose de fermer PrépaPilot pour lancer l’installation. Mets d’abord une séance en cours en pause et enregistre tes modifications. Le nouvel installateur remplace le programme et conserve tes notes, documents et préférences. **Aucune désinstallation n’est nécessaire.**

Tu peux toujours télécharger le nouvel installateur depuis **Releases**, fermer l’application et le lancer toi-même. Un export complet avant une mise à jour reste utile pour conserver une sauvegarde indépendante.

Le portable peut rechercher les versions et ouvrir la page **Releases**. Télécharge le nouveau ZIP portable, extrais-le dans un nouveau dossier, puis utilise l’export et l’import décrits ci-dessus. Garde l’ancien dossier jusqu’à la vérification.

Si l’écran indique que le dépôt de mises à jour n’est pas encore configuré, utilise les fichiers transmis par l’éditeur. Les versions construites par le workflow GitHub du projet reçoivent automatiquement l’adresse du dépôt ; la première Release publique doit avoir été publiée pour qu’une version soit disponible.

## Désinstaller

Ferme PrépaPilot, puis ouvre les **Paramètres Windows → Applications** et désinstalle PrépaPilot. La désinstallation conserve **`%LOCALAPPDATA%\PrepaPilot\data`** pour une future réinstallation. Pour effacer également ton espace, exporte d’abord ce que tu souhaites garder, puis supprime ce dossier toi-même.

Pour une version portable, supprimer son dossier supprime aussi ses données. Fais un export avant de le supprimer.

## Google Drive

Les fonctions locales sont utilisables sans compte Google. L’éditeur prépare une seule fois l’accès commun à PrépaPilot et l’intègre au programme. Avec une version configurée, ouvre **Réglages → Gérer mes sauvegardes Google Drive → Se connecter à Google**, choisis ton compte dans le navigateur et autorise l’application. Tu peux ensuite créer ou retrouver ton dossier de sauvegarde. Tu n’as pas à créer de projet Google Cloud ni à importer de JSON ; les configurations personnelles restent dans **Options avancées** pour les usages qui le nécessitent.

La livraison finale contient le client Google commun, activé en production. Le parcours réel de connexion, sauvegarde et restauration a été vérifié le 28 octobre 2026 avec des données fictives. Aucun compte n’est connecté automatiquement et Google reste facultatif : l’export local `.prepapilot` permet aussi de sauvegarder et transférer ton espace. Sur un autre PC, utilise une version préparée avec le même accès Google et reconnecte ton compte ; ce parcours entre deux machines et l’essai d’un autre compte restent à vérifier. Le [guide Google Drive](Documentation/Google-Drive.md) et la [notice de confidentialité](PRIVACY.md) donnent les détails.

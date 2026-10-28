# PrépaPilot

PrépaPilot aide à organiser ses études : matières et notes, documents, emploi du temps, séances de travail et progression personnelle.

**Version 2.26.0 · 27 octobre 2026 · Windows 10 (1809 ou ultérieur) et Windows 11 · 64 bits**

La version 2.26 étend le suivi de la souris à toutes les cartes : les reflets suivent le pointeur au-dessus des textes, champs et boutons, et les illustrations réagissent depuis toute leur carte. Progression conserve ses couleurs et ses dégradés ; les reflets reprennent chaque couleur d’accent. Les mouvements restent limités et respectent les animations réduites.

Depuis la version 2.25, le parcours Google Drive est simplifié : l’éditeur prépare une seule fois l’accès commun à PrépaPilot, puis chaque utilisateur se connecte et autorise son compte, sans créer de projet Google Cloud ni importer de fichier JSON. La préparation des distributions peut intégrer et exiger cette configuration ; elle reste à fournir pour activer réellement Google dans les livrables locaux.

Les transitions de pages directionnelles en profondeur, les notifications compactes avec copie du texte et pause de lecture, et le repère du champ actif de la version 2.24 sont conservés. Les couleurs équilibrées, le relief et les reflets restent présents. Les animations réduites permettent toujours d’ouvrir directement les pages.

**Documents → Ranger avec une IA** reste disponible : prépare des copies lisibles et une notice pour ton assistant, puis vérifie sa proposition avant de l’appliquer. Le [guide de rangement](Documentation/Rangement-IA.md) explique les étapes.

## Installer sur Windows

1. Ouvre **Releases** sur la page GitHub du projet.
2. Dans la dernière version publiée, télécharge **`PrepaPilot-2.26.0-Setup.exe`** sous **Assets**. Pour une version plus récente, choisis le fichier dont le nom se termine par **`-Setup.exe`**.
3. Ouvre ce fichier et suis l’installation, puis lance **PrépaPilot** depuis le menu Démarrer.

Python et les droits administrateur ne sont pas nécessaires. Le programme s’installe pour ton compte Windows. Le [guide d’installation](INSTALLER.md) explique aussi la version portable, les mises à jour et le transfert des données.

Au premier lancement, choisis **Français** ou **English**. Tu peux ensuite changer de langue dans **Réglages → Langue → Enregistrer mon profil** (**Settings → Language → Save preferences** en anglais). L’interface change immédiatement, sans redémarrage ; tes textes personnels et tes documents restent inchangés. [Installation guide in English](INSTALL.en.md).

Les liens **Source code (zip)** et **Source code (tar.gz)** contiennent le code du projet ; pour installer l’application, choisis le fichier **Setup.exe**.

Les versions publiées par le workflow du projet recherchent les mises à jour au démarrage, au plus une fois par jour. Dans **Réglages → Mises à jour**, tu peux aussi rechercher une version et, avec la version installée, utiliser **Télécharger et installer**. L’installation remplace le programme en conservant tes données, sans désinstallation. Le portable donne accès à la page de téléchargement. Le [guide d’installation](INSTALLER.md#mettre-à-jour) détaille les étapes.

**Première mise en ligne :** ce dossier prépare le dépôt et les fichiers à distribuer. Tant que son propriétaire n’a pas publié de version dans **Releases**, aucun téléchargement public de l’application n’est disponible. La marche à suivre se trouve dans [PUBLIER.md](PUBLIER.md).

## Données personnelles

La [notice de confidentialité](PRIVACY.md) décrit le stockage local, les sauvegardes Google facultatives et les requêtes de mise à jour.

Les données restent sur ton PC. La version installée les enregistre dans **`%LOCALAPPDATA%\PrepaPilot\data`**. La version portable utilise le dossier **`data`** à côté de son exécutable. Les deux modes ont donc des espaces séparés.

Pour changer de PC ou passer du portable à l’installation : **Réglages → Exporter toutes mes données**, puis **Réglages → Importer mes données** dans la nouvelle installation. Le fichier `.prepapilot` transporte ton espace personnel ; garde-le pour toi.

Google Drive reste facultatif. Avec une distribution configurée par l’éditeur, ouvre **Réglages → Gérer mes sauvegardes Google Drive → Se connecter à Google**, puis autorise ton propre compte dans le navigateur. Aucun client Google réel n’est encore fourni dans les livrables locaux de ce projet : si l’accès est indiqué comme non préparé, demande une version configurée au distributeur et utilise l’export local entre-temps. Voir le [guide Google Drive](Documentation/Google-Drive.md).

## Publier ou faire évoluer le projet

Le [compte rendu de validation du 28 octobre 2026](VERIFICATION-PUBLICATION.md) consigne les tests complets et les essais réels d'installation et de mise à jour.

Ce dossier est l’unique dossier à conserver pour préparer le dépôt GitHub. Son **contenu** doit se trouver à la racine du dépôt : le README et `.github` doivent être directement visibles à cet endroit.

| Emplacement | Rôle |
| --- | --- |
| [PUBLIER.md](PUBLIER.md) | Première mise en ligne et prochaines versions |
| [INSTALLER.md](INSTALLER.md) | Guide destiné aux utilisateurs Windows |
| [INSTALL.en.md](INSTALL.en.md) | Installation et transfert des données en anglais |
| `Sources/PrepaPilot` | Code Python, ressources, tests et licences tierces |
| `scripts` et `packaging` | Construction des distributions Windows et de l’installateur |
| `.github/workflows` | Tests et construction sur GitHub |
| `Documentation` | Guide complet et informations de développement |
| `Outils` | Outils de maintenance existants |
| `A-publier` | Fichiers locaux prêts à joindre à une Release, exclus du dépôt |

Les exécutables et archives de l’application vont dans **Releases**. Git conserve les sources et les outils de construction. Le fichier `.gitignore` exclut notamment les données personnelles et les résultats de construction.

Les licences des composants tiers sont conservées dans `Sources/PrepaPilot/licenses`. Aucune nouvelle licence du code de PrépaPilot n’est choisie par ce dossier ; ce choix reste au propriétaire du projet.

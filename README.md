# PrépaPilot

PrépaPilot aide à organiser ses études : matières et notes, documents, emploi du temps, séances de travail et progression personnelle.

**Version 2.26.1 · publiée le 29 octobre 2026 · Windows 10 (1809 ou ultérieur) et Windows 11 · 64 bits**

La version 2.26 étend le suivi de la souris à toutes les cartes : les reflets suivent le pointeur au-dessus des textes, champs et boutons, et les illustrations réagissent depuis toute leur carte. Progression conserve ses couleurs et ses dégradés ; les reflets reprennent chaque couleur d’accent. Les mouvements restent limités et respectent les animations réduites.

La livraison finale intègre l’accès Google commun à PrépaPilot, activé en production et vérifié le 28 octobre 2026. Google Drive reste facultatif : chaque utilisateur connecte et autorise son propre compte, sans créer de projet Google Cloud ni importer de fichier JSON. Aucun compte n’est connecté d’office.

Les transitions de pages directionnelles en profondeur, les notifications compactes avec copie du texte et pause de lecture, et le repère du champ actif de la version 2.24 sont conservés. Les couleurs équilibrées, le relief et les reflets restent présents. Les animations réduites permettent toujours d’ouvrir directement les pages.

**Documents → Ranger avec une IA** reste disponible : prépare des copies lisibles et une notice pour ton assistant, puis vérifie sa proposition avant de l’appliquer. Le [guide de rangement](Documentation/Rangement-IA.md) explique les étapes.

## Installer sur Windows

1. Ouvre **[Releases](https://github.com/clmtxx/PrepaPilot/releases)** sur le dépôt public du projet.
2. Dans la dernière version publiée, télécharge **`PrepaPilot-2.26.1-Setup.exe`** sous **Assets**. Pour une version plus récente, choisis le fichier dont le nom se termine par **`-Setup.exe`**.
3. Ouvre ce fichier et suis l’installation, puis lance **PrépaPilot** depuis le menu Démarrer.

Python et les droits administrateur ne sont pas nécessaires. Le programme s’installe pour ton compte Windows. Le [guide d’installation](INSTALLER.md) explique aussi la version portable, les mises à jour et le transfert des données.

Au premier lancement, choisis **Français** ou **English**. Tu peux ensuite changer de langue dans **Réglages → Langue → Enregistrer mon profil** (**Settings → Language → Save preferences** en anglais). L’interface change immédiatement, sans redémarrage ; tes textes personnels et tes documents restent inchangés. [Installation guide in English](INSTALL.en.md).

Les liens **Source code (zip)** et **Source code (tar.gz)** contiennent le code du projet ; pour installer l’application, choisis le fichier **Setup.exe**.

Les versions publiées par le workflow du projet recherchent les mises à jour au démarrage, au plus une fois par jour. Dans **Réglages → Mises à jour**, tu peux aussi rechercher une version et, avec la version installée, utiliser **Télécharger et installer**. L’installation remplace le programme en conservant tes données, sans désinstallation. Le portable donne accès à la page de téléchargement. Le [guide d’installation](INSTALLER.md#mettre-à-jour) détaille les étapes.

**Version stable :** [PrépaPilot 2.26.1](https://github.com/clmtxx/PrepaPilot/releases/tag/v2.26.1) est publiée et corrige le téléchargement des mises à jour depuis GitHub. Les **913 contrôles GitHub**, la construction et la vérification de l’installateur ont réussi. Si tu utilises 2.26.0, télécharge cet installateur manuellement pour cette première mise à jour. Le lien [dernière version stable](https://github.com/clmtxx/PrepaPilot/releases/latest) permet de retrouver les prochaines publications. Les distributions incluent le client Google commun, sans compte connecté. La procédure se trouve dans [PUBLIER.md](PUBLIER.md).

## Données personnelles

La [notice de confidentialité](PRIVACY.md) décrit le stockage local, les sauvegardes Google facultatives et les requêtes de mise à jour.

Les données sont enregistrées sur ton PC. La version installée utilise **`%LOCALAPPDATA%\PrepaPilot\data`**. La version portable utilise le dossier **`data`** à côté de son exécutable. Les deux modes ont donc des espaces séparés ; une sauvegarde Google envoie les catégories que tu choisis vers ton Drive.

Pour changer de PC ou passer du portable à l’installation : **Réglages → Exporter toutes mes données**, puis **Réglages → Importer mes données** dans la nouvelle installation. Le fichier `.prepapilot` transporte ton espace personnel ; garde-le pour toi.

Pour utiliser Google Drive, ouvre **Réglages → Gérer mes sauvegardes Google Drive → Se connecter à Google**, puis autorise ton propre compte dans le navigateur. Le 28 octobre 2026, une connexion réelle, une première sauvegarde, une seconde sans changement et une restauration exacte des données et documents ont réussi avec des données fictives. L’essai sur un autre PC et avec un autre compte reste à réaliser. Voir le [guide Google Drive](Documentation/Google-Drive.md).

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

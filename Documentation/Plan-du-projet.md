# Plan du projet PrépaPilot

## Dossier principal

```text
PrépaPilot/
├── LIRE-MOI.md                    Commencer ici
├── Ouvrir PrepaPilot.cmd          Lanceur Windows
├── Application/
│   └── PrepaPilot/
│       ├── PrepaPilot.exe         Application compilée
│       ├── _internal/             Bibliothèques nécessaires
│       ├── GUIDE.md               Guide joint à l’application
│       ├── VERIFICATION.md        Compte rendu de validation
│       └── data/                  Données créées lors de l’utilisation
├── Documentation/
│   ├── Guide-PrepaPilot.md        Fonctions et utilisation
│   ├── Plan-du-projet.md          Ce document
│   ├── Developpement.md           Développer et reconstruire
│   ├── Rangement-IA.md            Ranger ses cours avec un assistant
│   ├── Evolutions-proposees.md    Idées soumises à validation
│   └── Verification.md            Tests et contrôles
├── Sources/
│   └── PrepaPilot/                Code actuel uniquement
├── Outils/                       Maintenance et préparation du partage
└── Partage/                      Distributions générées
```

`data` n’existe pas dans une copie vierge : il apparaît au premier lancement. `Partage` n’est jamais recopié dans sa propre distribution.

## Lire le code

| Dans Sources/PrepaPilot | Contenu |
| --- | --- |
| `lancer.py` | Démarrage depuis Python |
| `mpsi_desktop` | Interface Qt, configuration, documents, emploi du temps, progression et transferts |
| `mpsi_core` | Stockage et calculs utilisés par l’application |
| `assets` | Icônes et ancien emploi du temps conservé pour la compatibilité |
| `tests` | Tests automatisés |
| `licenses` | Licences des dépendances distribuées |
| `requirements.txt` | Dépendances pour exécuter les sources |
| `requirements-dev.txt` | Dépendances de développement et de compilation |
| `build_windows.py` | Construction de l’application Windows |

Les anciennes applications et prototypes ne sont pas mélangés au code actif.

Le moteur `mpsi_desktop/progression.py` calcule les bilans depuis le journal. L’écran `mpsi_desktop/progression_page.py` présente les périodes et les objectifs. Les tests correspondants sont dans `tests/test_progression*.py`. Les calculs ne créent pas d’activités et ne réécrivent pas le journal.

Les illustrations et la couronne du score sont dans `mpsi_desktop/progression_visuals.py`. Le graphique interactif est dans `mpsi_desktop/progression_chart.py`. Ces éléments sont dessinés par Qt et ne nécessitent aucun téléchargement d’images.

Les illustrations des autres pages sont regroupées dans `mpsi_desktop/page_figures.py`. Les bandeaux, titres et cartes colorées communs sont dans `mpsi_desktop/page_chrome.py`. Ils partagent les thèmes et les préférences d’animation de l’application.

Le démarrage animé est géré par `mpsi_desktop/startup.py` et dessiné dans `mpsi_desktop/startup_splash.py`. Le lanceur démarre cet écran avant les imports lourds ; il fonctionne dans un processus temporaire distinct, sans accès aux données, puis se ferme lorsque l’application est prête.

## Les cours et leur espace de rangement IA

Le dialogue **Documents → Ranger avec une IA** affiche l’emplacement réel des données. Dans cette copie portable, il s’agit de `Application/PrepaPilot/data` ; une installation Windows utilise `%LOCALAPPDATA%/PrepaPilot/data`.

| Dans le dossier `data` | Rôle |
| --- | --- |
| `mpsi.sqlite3` | Bibliothèque, titres, matières, types et dossiers de l’application |
| `documents/<identifiant>.<extension>` | Fichiers gérés par PrépaPilot ; leur chemin reste stable lors du classement |
| `Rangement-IA/session-…/Bibliotheque` | Copies de consultation aux noms lisibles, regroupées par dossier, matière et type |
| `Rangement-IA/session-…/catalogue.json` | Correspondance entre les copies, les originaux et leurs informations de classement |
| `Rangement-IA/session-…/NOTICE-IA.md` et `AGENTS.md` | Instructions pour l’assistant chargé du rangement |
| `Rangement-IA/session-…/proposition.json` | Proposition à vérifier puis appliquer dans l’application |
| `Rangement-IA/session-…/A-importer` | Copies des nouveaux cours à ajouter par la proposition |

Les dossiers affichés dans Documents sont enregistrés dans la bibliothèque ; les copies lisibles permettent à un assistant de comprendre ce classement sans déplacer les originaux. Chaque préparation crée sa propre session. Les fichiers de travail d’une session sont distincts des sauvegardes de la bibliothèque. Le guide `Documentation/Rangement-IA.md` décrit leur utilisation.

Le module `mpsi_desktop/local_organization.py` prépare les fichiers, vérifie les propositions et applique les changements. `mpsi_desktop/local_organization_dialog.py` présente les étapes et l’aperçu. Les tests sont dans `tests/test_local_organization*.py`.

## Espace local, séparé du projet

Les sauvegardes Google Drive sont gérées par `mpsi_desktop/cloud_backup.py` (sélection, déduplication, restauration), `google_auth.py` (connexion), `google_drive.py` (transferts), `cloud_dialog.py` (interface) et `cloud_preferences.py` (rappels). Les identifiants de compte restent dans `Application/PrepaPilot/data/cloud`, exclus des exports et des distributions. `Documentation/Google-Drive.md` distingue la préparation faite une fois par l’éditeur et la connexion simple des utilisateurs. L’option de construction `--google-oauth-client CHEMIN` intègre une configuration de bureau commune dans `assets/google-oauth-client.json`, sans jeton de compte ; `--require-google-drive` permet d’exiger sa présence avant distribution. Chaque utilisateur autorise ensuite son propre compte depuis le navigateur.

À côté du projet, **« nom du projet - fichiers locaux »** rassemble ce qui reste sur la machine de travail :

| Dossier local | Contenu |
| --- | --- |
| `Archives` | Anciennes versions, code retiré et anciennes distributions |
| `Python` | Environnement Python propre à cette machine |
| `Construction` | Fichiers intermédiaires de compilation |
| `Livraison/PrepaPilot` | Dernière compilation avant installation |
| `Transactions` | Fichiers temporaires d’une mise à jour |
| `Verification/Interface` | Captures de contrôle de l’interface |
| `Verification/Historique` | Anciennes traces de validation |
| `References-personnelles` | Documents de référence d’origine |
| `Donnees-developpement` | Données séparées pour tester les sources |

Ces dossiers sont créés selon les besoins. L’application livrée fonctionne sans cet espace local. Un développeur sur une autre machine recrée son environnement Python depuis les fichiers de dépendances.

## Quel fichier transmettre ?

- **Projet complet :** `Partage/PrepaPilot-Projet` ou son ZIP. Le manifeste permet de contrôler les fichiers reçus.
- **Application seule :** `Partage/PrepaPilot-Windows.zip`.
- **Données personnelles vers un autre PC :** le fichier `.prepapilot` exporté depuis les Réglages.

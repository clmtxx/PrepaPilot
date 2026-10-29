# Développer PrépaPilot

L’application compilée fonctionne sans Python. Cette page concerne la modification du code.

## Construire la distribution GitHub

Le dossier **PrepaPilot-GitHub** est autonome : son README est l’entrée du dépôt public [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot), dont les sources ont été envoyées sur `main` le 28 octobre 2026. La version corrective **2.26.1** est préparée le 29 octobre pour corriger le téléchargement des mises à jour. Les fichiers publiés se trouvent sur la page [dernière version](https://github.com/clmtxx/PrepaPilot/releases/latest) ; le [rapport de publication](https://github.com/clmtxx/PrepaPilot/blob/main/VERIFICATION-PUBLICATION.md) précise leurs vérifications. Depuis sa racine, utilise Python 3.12 64 bits et [Inno Setup 6.3 ou ultérieur](https://jrsoftware.org/isdl.php) :

```powershell
py -3.12 -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r ./Sources/PrepaPilot/requirements-dev.txt
& ./.venv/Scripts/python.exe -B ./scripts/build_release.py --repository proprietaire/PrepaPilot
```

La construction crée dans **dist** un installateur, une archive portable et leurs empreintes SHA-256. Elle teste l’exécutable dans une copie temporaire avant de préparer ces fichiers. Avec `--iscc`, on peut indiquer le chemin exact du compilateur Inno Setup. L’installateur utilise le dossier de programmes de l’utilisateur et conserve les données dans `%LOCALAPPDATA%/PrepaPilot/data` ; le portable garde son dossier `data` à côté de l’exécutable. Les explications de publication sont dans **PUBLIER.md** à la racine du dépôt.

Remplace `proprietaire/PrepaPilot` par le nom exact de ton dépôt GitHub public. Le workflow le fournit automatiquement avec `github.repository`, sans secret. Le builder injecte uniquement `{"repository":"proprietaire/PrepaPilot"}` dans une copie temporaire des ressources `assets/update-channel.json` ; les sources restent inchangées. Un fichier public de ce nom peut aussi être fourni avant construction ; `--repository` prend alors priorité. Les URL complètes, les jetons et les autres clés JSON sont refusés. Sans option ni fichier public, l’application fonctionne et indique que les mises à jour ne sont pas encore configurées. L’option `--repository` impose une compilation complète et ne se combine pas à `--app-dir`.

La recherche utilise uniquement les Releases stables du dépôt public configuré. Une nouvelle version doit être publiée avec son tag `vX.Y.Z`, son installateur `PrepaPilot-X.Y.Z-Setup.exe` et le fichier `SHA256SUMS.txt` de la même construction. Le téléchargement n’est lancé qu’à la demande de l’utilisateur ; l’empreinte est vérifiée avant l’ouverture de l’installateur. Le mode portable ouvre la page de publication et conserve sa procédure de transfert. Les tests simulent GitHub et les téléchargements ; `--self-test` ne recherche pas de mises à jour sur le réseau.

### Intégrer l’accès Google dans l’installateur

Le distributeur prépare **un projet Google et un client OAuth Application de bureau communs à PrépaPilot**, puis conserve ce client pour les versions suivantes. Les étapes dans la console Google et la préparation d’une diffusion en production sont dans [Google Drive · préparation éditeur](Google-Drive.md#éditeur--préparer-une-seule-fois-laccès-commun). Cette opération n’est pas demandée à chaque utilisateur : avec l’installateur préparé, chacun clique sur **Se connecter à Google** et autorise son propre compte.

Depuis le dépôt GitHub autonome, fournis la configuration téléchargée à la construction :

```powershell
& ./.venv/Scripts/python.exe -B ./scripts/build_release.py --repository proprietaire/PrepaPilot --google-oauth-client 'C:/Configuration-PrepaPilot/client-google.json' --require-google-drive
```

Adapte le dépôt et le chemin. Les deux constructeurs, `scripts/build_release.py` et `Sources/PrepaPilot/build_windows.py`, acceptent `--google-oauth-client CHEMIN` et `--require-google-drive`. L’option `--google-oauth-client` choisit le fichier à intégrer ; `--require-google-drive` impose qu’une configuration valide soit disponible et interrompt la construction si elle manque. Sans cette exigence, une construction de développement peut rester utilisable avec les fonctions locales seulement.

Le JSON est validé puis réduit aux informations du client de bureau : `installed.client_id` et `installed.client_secret`. L’intégration se fait dans une copie temporaire des ressources, à l’emplacement `assets/google-oauth-client.json`, sans modifier les sources. Avec `--app-dir`, la préparation des ressources se fait aussi sur une copie du programme fourni. Il ne faut jamais fournir `credentials.bin`, un jeton d’accès ou le dossier personnel `data/cloud` à la construction.

Le fichier intégré identifie l’application, et non un compte déjà connecté. Chaque utilisateur se connecte dans son propre navigateur ; ses jetons restent dans ses données locales. Une configuration personnelle importée depuis les options avancées prend la priorité sur celle du programme.

Dans le workflow GitHub, les publications par tag exigent cette configuration ; les constructions manuelles de développement peuvent l’omettre. **État vérifié le 28 octobre 2026 :** le client OAuth de bureau commun est créé, l’application Google est En production et `GOOGLE_OAUTH_CLIENT_JSON` est enregistré comme secret du dépôt `clmtxx/PrepaPilot`. Ce secret contient la configuration du client, jamais les jetons d’un utilisateur. Pour une autre configuration, fournis ce JSON dans les variables ou secrets attendus par le workflow.

Un essai réel avec des données fictives a réussi : connexion PKCE, protection locale DPAPI, première sauvegarde de 14 objets, seconde sauvegarde sans envoi avec 14 objets réutilisés et aucune nouvelle version, puis restauration exacte des données et documents dans un espace distinct. Les jetons de l’essai ont été effacés. L’essai sur un autre PC et avec un autre compte reste à effectuer. Toute nouvelle construction doit être vérifiée avant diffusion. Ces contrôles Google sont distincts des contrôles de construction et de téléchargement de chaque version, consignés dans le rapport de publication.

Google Drive reste facultatif. Aucun compte n’est connecté d’office dans une distribution ; chaque utilisateur autorise son propre compte. Les [informations de confidentialité](https://github.com/clmtxx/PrepaPilot/blob/main/PRIVACY.md) décrivent les données transférées et leur conservation.

Les procédures suivantes concernent l’ancien espace de travail portable, avec ses dossiers **Application**, **Outils** et l’environnement Python voisin. Elles restent disponibles pour sa maintenance.

## Préparer Python

Sous Windows, utilise Python 3.12. Ouvre PowerShell dans le dossier principal du projet :

```powershell
$projetPrepa = (Get-Location).Path
$espacePrepa = Join-Path (Split-Path -Parent $projetPrepa) ((Split-Path -Leaf $projetPrepa) + ' - fichiers locaux')
py -3.12 -m venv (Join-Path $espacePrepa 'Python')
$pythonPrepa = Join-Path $espacePrepa 'Python/Scripts/python.exe'
& $pythonPrepa -m pip install -r './Sources/PrepaPilot/requirements-dev.txt'
```

Cet environnement reste à côté du projet. Il n’est pas transmis : ses chemins dépendent de la machine.

## Exécuter et tester

```powershell
& $pythonPrepa -B './Outils/lancer_sources.py'
Push-Location './Sources/PrepaPilot'
& $pythonPrepa -B -m unittest discover -s tests -v
Pop-Location
& $pythonPrepa -B -m unittest discover -s './Outils' -p 'test_*.py' -v
```

Le lanceur des sources utilise `Donnees-developpement` dans l’espace local, indépendamment des données de l’application installée. L’option `-B` évite la création de caches dans le code.

Pour les captures de contrôle :

`Outils/verifier_suivi_souris.py` contrôle le suivi du pointeur de la version 2.26 sur les cartes et leurs illustrations, dans les différentes pages et les deux thèmes, avec des données fictives. Les résultats vont dans `.local/Verification/Suivi-souris-2.26`. Le contrôle couvre le passage sur les textes, champs et boutons, la conservation des couleurs de Progression, les clics et la saisie, ainsi que l’arrêt des effets quand une carte est masquée, désactivée ou que les animations sont réduites. Les reflets suivent le pointeur avec une amplitude bornée, sans déplacer les contrôles ; les palettes et dégradés de base de Progression sont conservés.

`Outils/verifier_navigation.py` contrôle la navigation 2.24 avec des données fictives : panneaux directionnels, continuité des clics rapides, interruption par le clavier ou la souris, brouillons et défilement, notifications longues et focus des champs. Il produit un GIF et des planches dans `.local/Verification/Navigation-2.24`, dans les deux langues, thèmes et tailles. Les captures de transition sont bornées à 2 millions de pixels ; elles sont prises à la navigation et réutilisées pendant les images animées. `test_page_motion.py`, `test_interface_feedback.py` et `test_notice_card.py` couvrent les nouveaux comportements. Les mesures de capture décrivent uniquement le processus et la machine testés.

`Outils/verifier_finitions.py` contrôle les matériaux de l’interface 2.22 : tranches, reflets, scintillements, pression et retour élastique. Il enregistre les pages avec des données fictives, des planches d’animation et un aperçu GIF dans `.local/Verification/Finitions`. Les animations sont finies, leur rendu ne modifie pas les zones de clic et les effets s’arrêtent avec les animations réduites. Les tests `test_button_material.py` et `test_crafted_surfaces.py` complètent les contrôles de mouvement et de cache existants.

```powershell
& $pythonPrepa -B './Outils/verifier_interface.py'
```

Les images sont enregistrées dans `Verification/Interface-2.16` de l’espace local, avec des données fictives. Les contrôles couvrent les deux thèmes, deux tailles de fenêtre, les aperçus et les nouveaux objets en relief.

Les surfaces décoratives `AccentCard` réutilisent un fond borné à 220 000 pixels par carte ; textes et contrôles restent à leur résolution native. Les aperçus plafonnent aussi leur capture intermédiaire à 500 000 pixels, tandis que les transitions restent limitées à deux images de 2 millions de pixels. Les animations d’orbites et de lumière ne reconstruisent pas les dessins à chaque image. `NavigationAccent` ne déplace que son propre trait décoratif, sans modifier les boutons. Les nouveaux effets sont finis, sans boucle ni requête de données pendant leur lecture, et respectent les animations réduites.

Pour contrôler les nouveaux champs de notes et les deux graphiques, lance `& $pythonPrepa -B './Outils/verifier_notes.py'`. Les captures clair/sombre, à 1 360 × 900 et 1 024 × 680, vont dans `Verification/Notes` de l’espace local. Les données fictives couvrent plusieurs barèmes, les valeurs inconnues, une moyenne de zéro et des effectifs variables. Le contrôle inclut les messages d’erreur du formulaire.

Pour contrôler les séances de travail, lance `& $pythonPrepa -B './Outils/verifier_seances.py'`. Les captures de l’accueil, de la préparation et du bilan vont dans `Verification/Seances` de l’espace local. L’outil utilise une base temporaire et une horloge simulée pour séparer deux périodes de travail par une pause. Il couvre les thèmes clair et sombre, les fenêtres de 1 360 × 900 et 1 024 × 680, le débordement horizontal de l’accueil et la hauteur des dialogues. Les tests `tests/test_focus_session.py`, `tests/test_focus_dialogs.py` et `tests/test_focus_dashboard.py` vérifient le comportement et l’intégration au journal.

Pour les dossiers de documents, lance `& $pythonPrepa -B './Outils/verifier_dossiers.py'`. Les captures sont conservées dans `Verification/Dossiers` de l’espace local. L’outil utilise des fichiers fictifs et contrôle les deux thèmes, la recherche globale, les noms de dossiers longs, les deux tailles de fenêtre et les dialogues de rangement. Les tests `tests/test_document_folders_*.py` couvrent le stockage, les transferts et l’interface.

La passerelle de rangement IA est dans `mpsi_desktop/local_organization.py` et son dialogue dans `mpsi_desktop/local_organization_dialog.py`. Depuis `Sources/PrepaPilot`, lance `python -B -m unittest discover -s tests -p 'test_local_organization*.py' -v` avec l’environnement du projet. Les sessions de travail restent dans `data/Rangement-IA`, séparées des originaux de `data/documents`. Préserver cette séparation permet aux exports et aux sauvegardes Google Drive de conserver leur format. Toute application de proposition doit valider le lot complet, vérifier qu’il correspond encore à la bibliothèque et à l’aperçu, puis enregistrer les changements dans une seule transaction. La notice destinée à l’assistant est générée dans chaque session ; le guide public est `Documentation/Rangement-IA.md`.

Pour comparer les performances avec un jeu reproductible de 2 000 notes, 600 documents et 400 jours d’activités :

```powershell
& $pythonPrepa -B './Outils/mesurer_fluidite.py' --label ma-mesure
```

La base temporaire est indépendante des données personnelles. Le rapport JSON est enregistré dans `Verification/Fluidite` de l’espace local voisin. Il donne les durées médianes et les nombres de requêtes SQL ; il mesure Qt hors écran, sans constituer une garantie de fréquence d’affichage sur une autre machine. Les mesures doivent être comparées sur le même PC, avec une charge comparable. Depuis `Sources/PrepaPilot`, `python -B -m tests.benchmark_visual_rendering` compare séparément les illustrations vectorielles et leurs calques réutilisés dans le même processus.

## Construire et livrer

`Outils/verifier_succes.py` vérifie l’affichage des quêtes, du sport, des médailles et de l’historique avec des données temporaires. Les captures restent dans `Verification/Succes-2.15.1` de l’espace local voisin. Le moteur `mpsi_desktop/achievements.py` sépare le calcul du journal, la reconnaissance transactionnelle des récompenses et leur présentation. Les identifiants déterministes empêchent de réattribuer les XP ; les lectures répétées de l’interface réutilisent le rapport en mémoire tant que les données et la minute courante n’ont pas changé. Les tests `test_achievements.py`, `test_achievement_integration.py`, `test_achievement_visuals.py` et `test_achievement_transfers.py` couvrent le calcul, l’intégration, le rendu et les sauvegardes. Les catalogues historiques restent acceptés par le registre ; les nouveaux paliers de travail ont des identifiants distincts. Modifier un barème ne doit jamais transformer une ancienne récompense en validation d’un objectif plus élevé.

1. Construis avec `& $pythonPrepa -B './Sources/PrepaPilot/build_windows.py' --repository proprietaire/PrepaPilot`, en remplaçant le dépôt par le tien ou en omettant cette option avant la première publication. Les intermédiaires vont dans `Construction` et le programme dans `Livraison/PrepaPilot`, tous deux dans l’espace local.
2. Lance le programme de livraison avec `--self-test` pour vérifier son fonctionnement avec une base temporaire.
3. Ferme l’application utilisée, puis lance `& $pythonPrepa -B './Outils/mettre_a_jour_application.py' --archive-label 'PrepaPilot-v2.11.0'`, en adaptant ce numéro à la version remplacée.
4. Crée les distributions avec `& $pythonPrepa -B './Outils/partager_application.py'`, puis `& $pythonPrepa -B './Outils/preparer_projet.py'`.
5. Contrôle le ZIP Windows avec `& $pythonPrepa -B './Outils/verifier_distribution.py'`, puis le projet complet avec la même commande suivie de `--projet`.

La mise à jour conserve `Application/PrepaPilot/data` et archive les anciens binaires dans l’espace local. Les archives portent des noms uniques. Une distribution complète existante est également archivée avant son remplacement.

## Maintenir les documents

Pour maintenir l’accès Google Drive, suis `Documentation/Google-Drive.md`. Le code utilise uniquement la bibliothèque standard Python pour OAuth et l’API Drive ; aucune dépendance supplémentaire n’est nécessaire. Le parcours conseillé utilise `--google-oauth-client CHEMIN --require-google-drive` à la construction, comme expliqué plus haut. Le fichier facultatif `Sources/PrepaPilot/assets/google-oauth-client.json` reste reconnu pour les projets déjà configurés ; il identifie seulement l’application. Les jetons d’utilisateur dans `data/cloud` ne sont jamais intégrés. Une construction volontairement dépourvue de client conserve les fonctions locales et indique que l’accès Google n’y est pas préparé. Les tests réseau automatisés utilisent des réponses simulées ; l’essai réel du 28 octobre 2026 est décrit plus haut et dans le guide Google Drive. Il ne remplace pas la vérification d’une nouvelle distribution ni l’essai restant sur un autre PC et avec un autre compte.

`Outils/verifier_google.py` produit les captures de l’interface et du rappel avec un état fictif, sans réseau. Le contrôle compilé `--self-test` vérifie également ce dialogue et le rappel hebdomadaire sans ouvrir de connexion Google.

Le guide utilisateur est dans `Sources/PrepaPilot/README.md`, avec une copie dans `Documentation/Guide-PrepaPilot.md`. Les outils de partage le joignent à l’application. Le compte rendu de validation suit le même principe avec `Sources/PrepaPilot/VERIFICATION.md` et `Documentation/Verification.md`.

Les chemins des outils sont définis dans `Outils/chemins.py` et calculés depuis le dossier du projet, sans chemin personnel codé en dur.

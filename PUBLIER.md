# Mettre PrépaPilot à disposition sur GitHub

La version Windows **2.26.1 a été publiée le 29 octobre 2026** : [téléchargements](https://github.com/clmtxx/PrepaPilot/releases/tag/v2.26.1). Le dépôt public [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot) contient les sources sur `main`. Le client Google commun est en production, son secret de construction est enregistré dans GitHub et le parcours réel de sauvegarde/restauration a réussi. Ce guide conserve les étapes de première publication et sert de référence pour les prochaines versions.

La publication automatique par tag exige l’accès Google commun valide. Les distributions finales sont construites avec `clmtxx/PrepaPilot` pour les mises à jour et le client OAuth de bureau commun, sans compte connecté. Google reste facultatif pour chaque utilisateur. La [notice de confidentialité](PRIVACY.md) décrit ces échanges.

## 1. Mettre le dossier sur GitHub

**Déjà effectué pour PrépaPilot :** le dépôt public `clmtxx/PrepaPilot` existe et ses sources sont sur `main`. Les instructions de première création ci-dessous restent une référence ; pour ce dépôt, envoie les prochaines modifications sur la branche existante.

Utilise [GitHub Desktop](https://desktop.github.com/) pour envoyer le projet : il conserve les dossiers tels que `.github` et applique les exclusions de `.gitignore`.

1. Connecte GitHub Desktop à ton compte.
2. Choisis **File → Add local repository**, puis sélectionne **`PrepaPilot-GitHub`**. Si ce dossier n’est pas encore un dépôt, utilise le lien **create a repository** proposé. Vérifie que le chemin final reste ce dossier, sans créer un second `PrepaPilot-GitHub` à l’intérieur.
3. Conserve le `.gitignore` fourni. Ne fais pas ajouter une licence automatiquement : la licence du code reste ton choix.
4. Vérifie la liste des fichiers avant le premier enregistrement : `README.md`, `Sources`, `scripts`, `packaging`, `Documentation`, `Outils` et **`.github/workflows`** doivent être présents. **`A-publier`**, `dist`, les exécutables et tes données doivent être absents.
5. Si des changements restent à enregistrer, saisis un titre comme « Préparer la diffusion Windows », puis clique sur **Commit to main** (ou le nom de ta branche).
6. Clique sur **Publish repository**. Choisis le nom du dépôt, par exemple `PrepaPilot`. Pour que chacun puisse télécharger l’application, décoche **Keep this code private**, puis publie.

Le dépôt créé doit être vide avant ce premier envoi. Si tu as déjà créé un dépôt vide sur le site GitHub, clone-le avec GitHub Desktop, puis copie **le contenu** de `PrepaPilot-GitHub` à sa racine avant le premier commit. Dans l’Explorateur, affiche les éléments masqués pour inclure `.github` et `.gitignore`. Le README doit être à la racine, sans dossier supplémentaire autour.

Ces étapes suivent la [procédure GitHub Desktop](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop). L’envoi par **Upload files** dans le navigateur est moins adapté à ce projet : il demande de contrôler les fichiers exclus et les dossiers masqués à la main, et il est limité à 100 fichiers par envoi et 25 Mio par fichier. Voir les [limites et étapes d’envoi](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository).

## 2. Préparer une seule fois l’accès Google de l’application

**État au 28 octobre 2026 :** le client commun réel est créé, l’application Google est en production et **`GOOGLE_OAUTH_CLIENT_JSON`** est enregistré comme secret GitHub Actions. Une connexion réelle, une sauvegarde de 14 objets, une seconde sans nouvel envoi ni nouvelle version et une restauration exacte vers un espace fictif distinct ont réussi. Les jetons de l’essai ont été effacés. Un autre PC et un autre compte restent à tester.

Crée un projet Google et un client OAuth **Application de bureau** communs à PrépaPilot, avec Google Drive API et la seule autorisation `drive.file`. Le [guide Google Drive](Documentation/Google-Drive.md#éditeur--préparer-une-seule-fois-laccès-commun) détaille la préparation, les utilisateurs test, le passage en production et les vérifications d’identité demandées par Google.

Dans le dépôt GitHub, ouvre **Settings → Secrets and variables → Actions**, puis choisis l’un des deux emplacements :

- **Variables → New repository variable**, avec le nom **`GOOGLE_OAUTH_CLIENT_JSON`** ;
- ou **Secrets → New repository secret**, avec ce même nom, si tu préfères ne pas afficher la configuration dans les réglages du dépôt.

Colle comme valeur **le contenu JSON du client de bureau téléchargé**, et non le chemin du fichier sur ton PC. Le workflow donne priorité au secret si les deux existent. Il écrit la configuration dans un fichier temporaire, transmet son chemin au constructeur, puis la retire du poste de construction. Le constructeur ne conserve que l’identité normalisée du client d’application, `installed.client_id` et `installed.client_secret`, dans les ressources du programme.

Cette identité d’application de bureau est distribuée avec PrépaPilot : la placer dans un secret GitHub ne la rend pas secrète dans l’exécutable. **N’utilise jamais ici un jeton personnel, `credentials.bin`, une sauvegarde ni le contenu de `data/cloud`.** Chaque utilisateur connecte et autorise ensuite son propre compte ; la configuration commune ne lui donne pas accès au compte de l’éditeur ou aux sauvegardes des autres.

Un client déjà présent dans `Sources/PrepaPilot/assets/google-oauth-client.json` peut aussi servir à la construction. Le passage par la variable ou le secret évite de devoir ajouter ce fichier aux sources. Conserve le même client pour les futures versions et les autres PC.

Une publication par tag ajoute **`--require-google-drive`** : sans configuration valide, la construction s’arrête et la Release automatique n’est pas publiée. Le lancement manuel reste possible sans client pour les essais des fonctions locales. Le parcours réel déjà vérifié et ses limites sont détaillés dans [VERIFICATION-PUBLICATION.md](VERIFICATION-PUBLICATION.md).

## 3. Construire les fichiers Windows sur GitHub

1. Sur la page du dépôt, ouvre **Actions**.
2. Choisis **Windows — tests et distributions**.
3. Clique sur **Run workflow**, choisis la branche principale, puis confirme **Run workflow**.
4. Attends que l’exécution se termine avec succès. Ouvre son résultat et télécharge l’archive dans la rubrique **Artifacts**.
5. Extrais cette archive. Pour la version 2.26.1, elle fournit **`PrepaPilot-2.26.1-Setup.exe`**, **`PrepaPilot-2.26.1-Windows-portable.zip`** et **`SHA256SUMS.txt`**.

Le bouton **Run workflow** apparaît quand le workflow est présent sur la branche par défaut du dépôt. Le lancement manuel est décrit dans la [documentation GitHub Actions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Un résultat dans **Artifacts** permet de récupérer et d’essayer les fichiers ; la page **Releases** est l’endroit à partager avec les utilisateurs.

Le workflow inscrit automatiquement le nom du dépôt GitHub dans le programme pour les mises à jour ; cette information ne demande aucun jeton personnel. La configuration Google de la section 2 est indépendante. La recherche des mises à jour devient utilisable dès qu’une première **Release publique stable** contient l’installateur et son fichier **SHA256SUMS.txt**. Un dépôt privé, un brouillon ou une préversion ne sert pas de canal de mise à jour public.

## 4. Publier la première version

Le dossier local **`A-publier`** contient les fichiers Windows de la livraison finale pour une publication manuelle et reste hors de Git grâce au `.gitignore`. La construction finale reçoit le dépôt `clmtxx/PrepaPilot` et le client Google commun. Garde ensemble l’installateur, le ZIP et le fichier de sommes provenant de la même construction ; les anciennes distributions sont archivées séparément. Les fichiers d’une construction GitHub réussie peuvent aussi être utilisés.

1. Essaie l’installateur sur un compte ou un PC Windows de test. Vérifie le lancement depuis le menu Démarrer, un export/import et la désinstallation. Vérifie aussi le lancement du portable après extraction complète.
2. Dans le dépôt GitHub, ouvre **Releases → Draft a new release**.
3. Dans **Choose a tag**, crée **`v2.26.1`** en ciblant la branche qui contient cette version.
4. Donne le titre **PrépaPilot 2.26.1**. Dans la description, indique « Windows 64 bits — télécharger le fichier Setup.exe pour installer » et les changements utiles.
5. Joins **`PrepaPilot-2.26.1-Setup.exe`**, le **ZIP portable** et **`SHA256SUMS.txt`** dans la zone des fichiers de la Release.
6. Vérifie que ces trois fichiers apparaissent, puis clique sur **Publish release**.

Le [guide officiel des Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository?tool=webui) détaille ce formulaire. La création du tag peut aussi lancer la construction automatique : elle ajoute ou remplace les trois fichiers de cette même Release, en conservant son titre et sa description. Attends sa réussite avant de diffuser le lien. Si le tag a déjà été envoyé selon la section suivante, complète la Release existante.

Partage ensuite le lien de la page **Releases**, ou celui de cette version. Pour un lien stable vers la dernière version, utilise l’adresse de ton dépôt suivie de **`/releases/latest`**. Les utilisateurs téléchargent le fichier **`-Setup.exe`** sous **Assets** ; les archives **Source code** générées par GitHub servent au développement.

## 5. Préparer les prochaines versions

1. Modifie et vérifie le code. Mets à jour le numéro de version dans la source et dans les guides concernés.
2. Enregistre et envoie les changements avec GitHub Desktop.
3. Lance d’abord la construction manuelle dans **Actions** et essaie les fichiers obtenus.
4. Dans GitHub Desktop, ouvre **History**. Clique droit sur l’enregistrement correspondant à la version vérifiée, puis **Create Tag…**. Saisis **`vX.Y.Z`** avec le numéro exact de cette version, crée le tag, puis envoie-le avec **Push origin**. Le workflow **Windows — tests et distributions** construit les fichiers et publie la Release correspondante. Voir la [gestion des tags dans GitHub Desktop](https://docs.github.com/en/desktop/managing-commits/managing-tags-in-github-desktop).
5. Attends sa réussite, puis vérifie la Release, ses trois fichiers et son téléchargement. Complète ses notes de version avant de diffuser le lien.

Pour que les utilisateurs déjà installés reçoivent la nouvelle version, conserve le même dépôt public et augmente le numéro `X.Y.Z`. Chaque Release stable doit garder les noms **`PrepaPilot-X.Y.Z-Setup.exe`** et **`SHA256SUMS.txt`** produits par le workflow. Les utilisateurs reçoivent alors une notification et peuvent choisir **Télécharger et installer** depuis **Réglages → Mises à jour**. L’application vérifie le téléchargement avant de proposer de fermer PrépaPilot et d’ouvrir l’installateur. Les données restent dans le même dossier ; aucune désinstallation n’est nécessaire. Le portable propose la page de téléchargement.

Si tu préfères conserver une publication manuelle, reprends la section 4 avec les fichiers de la nouvelle construction. N’utilise pas les anciens fichiers de `A-publier` pour annoncer une version plus récente. Une construction manuelle sans client reste utile pour les essais locaux ; ne l’annonce pas comme une distribution avec Google Drive activé.

## Options de publication et Google Drive

- **Licence du code :** choisis les conditions de réutilisation que tu souhaites autoriser. Les licences des bibliothèques tierces sont déjà conservées ; elles ne définissent pas à elles seules la licence de ton code.
- **Signature Windows :** aucun certificat d’éditeur n’est fourni par cette préparation. Un avertissement Windows peut apparaître. Une signature nécessitera ton propre certificat et sa configuration dans la chaîne de construction.
- **Google Drive :** l’accès commun est activé en production et son premier parcours réel est vérifié. Conserve ce client pour les nouvelles versions et le workflow. Chaque utilisateur clique sur **Se connecter à Google** et autorise son propre compte ; aucun compte n’est connecté dans les fichiers distribués. Suis [Documentation/Google-Drive.md](Documentation/Google-Drive.md).

Pour reconstruire localement, consulte les options de `scripts/build_release.py` et le [guide de développement](Documentation/Developpement.md). Les résultats vont dans `dist` et sont exclus du dépôt, comme le contenu de `A-publier`.

Depuis la racine du dépôt, utilise par exemple :

```powershell
python -B ./scripts/build_release.py --repository clmtxx/PrepaPilot --google-oauth-client 'C:/Configuration-PrepaPilot/client-google.json' --require-google-drive --expect-version 2.26.1
```

Adapte le chemin à ton client Google de bureau et le numéro attendu pour une autre version. Le constructeur prépare ces informations dans une copie temporaire des ressources et ne modifie pas les sources. Pour une construction de développement sans Google, omets les deux options Google.

Il est aussi possible de fournir `Sources/PrepaPilot/assets/update-channel.json` contenant uniquement `{"repository":"proprietaire/PrepaPilot"}` ; l’option `--repository` prend priorité. Aucun jeton n’est accepté dans ce fichier. Sans dépôt fourni, le programme reste utilisable et affiche que son canal de mises à jour n’est pas encore configuré. Un ancien programme fourni avec `--app-dir` conserve son dépôt de mises à jour : il faut recompiler pour le changer. L’intégration du client Google avec `--app-dir` se fait sur une copie de ce programme.

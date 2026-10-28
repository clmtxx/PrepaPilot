# Confidentialité / Privacy

Dernière mise à jour / Last updated: **28 octobre 2026 / 28 October 2026**.

## Français

**Éditeur du projet :** compte GitHub [clmtxx](https://github.com/clmtxx). **Contact :** [Issues de PrépaPilot](https://github.com/clmtxx/PrepaPilot/issues). Ces échanges sont publics ; utilise des exemples fictifs pour signaler un problème.

### Données sur ton ordinateur

PrépaPilot conserve localement ton profil et tes préférences, matières, années scolaires, notes, documents, emploi du temps, activités, repères et succès. La version installée utilise `%LOCALAPPDATA%\PrepaPilot\data` ; la version portable utilise le dossier `data` à côté de l’exécutable. Les exports `.prepapilot` et les sauvegardes locales contiennent des copies de tes données.

« Ranger avec une IA » prépare des copies de documents et leurs chemins sur ton ordinateur. Un assistant externe auquel tu donnes accès à cet espace peut les lire ; aucun modèle IA n’est intégré à cette fonction.

### Sauvegardes Google Drive facultatives

Avec une distribution configurée, tu peux connecter ton propre compte Google dans le navigateur et lancer une sauvegarde. L’application demande uniquement l’autorisation `https://www.googleapis.com/auth/drive.file`, pour les fichiers utilisés avec PrépaPilot. Les rappels ne déclenchent pas de transfert automatique.

Tu choisis parmi sept catégories : documents et cours ; notes et évaluations ; sommeil ; travail, sport et autres activités ; emploi du temps et vacances ; repères et archives personnelles ; profil et préférences. **Les matières, les années scolaires et les succès et quêtes débloqués sont toujours inclus.** Les données sélectionnées et les informations nécessaires à leur restauration sont envoyées dans le dossier Drive choisi.

Les jetons de connexion sont enregistrés localement dans `data/cloud/credentials.bin`, protégés par Windows DPAPI pour ton utilisateur Windows. Ils sont exclus des sauvegardes et des distributions. Cette protection locale ne chiffre pas les cours et sauvegardes : **PrépaPilot n’ajoute pas de chiffrement de bout en bout aux sauvegardes Drive**. Les transferts utilisent HTTPS ; les empreintes de fichiers servent à vérifier leur intégrité.

### Conservation et suppression

Tu gères la suppression des données locales, des exports et des sauvegardes. La désinstallation normale conserve les données. Les anciennes versions Drive ne sont pas supprimées automatiquement : retirer une donnée dans PrépaPilot ne l’efface pas des sauvegardes déjà créées. Tu peux supprimer le dossier de sauvegarde depuis Google Drive ; ses fichiers techniques peuvent être partagés par plusieurs versions.

« Déconnecter ce PC » efface le jeton local, sans supprimer les sauvegardes Drive ni déconnecter les autres PC. Pour retirer l’autorisation de l’application, utilise les paramètres de ton compte Google.

### Mises à jour et GitHub

Lorsqu’un dépôt public est configuré, la recherche de mises à jour contacte GitHub par HTTPS, automatiquement au plus une fois par jour ou à ta demande. La recherche automatique peut être désactivée dans les Réglages. Le téléchargement de l’installateur nécessite ton action.

Ce mécanisme ne transmet pas tes données scolaires, ton nom de profil ni un jeton GitHub. GitHub et ses services de téléchargement reçoivent les informations techniques habituelles de la connexion, notamment l’adresse IP et l’identifiant fixe `PrepaPilot-Updater`.

## English

**Project publisher:** GitHub account [clmtxx](https://github.com/clmtxx). **Contact:** [PrépaPilot Issues](https://github.com/clmtxx/PrepaPilot/issues). Issues are public; use fictional examples when reporting a problem.

### Data on your computer

PrépaPilot stores your profile and preferences, subjects, school years, grades, documents, timetable, activities, personal notes and achievements locally. The installed version uses `%LOCALAPPDATA%\PrepaPilot\data`; the portable version uses the `data` folder beside the executable. `.prepapilot` exports and local backups contain copies of your data.

“Organise with AI” prepares document copies and their paths on your computer. An external assistant you give access to that workspace can read them; this feature does not include an AI model.

### Optional Google Drive backups

With a configured distribution, you can connect your own Google account in your browser and start a backup. The application requests only `https://www.googleapis.com/auth/drive.file`, for files used with PrépaPilot. Reminders do not start transfers automatically.

You choose from seven categories: documents and course files; grades and assessments; sleep; study, sport and other activities; timetable and holidays; personal notes and archives; profile and preferences. **Subjects, school years, and unlocked achievements and quests are always included.** Selected data and the information needed to restore it are sent to your chosen Drive folder.

Connection tokens are stored locally in `data/cloud/credentials.bin`, protected with Windows DPAPI for your Windows user. They are excluded from backups and distributions. This local protection does not encrypt your course files or backups: **PrépaPilot does not add end-to-end encryption to Drive backups**. Transfers use HTTPS; file hashes check integrity.

### Retention and deletion

You manage deletion of local data, exports and backups. Normal uninstallation preserves data. Older Drive versions are not deleted automatically: removing data in PrépaPilot does not remove it from existing backups. You can delete the backup folder in Google Drive; its technical files may be shared by several versions.

“Disconnect this PC” removes the local token without deleting Drive backups or disconnecting other PCs. To revoke the application’s access, use your Google account settings.

### Updates and GitHub

When a public repository is configured, update checks contact GitHub over HTTPS, automatically at most once a day or when you request a check. Automatic checks can be disabled in Settings. Downloading the installer requires your action.

This mechanism does not send your study data, profile name or a GitHub token. GitHub and its download services receive normal connection information, including the IP address and the fixed identifier `PrepaPilot-Updater`.

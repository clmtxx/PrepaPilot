# Sauvegarder et retrouver ses données avec Google Drive

PrépaPilot peut envoyer une sauvegarde dans ton Google Drive et la récupérer sur un autre ordinateur. Le parcours habituel est simple : **Réglages → Gérer mes sauvegardes Google Drive → Se connecter à Google**, puis tu choisis ton compte dans ton navigateur et tu autorises l’application. Google Drive pour ordinateur n’est pas nécessaire.

La personne qui distribue PrépaPilot prépare une seule fois l’accès Google commun à l’application et l’intègre dans l’installateur. **Les utilisateurs n’ont pas à créer de projet Google Cloud ni à fournir de fichier JSON.** Chacun se connecte à son propre compte et conserve ses propres sauvegardes.

**État vérifié le 28 octobre 2026 :** le client OAuth de bureau commun est créé, l’application Google est **En production** et le secret de construction `GOOGLE_OAUTH_CLIENT_JSON` est enregistré dans le dépôt public [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot), dont les sources sont présentes sur `main`. La préparation de l’accès commun est terminée ; les distributions doivent être construites avec cette configuration. Ces éléments ne constituent pas à eux seuls la publication d’une Release.

Google Drive reste facultatif et aucun compte n’est connecté d’office. Chaque personne autorise son propre compte. L’export local `.prepapilot` reste disponible. Consulte les [informations de confidentialité](https://github.com/clmtxx/PrepaPilot/blob/main/PRIVACY.md) pour les données transférées et leur conservation.

## Se connecter et choisir un dossier

Clique sur **Se connecter à Google**. Dans le navigateur, choisis ton compte et accepte l’autorisation de PrépaPilot, puis reviens dans l’application.

Au premier usage, clique sur **Nouveau dossier** pour créer ton dossier de sauvegarde. Par la suite, **Retrouver mes dossiers** permet de sélectionner un dossier déjà créé par PrépaPilot. Tu peux aussi coller son lien dans le champ prévu à cet effet. **Ouvrir dans Drive ↗** l’affiche dans le navigateur.

Le lien d’un dossier quelconque ne suffit pas à donner accès à son contenu. Cette version utilise les dossiers de sauvegarde créés par PrépaPilot avec la même configuration Google.

**Déconnecter ce PC** efface la connexion enregistrée sur cet ordinateur. Les sauvegardes restent dans Drive et les autres ordinateurs restent connectés. Pour retirer entièrement l’autorisation de l’application à ton compte, utilise les paramètres de ton compte Google, comme décrit dans le [guide Google de gestion des accès des applications](https://support.google.com/accounts/answer/14012355). Cette révocation peut imposer une nouvelle connexion sur tous les PC concernés.

## Choisir ce qui sera sauvegardé

Coche les catégories souhaitées avant de lancer **Sauvegarder maintenant**.

| Catégorie | Contenu |
| --- | --- |
| Documents et fichiers de cours | Les documents ajoutés à l’application, leurs informations et leurs fichiers |
| Notes et évaluations | Les notes, barèmes, coefficients, dates et intitulés |
| Données de sommeil | Les activités enregistrées dans la catégorie sommeil |
| Travail, sport et autres activités | Les autres activités de la gestion du temps |
| Emploi du temps et vacances | La configuration du planning, les changements de semestre, les vacances et l’historique des journées configurées |
| Repères et archives personnelles | Les repères et les données personnelles historiques conservées par l’application |
| Profil et préférences | Le profil, l’apparence et les préférences de progression |

Les matières, les années et les **succès et quêtes déjà débloqués** sont inclus automatiquement. Les informations de connexion Google et les réglages de rappel propres à ce PC ne font pas partie de la sauvegarde.

Les médailles et les XP acquis restent disponibles après restauration, même si le travail ou le sommeil n’étaient pas sélectionnés dans cette sauvegarde. Pour retrouver également les compteurs en cours et l’historique détaillé, coche ces deux catégories. À l’import Drive, les récompenses enregistrées sont réunies avec celles déjà présentes sur ce PC ; un même succès ou une même quête ne rapporte jamais ses points deux fois. Les sauvegardes anciennes qui ne contiennent pas de succès conservent les récompenses locales. L’import complet d’un fichier `.prepapilot` reste, lui, un remplacement intégral par l’état archivé.

PrépaPilot calcule une empreinte SHA-256 pour chaque enregistrement et chaque fichier. Il réutilise les éléments déjà présents et vérifiés dans le dossier choisi. Un changement envoie uniquement les éléments nouveaux ou modifiés, avec un nouveau récapitulatif de sauvegarde. Deux sauvegardes identiques ne créent pas de nouvelle version ni de copie supplémentaire des données.

Les anciennes versions sont conservées. Supprimer ou modifier une donnée dans l’application ne retire pas les versions déjà sauvegardées. Le dossier Drive contient des fichiers techniques partagés entre plusieurs versions : conserve son contenu intact pour pouvoir les restaurer.

Un transfert interrompu ne remplace pas une sauvegarde précédente. Relance-le : les éléments déjà envoyés et vérifiés pourront être réutilisés. La date de dernière sauvegarde n’est mise à jour qu’après confirmation du résultat.

Depuis la version 2.15, le registre sauvegardé conserve aussi les anciens barèmes de travail avec leurs XP, les nouveaux paliers renforcés et les succès de sport. Utilise la version 2.15 ou une version plus récente sur l’ordinateur qui restaure ces nouveaux succès. Pour retrouver le détail des activités sportives, sélectionne **Travail, sport et autres activités** ; les médailles acquises sont incluses même sans cette catégorie.

Les paliers hebdomadaires et mensuels rééquilibrés de la version **2.15.1** nécessitent cette version ou une version ultérieure sur l’appareil de restauration. Les récompenses des précédents barèmes restent conservées, y compris leurs dates et leurs XP.

## Recevoir un rappel

Le rappel est activé par défaut avec une fréquence d’une semaine. Dans **Garder le réflexe**, tu peux choisir **Chaque semaine**, **Tous les 3 jours** ou **Chaque jour**, puis cliquer sur **Enregistrer mes choix**. Tu peux aussi désactiver le rappel.

Le délai part de la dernière sauvegarde vérifiée ; avant la première sauvegarde, il part du premier lancement de PrépaPilot avec ce rappel disponible. Le bandeau permet de lancer la sauvegarde ou de reporter le rappel d’un jour.

Le rappel apparaît dans PrépaPilot. Si l’application est fermée à l’échéance, il apparaîtra à la prochaine ouverture. Il ne déclenche aucun envoi automatique : tu gardes le choix des données et du moment du transfert.

## Importer depuis Drive ou changer d’ordinateur

1. Sur l’autre PC, installe une version compatible de PrépaPilot distribuée avec **le même accès Google de l’application**. Aucune configuration technique n’est nécessaire avec une version déjà préparée.
2. Connecte-toi au **même compte Google** que pour la sauvegarde, puis utilise **Retrouver mes dossiers** et sélectionne ton dossier.
3. Clique sur **Afficher les sauvegardes**, choisis une date, puis sur **Vérifier et importer…**.
4. Lis le récapitulatif des catégories avant de confirmer.

Les catégories présentes dans la version choisie remplacent les catégories correspondantes de ce PC. Les autres restent conservées. Les cases de la section **Ce que tu emportes** servent à préparer une sauvegarde ; elles ne changent pas le contenu d’une version déjà sauvegardée.

Le téléchargement est vérifié et la restauration préparée avant toute modification des données actives. Une sauvegarde locale complète de l’état courant est créée juste avant le remplacement, dans `%LOCALAPPDATA%/PrepaPilot/data/backups` avec la version installée, ou dans `data/backups` à côté de l’exécutable avec la version portable. Son nom commence par `avant-import-` et son extension est `.prepapilot`. Pour revenir à cet état, utilise l’import local de sauvegarde dans **Réglages** et sélectionne ce fichier.

Si une restauration partielle crée un conflit entre des activités, ou si les données locales ont changé pendant sa préparation, l’application interrompt l’import. Tu peux alors régler le conflit ou recharger la sauvegarde avant de recommencer.

Cette fonction sert à sauvegarder et à transférer un état de tes données. Elle ne fusionne pas automatiquement les modifications de plusieurs ordinateurs. Pour passer d’un PC à l’autre, sauvegarde sur le premier, puis importe sur le second avant de continuer ton travail.

## Éditeur · préparer une seule fois l’accès commun

Cette partie concerne la personne qui construit et partage PrépaPilot. La préparation commune de ce projet a été réalisée le 28 octobre 2026 ; les étapes suivantes servent à conserver ou à reproduire cette configuration. Elle se fait une seule fois pour l’application, puis la configuration est réutilisée pour les versions suivantes et sur les différents PC. Elle ne connecte aucun compte d’utilisateur.

1. Dans la [console Google Cloud](https://console.cloud.google.com/), crée ou sélectionne le projet destiné à PrépaPilot, puis active **Google Drive API**. Voir le [guide de démarrage Drive](https://developers.google.com/workspace/drive/api/quickstart/python#enable_the_api).
2. Dans **Google Auth Platform**, renseigne le nom de l’application, une adresse d’assistance et les coordonnées de l’éditeur. Choisis l’audience **Externe** pour permettre la connexion de comptes Google personnels. Le [guide Google du consentement](https://developers.google.com/workspace/guides/configure-oauth-consent) décrit cette préparation.
3. Dans les accès aux données, déclare uniquement `https://www.googleapis.com/auth/drive.file`. Google classe cette autorisation parmi les accès **non sensibles** : elle porte sur les fichiers utilisés avec l’application. PrépaPilot l’utilise pour ses dossiers et sauvegardes, sans demander l’accès général au Drive de l’utilisateur. Voir les [autorisations Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
4. Dans **Google Auth Platform → Clients**, crée un client OAuth de type **Application de bureau**, puis télécharge sa configuration JSON. Voir le [parcours Google pour applications de bureau](https://developers.google.com/identity/protocols/oauth2/native-app).
5. Transmets ce fichier au constructeur de l’application avec `--google-oauth-client CHEMIN` et ajoute `--require-google-drive` pour empêcher la création d’une distribution annoncée compatible sans cette configuration. La commande complète est dans [Développement](Developpement.md#intégrer-laccès-google-dans-linstallateur).

Le constructeur intègre une configuration normalisée qui identifie l’application. **N’intègre aucun compte connecté, aucun `credentials.bin`, aucun jeton et aucun dossier personnel `data/cloud`.** Chaque utilisateur autorise ensuite PrépaPilot dans son propre navigateur ; son mot de passe n’est pas fourni au programme.

Le même client doit être conservé pour les mises à jour et les autres PC : le remplacer par un client indépendant peut empêcher de retrouver les fichiers créés avec le précédent. Ce fichier identifie une application de bureau distribuée ; il ne remplace pas l’autorisation individuelle de chaque compte. Google traite les applications de bureau comme des clients publics. [Documentation Google](https://developers.google.com/identity/protocols/oauth2/native-app)

### Tests puis distribution publique

Pendant les essais, ajoute les comptes autorisés à la liste des **utilisateurs test** dans l’audience du projet. En audience **Externe / Test**, l’accès est limité à cette liste et les jetons de renouvellement de PrépaPilot expirent au bout de **sept jours**. Une reconnexion peut donc être nécessaire ; les sauvegardes ne sont pas supprimées. [États OAuth Google](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview), [expiration des jetons](https://developers.google.com/identity/protocols/oauth2#expiration)

Le projet Google de PrépaPilot est **En production / Published** depuis la préparation du 28 octobre 2026. La [page de confidentialité du projet](https://github.com/clmtxx/PrepaPilot/blob/main/PRIVACY.md) décrit les données et les échanges. Pour une nouvelle configuration, prépare les éléments d’identité demandés par Google : nom, contacts, page de présentation, politique de confidentialité et domaines vérifiés selon le parcours affiché. Effectue les vérifications de marque applicables pour afficher le nom et le logo. L’autorisation `drive.file` n’est pas un accès sensible ou restreint ; elle ne justifie pas les contrôles supplémentaires propres à ces catégories. Le statut En production ne constitue pas à lui seul une attestation de validation de marque. [Vérification de marque](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification), [catégories d’autorisation](https://developers.google.com/workspace/guides/configure-oauth-consent#scope_categories)

**Essai réel du 28 octobre 2026 :** la connexion avec PKCE et la protection locale des jetons par DPAPI ont réussi. La première sauvegarde de données fictives a envoyé **14 objets**. Une seconde sauvegarde identique a envoyé **0 objet**, réutilisé les **14 objets** et n’a créé **aucune nouvelle version**. La restauration vers un espace de test distinct a retrouvé exactement les données et documents attendus. Les jetons utilisés pour cet essai ont été effacés ; aucun compte connecté n’est inclus dans une distribution.

L’essai sur **un autre PC** et avec **un autre compte Google** reste à effectuer. Il devra confirmer le transfert avec le même client et la séparation des dossiers de chaque personne. Une nouvelle construction intégrant le dépôt et le client Google doit aussi être revérifiée avant diffusion. Le statut En production ne garantit pas qu’un compte d’organisation autorisera l’application ; son administrateur peut appliquer ses propres règles. [Règles d’organisation Google](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview#administrative_overrides_in_google_workspace_environments)

## Avancé · utiliser son propre client Google

Ce choix convient aux essais ou à une utilisation personnelle lorsque tu souhaites gérer toi-même le projet Google. Il n’est pas nécessaire pour les utilisateurs d’une distribution déjà configurée.

Prépare un projet et un client **Application de bureau** selon les étapes éditeur ci-dessus, avec la seule autorisation `drive.file`. Si le projet est en mode Test, ajoute ton compte aux utilisateurs test. Dans **Options avancées** du dialogue Google Drive de PrépaPilot, utilise **Importer une configuration personnelle…** pour sélectionner le JSON téléchargé. Connecte ensuite ton compte avec **Se connecter à Google**.

Conserve cette configuration et importe **le même client** sur tes autres PC avant de retrouver tes sauvegardes. Une configuration locale importée prend la priorité sur celle intégrée à l’application. Changer de client n’est donc pas une étape habituelle d’installation ou de mise à jour.

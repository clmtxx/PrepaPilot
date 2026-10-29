# PrépaPilot 2.26.1 — version corrective préparée le 29 octobre 2026

La version 2.26.1 corrige le téléchargement des mises à jour depuis GitHub. Le [rapport de publication](VERIFICATION-PUBLICATION.md) précise les vérifications finales ; les fichiers publiés sont accessibles sur la page [dernière version](https://github.com/clmtxx/PrepaPilot/releases/latest).

## Correctif 2.26.1

Le téléchargement accepte le format actuel d’hébergement des fichiers GitHub. Les contrôles du fichier téléchargé, notamment son empreinte SHA-256, restent appliqués.

## Nouveautés 2.26

- **Un suivi du pointeur dans tous les espaces :** les reflets lumineux réagissent sur toute la carte, y compris lorsque la souris passe sur un texte, un champ ou un bouton.
- **Les couleurs de Progression conservées :** le travail, le sommeil, le sport et le repos gardent leurs palettes et dégradés. Chaque reflet utilise la couleur d’accent de sa carte.
- **Des illustrations liées à leur carte :** leur réaction suit le pointeur sur la surface de la carte qui les contient, comme sur l’accueil.
- **Des mouvements mesurés :** l’amplitude reste limitée, les boutons et champs gardent leurs zones de clic et de saisie. Une carte masquée ou désactivée cesse de réagir ; **Réduire les animations** arrête les effets de suivi.

La simplification Google Drive de la version **2.25** reste disponible : l’éditeur prépare une seule fois le client commun de l’application et chaque utilisateur se connecte puis autorise son compte. Les options de construction **`--google-oauth-client`** et **`--require-google-drive`**, ainsi que les configurations personnelles dans les options avancées, sont conservées. L’état de l’activation réelle est précisé ci-dessous.

Les transitions directionnelles en profondeur, les notifications compactes avec copie du texte et pause de lecture, ainsi que le repère du champ actif de la version **2.24** sont conservés. Le relief, les reflets et les couleurs équilibrées restent disponibles dans les deux thèmes. Les animations réduites ouvrent les pages directement.

Le rangement des cours avec une IA, la recherche **Ctrl+F**, les actions rapides **Ctrl+K**, la barre de séance et l’aide **F1** restent disponibles.

La version est disponible en français et en anglais, dans les deux thèmes, avec les animations réduites. Les données existantes sont conservées lors d’une mise à jour de l’installation.

## Fichiers Windows

- **PrepaPilot-2.26.1-Setup.exe** : installation pour le compte Windows, sans Python ni droits administrateur.
- **PrepaPilot-2.26.1-Windows-portable.zip** : extraire tout le dossier avant d’ouvrir PrepaPilot.exe.
- **SHA256SUMS.txt** : empreintes des deux fichiers.

Les guides INSTALLER.md et INSTALL.en.md expliquent le premier lancement, les sauvegardes et le transfert entre modes. Une version portable et une version installée ont des espaces de données distincts : utilise l’export/import complet pour les transférer.

Les fonctions locales sont utilisables immédiatement. La livraison utilise le dépôt public [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot) pour les mises à jour ; retrouve les versions stables sur la page [dernière version](https://github.com/clmtxx/PrepaPilot/releases/latest).

**Google Drive est préparé dans la livraison finale :** le client commun réel est intégré et l’application Google est en production. Le 28 octobre, une connexion réelle, une sauvegarde de 14 objets, une seconde sans nouvel envoi ni nouvelle version et une restauration exacte des données et documents ont réussi avec un espace fictif. Aucun compte n’est connecté automatiquement. Google reste facultatif ; chacun autorise son propre compte. Un autre PC et un autre compte restent à tester. La [notice de confidentialité](PRIVACY.md) décrit le stockage et les transferts.

Le secret GitHub **`GOOGLE_OAUTH_CLIENT_JSON`** est enregistré pour la construction par tag, sans jeton ni connexion personnelle. Une construction manuelle de développement peut rester sans Google. Le guide [PUBLIER.md](PUBLIER.md) explique le processus de publication et les prochaines versions.

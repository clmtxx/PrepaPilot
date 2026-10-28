# PrépaPilot 2.26.0 — 27 octobre 2026

## Nouveautés

- **Un suivi du pointeur dans tous les espaces :** les reflets lumineux réagissent sur toute la carte, y compris lorsque la souris passe sur un texte, un champ ou un bouton.
- **Les couleurs de Progression conservées :** le travail, le sommeil, le sport et le repos gardent leurs palettes et dégradés. Chaque reflet utilise la couleur d’accent de sa carte.
- **Des illustrations liées à leur carte :** leur réaction suit le pointeur sur la surface de la carte qui les contient, comme sur l’accueil.
- **Des mouvements mesurés :** l’amplitude reste limitée, les boutons et champs gardent leurs zones de clic et de saisie. Une carte masquée ou désactivée cesse de réagir ; **Réduire les animations** arrête les effets de suivi.

La simplification Google Drive de la version **2.25** reste disponible : l’éditeur prépare une seule fois le client commun de l’application et chaque utilisateur se connecte puis autorise son compte. Les options de construction **`--google-oauth-client`** et **`--require-google-drive`**, ainsi que les configurations personnelles dans les options avancées, sont conservées. L’état de l’activation réelle est précisé ci-dessous.

Les transitions directionnelles en profondeur, les notifications compactes avec copie du texte et pause de lecture, ainsi que le repère du champ actif de la version **2.24** sont conservés. Le relief, les reflets et les couleurs équilibrées restent disponibles dans les deux thèmes. Les animations réduites ouvrent les pages directement.

Le rangement des cours avec une IA, la recherche **Ctrl+F**, les actions rapides **Ctrl+K**, la barre de séance et l’aide **F1** restent disponibles.

La version est disponible en français et en anglais, dans les deux thèmes, avec les animations réduites. Les données existantes sont conservées lors d’une mise à jour de l’installation.

## Fichiers Windows

- **PrepaPilot-2.26.0-Setup.exe** : installation pour le compte Windows, sans Python ni droits administrateur.
- **PrepaPilot-2.26.0-Windows-portable.zip** : extraire tout le dossier avant d’ouvrir PrepaPilot.exe.
- **SHA256SUMS.txt** : empreintes des deux fichiers.

Les guides INSTALLER.md et INSTALL.en.md expliquent le premier lancement, les sauvegardes et le transfert entre modes. Une version portable et une version installée ont des espaces de données distincts : utilise l’export/import complet pour les transférer.

Les fonctions locales sont utilisables immédiatement. Les mises à jour automatiques nécessiteront le futur dépôt public.

**Google Drive n’est pas encore activé dans les livrables locaux :** aucun client réel n’est fourni à ce jour. L’éditeur doit terminer la préparation Google, intégrer ce client puis vérifier une connexion, une sauvegarde et une restauration réelles. La simplification du parcours ne connecte aucun compte et ne crée aucun dossier automatiquement. Les tests simulés ne remplacent pas cette validation.

Pour publier par tag, renseigne **`GOOGLE_OAUTH_CLIENT_JSON`** dans les variables ou secrets GitHub avec le JSON du client d’application de bureau, sans jeton ni connexion personnelle. Une construction manuelle de développement peut rester sans Google. Le guide [PUBLIER.md](PUBLIER.md) explique la procédure.

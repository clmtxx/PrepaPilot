# Outils de PrépaPilot

## Diffusion GitHub

Le dossier autonome **PrepaPilot-GitHub** utilise **scripts/build_release.py** et **PUBLIER.md** pour la distribution Windows. Les outils ci-dessous servent à l’espace de travail portable historique.

Depuis cet espace de travail, **preparer_github.py** recopie les sources, tests, licences et guides sélectionnés dans **PrepaPilot-GitHub**, sans parcourir l’application ni ses données. Il préserve les scripts de construction, l’installateur et les guides de publication déjà présents. Il exclut aussi la configuration OAuth Google. Exécute-le après une modification dans les sources historiques, puis reconstruis la distribution. Dans le dépôt GitHub autonome, modifie directement les fichiers de **Sources/PrepaPilot**.

Le rapport public **Documentation/Audit-2026-10-25.md** fait partie des documents sélectionnés. La synchronisation des sources ne reconstruit pas les fichiers de **A-publier** et ne publie rien en ligne.

Ces scripts servent à maintenir le projet. Pour utiliser l’application, ouvre simplement **Ouvrir PrepaPilot.cmd** à la racine.

## Scripts actuels

| Script | Fonction |
| --- | --- |
| `chemins.py` | Chemins communs du projet et de son espace local voisin |
| `lancer_sources.py` | Lance les sources avec des données de développement séparées |
| `verifier_couleurs.py` | Contrôle les sept pages dans les deux thèmes et deux tailles de fenêtre ; captures et rapport dans `.local/Verification/Couleurs` du projet, avec données fictives |
| `verifier_engagement.py` | Contrôle l’accueil contextuel, les premiers pas, la semaine et la palette Ctrl+K, en français/anglais et dans les deux thèmes ; résultats dans `.local/Verification/Engagement` |
| `partager_application.py` | Crée `Partage/PrepaPilot-Windows.zip`, application seule sans données |
| `preparer_projet.py` | Crée le dossier et le ZIP `Partage/PrepaPilot-Projet`, projet complet propre |
| `verifier_distribution.py` | Extrait et teste le ZIP Windows ; `--projet` vérifie le projet complet |
| `verifier_interface.py` | Capture l’interface avec des données fictives dans l’espace local |
| `verifier_notes.py` | Vérifie et capture les moyennes de classe, classements et formulaires facultatifs, avec des données fictives dans les deux thèmes |
| `verifier_seances.py` | Capture le minuteur, la préparation et le bilan des séances dans les deux thèmes, avec une horloge et des données fictives |
| `verifier_dossiers.py` | Capture les dossiers, la recherche globale et les dialogues de rangement avec des fichiers fictifs dans les deux thèmes |
| `verifier_rangement_ia.py` | Vérifie les chemins, le guide et l’aperçu du rangement IA ; 24 captures en français/anglais, clair/sombre et deux tailles, avec des cours fictifs |
| `verifier_finitions.py` | Contrôle le relief, les reflets, les scintillements et le retour de pression ; captures des pages, planches d’animation et aperçu GIF, avec des données fictives |
| `verifier_navigation.py` | Contrôle et capture les transitions de pages en profondeur, les clics rapides, les brouillons, les notifications et le focus des champs ; résultats dans `.local/Verification/Navigation-2.24` |
| `verifier_suivi_souris.py` | Contrôle le suivi du pointeur dans les cartes et leurs illustrations, les couleurs de Progression, les interactions et les animations réduites ; résultats dans `.local/Verification/Suivi-souris-2.26` avec des données fictives |
| `verifier_succes.py` | Capture les succès, le sport, les quêtes, les cinq paliers et l’historique des anciens barèmes avec un journal fictif, dans les deux thèmes et deux tailles de fenêtre |
| `mesurer_fluidite.py` | Mesure les chargements et rafraîchissements avec une base fictive volumineuse ; conserve le rapport dans les fichiers locaux |
| `verifier_demarrage.py` | Vérifie l’affichage et la fermeture du chargement animé Windows ; `--installed` contrôle la version installée |
| `verifier_google.py` | Capture les réglages Google Drive, les rappels et l’import avec un état fictif, sans compte ni réseau |
| `verifier_plein_ecran.py` | Diagnostic Windows du plein écran depuis les sources |
| `mettre_a_jour_application.py` | Installe une livraison testée, conserve les données et archive l’ancien programme |
| `test_*.py` | Tests des outils, exécutés dans des dossiers temporaires |

La construction se lance avec `Sources/PrepaPilot/build_windows.py`. La procédure complète et les commandes sont dans **Documentation/Developpement.md**.

## Où vont les résultats ?

Les outils créent un dossier voisin nommé **« nom du projet - fichiers locaux »**. Il contient `Construction`, `Livraison`, `Archives`, `Transactions` et `Verification`. Aucun cache, ancien programme ou environnement Python n’est nécessaire dans ce dossier Outils.

Le dossier `Partage` ne contient que les distributions à transmettre. Il n’est pas inclus dans le projet exporté, afin d’éviter les copies imbriquées.

## Garanties de la mise à jour

- Une livraison doit avoir passé son contrôle `--self-test`.
- Le verrou de l’application empêche une mise à jour pendant son utilisation.
- Le dossier `data` reste en place.
- Les anciens binaires sont conservés dans une archive au nom unique.
- Si le remplacement échoue, l’outil remet les anciens fichiers en place et conserve les fichiers utiles à la récupération.

Les anciennes commandes de migration sont rangées avec les archives historiques. Pour transférer les données actuelles, utilise l’import et l’export intégrés à l’application.

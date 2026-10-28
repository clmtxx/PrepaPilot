# Vérification de PrépaPilot 2.26.0 — état du 28 octobre 2026

Les sources sont disponibles sur le dépôt public [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot). La livraison finale est préparée avec ce dépôt pour les mises à jour et avec le client Google commun, activé en production. Le secret de construction GitHub est enregistré. La première Release publique reste à publier ; les sections historiques ci-dessous décrivent l’état à leur date.

La campagne locale consolide **851 tests applicatifs réussis**, **23 tests de distribution réussis** après le correctif Windows 8.3, et **33 tests d’outils réussis avec 2 ignorés** faute de privilège de liens symboliques : **907 réussites et 2 ignorés sur 909 contrôles distincts**. Les reprises ne sont pas additionnées au nombre de cas. Le rapport [de publication](https://github.com/clmtxx/PrepaPilot/blob/main/VERIFICATION-PUBLICATION.md) détaille les contrôles.

Les diagnostics compilés français et anglais réussissent dans la construction configurée et le ZIP extrait. Installation, réinstallation 2.26.0 → 2.26.0, mise à jour 2.25.0 → 2.26.0 et désinstallation ont été vérifiées dans un espace isolé, avec conservation des empreintes des données fictives et de la préférence anglaise. La dernière reconstruction documentaire embarque le guide actualisé ; ses fichiers doivent rester associés au `SHA256SUMS.txt` produit avec eux.

Le parcours Google réel a réussi avec un vrai compte et uniquement des données applicatives fictives : OAuth PKCE, jetons protégés par DPAPI, première sauvegarde de 14 objets, seconde avec 0 envoi et 14 objets réutilisés sans nouvelle version, puis restauration exacte des données et du document vers un espace distinct. Les jetons de l’essai ont été effacés. Un autre PC et un autre compte restent à tester. Google est facultatif et aucun compte n’est connecté d’office ; voir la [confidentialité](https://github.com/clmtxx/PrepaPilot/blob/main/PRIVACY.md).

## Historique — vérification du 27 octobre 2026

## Livraison 2.26 — suivi souris sur toutes les pages

Les cartes suivent les événements de survol natifs qui traversent les textes, boutons et champs. Leur lumière se déplace sur toute la surface et entraîne les couches décoratives des illustrations. La sortie d’une illustration vers le texte ne recentre plus le dessin ; la sortie de la carte le ramène au repos. Les déplacements restent bornés à quelques pixels, sans déplacer les textes ni les contrôles.

Progression conserve les palettes, les dégradés et les fonds propres au travail, au sommeil, au sport et à la détente. Seuls le reflet et son liseré utilisent l’accent de la carte. Le score reste immobile. Les animations s’arrêtent lorsque la carte est masquée ou désactivée, ou lorsque les animations réduites sont choisies.

Les **60 tests existants ciblés** et **8 nouveaux tests de suivi** passent : événements réels sur les enfants et les sept pages, contenu ajouté après affichage, clic unique et saisie, défilement, stabilité des caches et de la géométrie, arrêt des effets et préservation exacte des couleurs de Progression. L’autotest source français vérifie aussi le suivi des sept pages. Les contrôles emploient uniquement des données fictives.

L’outil `Outils/verifier_suivi_souris.py` valide **28 parcours** (sept pages, deux thèmes et deux tailles) et produit **11 artefacts sans erreur**, dont un GIF du suivi depuis les textes. Les captures sont dans `.local/Verification/Suivi-souris-2.26`. Les vues de Progression conservent les fonds bleu, violet, vert et ambre, ainsi que le dégradé du bilan.

L’installateur et le ZIP portable Windows 2.26 ont été construits. Les diagnostics compilés français et anglais passent dans le constructeur puis dans le ZIP extrait ; ils incluent le suivi des sept pages et les accents de Progression. La version 2.26 est installée dans le projet, avec l’ancienne version archivée et les empreintes de tous les fichiers de données inchangées. Aucun accès Google ni aucune publication en ligne n’a été effectué.

## Historique — livraison 2.25

## Livraison 2.25 — connexion Google préparée par l’éditeur

Le parcours normal présente la connexion personnelle au compte Google ; l’import d’une configuration manuelle reste replié dans les options avancées. Si le client commun manque, les Réglages et le dialogue expliquent que l’éditeur doit le préparer. Le rappel de sauvegarde est masqué tant que cette version ne peut pas se connecter.

Les deux constructeurs acceptent un fichier OAuth Desktop commun, le valident et n’intègrent que l’identité de l’application dans une copie temporaire des ressources. Les connexions personnelles restent séparées sur chaque PC. Les publications par tag refusent un client absent ou invalide. Aucune configuration Google réelle n’a encore été créée : la connexion et les transferts réels restent à valider avec un compte autorisé.

Les groupes ciblés de 38 tests de sauvegardes, 16 tests OAuth, 4 tests d’installation Google, 6 tests de langues, 6 tests d’aide et 6 tests de configuration commune passent. Les 21 tests de distribution et 35 tests d’outils passent également, avec deux contrôles de liens ignorés faute de privilèges Windows. Le test de retour OAuth est effectué uniquement en boucle locale ; aucun échange avec Google n’est nécessaire. Douze captures synthétiques vérifient les états prêt, absent et avancé en français et anglais, dans les deux thèmes, dans `.local/Verification/Google-simplifie`.

Le constructeur Windows 2.25 a généré l’installateur et le ZIP portable. Ses autotests compilés français et anglais réussissent après adaptation du contrôle du rappel aux états configuré et non configuré. Le ZIP extrait a également passé ces deux diagnostics. La version 2.25 est installée dans le projet ; l’ancienne version est archivée et les empreintes de tous les fichiers de données restent identiques. Le contrôle de publication exigeant Google refuse correctement l’absence de client avant compilation. Les 11 tests de transferts Drive simulés passent également. Aucune publication en ligne n’a été effectuée.

## Historique — livraison 2.24

## Livraison 2.24 — navigation et retours d’interface

Les pages utilisent une transition directionnelle de 540 ms : panneau sortant en léger retrait, panneau entrant décalé de 100 à 180 pixels avec perspective et ombre de tranche. Les deux extrémités correspondent exactement aux pages capturées. Une navigation rapide reprend l’image actuellement visible. Les contrôles vivants restent immobiles ; clavier, souris, défilement, changement de thème, redimensionnement et animations réduites interrompent la décoration immédiatement. Les captures sont plafonnées à 2 millions de pixels et sont libérées à la fin ou au masquage.

Les notifications disposent d’un sceau compact, de catégories explicites, d’un message en texte brut sélectionnable et d’un bouton de copie intégrale. Les longs messages défilent dans une hauteur bornée. La durée de lecture varie de 4,2 à 12 secondes et se met en pause au survol ou au focus. Les champs actifs ont un cadre plus net et un fond légèrement teinté, sans déplacement des textes ni des zones de saisie. Les onglets indiquent leur raccourci clavier.

Les campagnes ciblées de **91 tests**, puis **24 tests d’intégration** et **24 tests de retours d’interface**, passent. Les derniers groupes couvrent les ajustements de géométrie de la barre de séance, la continuité d’une navigation rapide, les brouillons, la saisie pendant les notifications, la fermeture et les animations réduites. Les tests de copie utilisent un presse-papiers simulé. La suite complète de stockage n’a pas été répétée pour ces changements d’interface.

`Outils/verifier_navigation.py` produit **11 artefacts sans erreur** : huit planches dans les deux langues, thèmes et tailles, une vue de formulaire, une notification longue et un GIF de navigation. Les contrôles utilisent uniquement des données fictives. Les 107 navigations et 214 captures mesurées dans ce processus ne dépassent pas 932 184 pixels par capture ; ces mesures ne constituent pas une garantie de fréquence d’images sur une autre machine. Résultats : `.local/Verification/Navigation-2.24`.

Le programme Windows et ses ressources de version 2.24 ont été reconstruits. Les autotests compilés français et anglais ont réussi ; ils vérifient désormais une transition à mi-course et l’affichage/fermeture d’une notification. Aucune publication en ligne n’a été effectuée.

## Historique — livraison 2.23

## Livraison 2.23 — couleurs et détails équilibrés

La couleur revient dans les bandes hautes et les coins des cartes, avec des accents bleu, framboise, jade, ambre, violet et olive. Les zones de lecture restent neutres. L’onglet actif reprend la couleur de sa page ; les boutons utilisent le pigment de leur carte pour leurs liserés et leurs reflets. Des doubles coutures, de fines incrustations et un médaillon de verre teinté gradué complètent les surfaces. Aucune animation permanente ni modification de géométrie n’est ajoutée.

Les **56 tests ciblés** passent : boutons, surfaces, cache, illustrations, navigation, changement de thème, langues et affichage des sept pages. Ils incluent les nouveaux contrôles de teinte localisée, de centre de lecture neutre, de couleur de bouton, de danger et d’état désactivé. La suite complète de 799 tests validée en 2.22 n’a pas été répétée pour ce réglage visuel.

L’outil `Outils/verifier_finitions.py` produit **29 fichiers sans erreur** : 26 vues d’application en français/anglais, clair/sombre et deux tailles, deux planches d’animation et un GIF. Les comparaisons 2.22 → 2.23 sont dans `.local/Verification/Couleur2.23/Comparaisons`. Les surfaces pastel sont plus présentes sur l’accueil et Documents ; les couleurs fortes restent localisées. Les contrôles de clic, de zones interactives, de défilement et d’arrêt des animations passent. Les données utilisées sont fictives.

Les **32 tests d’outils et 17 tests de distribution** passent, avec deux contrôles de liens ignorés faute de privilèges Windows. L’application Windows et ses ressources de version 2.23 ont été reconstruites ; les autotests compilés français et anglais ont réussi sur une copie de préparation, avec des données temporaires. Aucune publication en ligne n’a été effectuée.

## Historique — livraison 2.22

## Livraison 2.22 — matériaux et mouvements de l’interface

L’interface utilise un fond papier en clair et ardoise en sombre, des accents plus profonds et des titres plus directs. Les boutons gardent leur rendu et leurs comportements Qt natifs : une lèvre et une tranche peintes ajoutent le relief, une compression de 110 ms accompagne la pression et un retour élastique de 290 ms suit le relâchement. Les reflets sont orientés par le pointeur ; les scintillements de bord durent 660 ms. Les cartes présentent une tranche, une facette, une gravure discrète et un reflet de 720 ms. Aucun effet ne déplace les textes ni les zones de clic, et les animations se terminent au repos.

Les **108 tests ciblés** passent : matériaux, événements souris/clavier, clic unique, désactivation et destruction, annulation immédiate des animations réduites, cache, illustrations, surfaces, transitions, navigation, langues et états de l’accueil. Ils comprennent **11 nouveaux tests** sur les boutons et les surfaces. Les **32 tests d’outils** passent, avec deux contrôles de liens ignorés faute de privilèges Windows.

`Outils/verifier_finitions.py` produit **26 captures et un GIF, sans erreur**, en français/anglais, clair/sombre et aux tailles 1 024 × 680 et 1 360 × 900. Le contrôle vérifie la stabilité des zones de clic, l’arrêt naturel des effets et leur interruption avec les animations réduites. Les données sont fictives. Les captures et le rapport se trouvent dans `.local/Verification/Finitions` ; l’aperçu GIF présente seize étapes d’une interaction, en lecture unique.

La version Windows 2.22 a été reconstruite avec ses ressources de version, puis les autotests compilés français et anglais ont réussi dans la préparation de distribution et sur la livraison finale extraite du ZIP. Les caches des cartes et illustrations conservent leurs plafonds ; aucun traitement réseau ni accès aux données n’est ajouté pendant les animations. La validation des effets au repos n’est pas une mesure de fréquence d’images sur toutes les machines.

## Historique — livraison 2.21

## Livraison 2.21 — rangement avec un assistant IA

**Documents → Ranger avec une IA** prépare un espace lisible, une notice bilingue, un inventaire des chemins exacts et une proposition JSON. L’aperçu précède l’application transactionnelle des changements et des nouveaux imports. Les originaux existants sont conservés. Aucun modèle IA ni appel réseau n’est intégré à cette passerelle ; l’assistant est choisi séparément.

Les **23 nouveaux tests** passent : correspondance des chemins et copies, préparation/reprise, import et classement, rejet des identifiants et chemins invalides, JSON ambigu, limites, propositions périmées ou modifiées après lecture, double application, échec de copie et rollback SQL, traductions, interface asynchrone, export complet et restauration Drive simulée. Les **81 tests de régression ciblés** sur les documents, dossiers, transferts, aide et traductions passent également. Les **32 tests d’outils** passent, avec deux contrôles de liens ignorés faute de privilèges Windows.

La suite existante a exécuté **765 tests : 764 réussis et un test de retour OAuth local en erreur** dans l’environnement restreint. Ce dernier a ensuite été relancé avec l’accès local nécessaire et a réussi, sans compte Google ni réseau Google. Aucune modification du code d’authentification n’a été nécessaire. La suite complète n’a pas été répétée après les ajustements finaux ; les tests ciblés couvrent les fichiers modifiés.

`Outils/verifier_rangement_ia.py` produit **24 captures sans erreur**, en français/anglais, clair/sombre et aux tailles 1 024 × 680 et 1 360 × 900. Les contrôles utilisent uniquement des cours fictifs ; l’affichage des chemins, la page Documents, les instructions et l’aperçu de proposition ont été inspectés. Résultats : `.local/Verification/Rangement-IA`.

La nouvelle application Windows a été reconstruite et ses **autotests compilés français et anglais ont réussi** avec une base temporaire. Ces autotests couvrent aussi la préparation et l’application d’un classement IA, l’intégrité du cours original et l’affichage du nouveau dialogue. Les sessions de rangement sont des fichiers locaux temporaires : leurs réglages d’autorité sont exclus des exports et invalidés après restauration ; le classement appliqué et les cours importés sont sauvegardés normalement.

La copie utilisée par le lanceur habituel a été remplacée par cette livraison testée ; l’ancienne version est archivée. Les empreintes de tous les fichiers des données personnelles sont inchangées après la mise à jour. Les **17 tests de distribution Windows** passent. L’installateur et le ZIP portable 2.21 ont été reconstruits à partir du même programme, avec deux nouveaux autotests sur leur copie de préparation. Aucune publication en ligne n’a été effectuée.

## Historique — livraison 2.20

## Livraison 2.20

La recherche globale locale, la barre de séance dans les autres espaces, l’aide hors connexion et les contrôles du diagnostic compilé sont intégrés. Aucun format de données ni schéma de base n’a été modifié. Le calcul de travail de l’accueil inclut maintenant les séances autonomes et exclut les activités non terminées, comme Progression.

**765 scénarios applicatifs distincts sont validés sur l’état final.** La suite globale a exécuté 763 tests : 762 réussis et une erreur dans une nouvelle fixture de test qui appelait une méthode inexistante. La fixture a été corrigée pour utiliser `save_subjects`, puis les 17 tests de recherche et navigation ont été relancés avec succès, dont cette fixture et le nouveau contrôle des décimales françaises/anglaises. Le scénario Google de retour OAuth local, exclu de cette exécution restreinte, a été exécuté séparément avec l’accès local nécessaire : réussi, sans compte ni réseau Google. Les 45 contrôles ciblés précédents passent également. Les **30 tests d’outils et 17 tests de distribution** passent ; deux contrôles de liens symboliques sont ignorés faute de privilèges Windows.

Le contrôle visuel produit **104 captures sans erreur** en français/anglais, clair/sombre, 1 024 × 680 et 1 360 × 900 : recherche globale et états vides, quatre rubriques de l’aide, séances en cours/pause/bilan sur Notes et Documents. La barre tronque les longs objectifs avec une info-bulle ; les informations restent accessibles au clavier. L’outil `Outils/verifier_lancement.py` utilise uniquement des données fictives et charge explicitement les polices Windows.

L’installateur **PrepaPilot-2.20.0-Setup.exe**, le ZIP **PrepaPilot-2.20.0-Windows-portable.zip** et leurs empreintes sont reconstruits avec les ressources de version Windows 2.20.0. Le builder a validé le programme natif en français et en anglais. Le ZIP final extrait a ensuite réussi trois essais natifs supplémentaires : français **32,22 s**, anglais **12,33 s**, français haute résolution ×2 **13,80 s**. Ces contrôles couvrent aussi la recherche réelle, l’aide, la barre de séance, la navigation et les sauvegardes avec une base temporaire.

Un premier diagnostic d’un binaire intermédiaire a provoqué une violation d’accès juste après une trace asynchrone à 15 secondes. Le watchdog `dump_traceback_later` a été retiré du mode diagnostic, en conservant `faulthandler.enable` et le délai externe de 180 secondes. L’inférence d’une course du watchdog s’appuie sur le moment des échecs et un [défaut de même famille documenté par CPython](https://github.com/python/cpython/issues/140815) ; elle ne constitue pas une preuve de causalité pour Python 3.12. Le défaut n’a pas été reproduit dans les trois essais du ZIP final, dont l’un dépasse largement 15 secondes. Les journaux initiaux restent conservés.

Les résultats détaillés se trouvent dans `.local/Verification/Lancement`. La copie de travail et les distributions sont préparées sans données personnelles. Le dépôt GitHub public et le client OAuth Google ne sont pas configurés : les fonctions locales et l’export complet sont disponibles, les services facultatifs seront activés après leur configuration. L’installateur local est sans signature d’éditeur ; aucune publication en ligne ni installation de l’installateur dans le compte Windows actif n’a été réalisée par cette validation.

## Historique — livraison 2.19 et amélioration de l’accueil

## Expérience utilisateur — 26 octobre 2026

L’accueil propose une action adaptée à la séance, une semaine de travail fondée sur les activités réalisées et un parcours de découverte fondé sur les données sauvegardées. Une palette d’actions accessible avec Ctrl+K donne accès aux fonctions et aux espaces. Les ajouts conservent les deux langues, les deux thèmes, le clavier et les animations réduites.

La suite globale a exécuté **732 tests : 731 réussis et un contrôle Google bloqué** par les restrictions système sur les connexions locales (`WinError 10013`). Ce contrôle concerne le retour OAuth local et ne dépend pas des changements d’interface. Les **16 tests ciblés** exécutés après les derniers ajustements passent : états de séance, travail autonome, suppression, changement d’objectif, historique des notes, lectures sans écriture, calcul hebdomadaire et traductions. Les sept tests de la palette passent également dans la suite globale.

Le contrôle visuel a produit **80 captures sans erreur** : français/anglais, clair/sombre, 1 024 × 680 et 1 360 × 900, accueil vide ou renseigné, séance en pause ou en bilan, cartes de progression et palette ouverte au clavier. Les données utilisées sont fictives. Les résultats sont dans `.local/Verification/Engagement` et les captures sont reproductibles avec `Outils/verifier_engagement.py`. L’avertissement de polices Qt est compensé dans cet outil par le chargement explicite des polices Windows.

La version Windows a été reconstruite et ses **autotests natifs français et anglais ont réussi**. Elle a remplacé la copie de `Application/PrepaPilot` avec l’outil transactionnel du projet : l’ancien programme est archivé dans `.local/Archives/PrepaPilot-v2.19.0`, la taille et la date de modification de la base personnelle sont inchangées, et l’empreinte de l’exécutable installé correspond à celle du programme testé. Les sources du dossier GitHub sont synchronisées. Les **30 tests des outils et 17 tests de distribution** passent ; deux contrôles de liens symboliques sont ignorés faute de privilèges Windows. Les archives de partage et les installateurs de publication n’ont pas été régénérés.

Limite diagnostique : un premier autotest du binaire avec le plugin Qt `offscreen` a provoqué une violation d’accès pendant les animations. Cet échec n’est pas reproduit par les sources avec le même plugin ni par les deux autotests natifs du binaire. La validation Windows utilise donc l’affichage natif ; le journal du premier essai reste conservé dans l’historique de cette intervention.

Audit complémentaire des sources du **25 octobre 2026** : **711 tests applicatifs, 30 tests des outils et 17 tests de distribution réussis**, avec 63 nouveaux tests applicatifs ; deux contrôles de liens symboliques ignorés. Les bugs reproduits, corrections, 96 captures et limites sont détaillés dans [le rapport d’audit](../../Documentation/Audit-2026-10-25.md). Les corrections sont dans les sources ; l’exécutable et les distributions n’ont pas été reconstruits pendant cet audit. Le compte rendu ci-dessous décrit la livraison du 24 octobre.

## Mises à jour depuis l’application

La version installée peut rechercher une version publique stable, afficher une notification et proposer Télécharger et installer dans Réglages → Mises à jour. La vérification automatique est facultative, au plus une fois par jour, et ne lance aucun téléchargement. Les préférences et téléchargements restent propres à ce PC, hors des exports scolaires. Le portable ouvre la page de la nouvelle version avec les indications de transfert.

Le téléchargement vérifie le dépôt et les adresses GitHub, la taille, l’empreinte SHA256 et le format de l’installateur. Une dernière vérification détecte un fichier modifié dans le cache. Après confirmation, l’application sauvegarde sa séance, ferme la base et libère son verrou avant de lancer l’installation. Une erreur de sauvegarde ou une annulation empêche la fermeture. Le programme ne transmet aucune donnée scolaire au service de mise à jour.

Le dépôt du propriétaire n’est pas encore créé. Cette construction locale reste donc sans canal de téléchargement. Le workflow GitHub injecte automatiquement l’adresse du futur dépôt dans les versions qu’il construit ; les utilisateurs devront recevoir cette première version construite depuis le dépôt. Les versions locales peuvent aussi être configurées avec --repository. Aucun dépôt fictif ni jeton n’est intégré.

## Contrôles réalisés

La copie locale `Application/PrepaPilot` est en version 2.19.0, avec un exécutable identique à celui du ZIP. Ses **3 fichiers de données** sont identiques avant et après mise à jour. Le programme 2.18.0 est conservé dans les archives locales voisines.

La suite complète a réussi ses **648 tests** en 427 secondes, dont 51 contrôles du moteur, du panneau, du lancement et de l’intégration. Les **17 tests de distribution** ont réussi. Les outils ont terminé **32 contrôles : 30 réussis, 2 ignorés** faute de privilège Windows pour les liens symboliques.

Le panneau et le bandeau ont été contrôlés dans **41 états** : français/anglais, clair/sombre, 1 024 × 680 et 1 360 × 900, disponibilité, téléchargement, attente d’installation, erreur et canal absent. Quatre captures ont été inspectées. Le changement de langue conserve le contrôleur et la préférence automatique.

Le programme Windows compilé a réussi ses autotests en français et en anglais sans recherche réseau. Une vraie installation 2.17.0 a été remplacée par la 2.19.0 dans le même dossier, sans désinstallation intermédiaire. La version installée a été contrôlée et ses deux autotests ont réussi. Les empreintes de la base et du témoin fictifs et la préférence anglaise sont conservées après mise à jour puis désinstallation.

Le moteur a également vérifié le véritable installateur 2.19 avec un service GitHub simulé : métadonnées, téléchargement, empreinte et commande finale. L’essai en ligne avec le dépôt public restera à effectuer après sa création et sa première Release ; aucune recherche en ligne sur un dépôt fictif n’a été exécutée.

## Historique de validation — version 2.18.0 du 24 octobre 2026

## Couleurs, dégradés et encadrés

Les six espaces illustrés disposent de palettes plus saturées : bleu électrique, rose, vert, ambre, violet et citron vert. Les cartes utilisent des fonds dégradés persistants, des contours colorés et un reflet intérieur. Les panneaux de Progression et Succès reprennent cette intensité, en conservant les couleurs des quatre domaines. Les boutons primaires et les onglets actifs sont davantage mis en valeur.

Les fonds restent visibles avec les animations réduites. Les surfaces décoratives conservent leur cache borné à 220 000 pixels ; les contrôles et les textes restent natifs. Le survol des boutons ne change pas leur géométrie, la désactivation arrête leurs animations et le focus clavier est visible dans les deux thèmes. Les dégradés des boutons primaires gardent un contraste d’au moins 4,5:1 avec leur texte au repos et au survol.

Les suites ciblées ont réussi : **57 contrôles** d’application, navigation, transitions, plein écran et cache ; **20 contrôles** de surfaces et figures de page ; **14 contrôles** des widgets et animations ; **36 contrôles** de Progression et Succès. Les contrôles de cache communs à deux suites ne constituent pas des tests supplémentaires.

`Outils/verifier_couleurs.py --label apres` a produit **48 captures** avec des données fictives : sept pages, Succès, thèmes clair et sombre, fenêtres de 1 360 × 900 et 1 024 × 680, plus le bas des petites fenêtres. Aucun débordement horizontal, titre d’introduction tronqué ou défaut de peinture Qt n’a été détecté. Les captures et le rapport sont conservés dans `.local/Verification/Couleurs/apres` du projet. L’accueil, Progression, Notes, Documents et Succès ont été inspectés visuellement.

Les sept pages et Succès ont également été contrôlés en anglais à 1 024 × 680 dans les deux thèmes : **32 captures**, sans débordement, titre tronqué, bouton de navigation coupé ou erreur de peinture. Le rapport est dans `.local/Verification/Couleurs/anglais`.

Les modules d’apparence et le numéro de version 2.18.0 ont aussi été vérifiés dans l’exécutable reconstruit. Cet exécutable a réussi son autotest natif en français puis en anglais, avec code retour 0 et marqueur de succès frais après chaque essai. Les essais utilisent exclusivement des bases temporaires et ne nécessitent aucune connexion réseau.

## Historique de validation — version 2.17.0 du 24 octobre 2026

## Interface française et anglaise

Le premier lancement propose Français ou English avant la présentation et la configuration des matières. Le choix est mémorisé et modifiable dans Réglages → Langue → Enregistrer mon profil (Settings → Language → Save preferences), sans redémarrage. Les 1269 messages du catalogue couvrent les pages, dialogues, erreurs, graphiques, succès, dates et sauvegardes. Les textes personnels et les documents ne sont pas traduits.

Le changement de langue conserve les brouillons, la sélection et l’aperçu des documents, les filtres, les dates, les modes des graphiques et la séance de travail en cours. Le temps de reconstruction de l’interface est exclu du chronomètre. Une restauration conserve la langue choisie sur ce PC, y compris l’absence de préférence avant son premier choix.

## Vérifications réalisées

La version 2.17.0 est installée dans `Application/PrepaPilot`. Son exécutable a la même empreinte que le ZIP portable testé. Les **3 fichiers de données présents** sont identiques avant et après mise à jour ; l’ancienne version 2.16.0 est archivée dans l’espace local voisin.

La suite complète a réussi ses **597 tests** en 326 secondes. Les **10 tests de construction des distributions** ont réussi. Les outils de maintenance ont terminé leurs **30 contrôles : 28 réussis et 2 ignorés**, faute de privilège Windows pour les liens symboliques. Leur dossier temporaire court évite la limite de longueur des chemins Windows des archives de test.

Les sept pages ont été contrôlées en anglais dans les thèmes clair (1 360 × 900) et sombre (1 024 × 680). Le choix initial, l’accueil et les deux étapes de configuration en anglais ont aussi été vérifiés. Dix-sept captures de contrôle ont été inspectées, sans débordement constaté.

L’application Windows compilée a réussi son autotest natif en français puis en anglais. L’installateur bilingue a réussi un cycle réel installation, lancement en anglais, réinstallation et désinstallation dans un espace isolé. La préférence anglaise est persistante ; la base et le fichier témoin fictifs gardent les mêmes empreintes après réinstallation et désinstallation. L’archive portable est vérifiée sans données ni marqueur d’installation, avec les deux guides.

Les essais Google utilisent un service simulé. La publication GitHub et l’activation réelle de Google Drive restent les opérations du propriétaire décrites dans leurs guides.

## Historique de validation — version 2.16.0 du 20 octobre 2026

## Verre satiné, sculptures et navigation

Les introductions des pages présentent des rubans de verre satiné et un passage de lumière fini de 900 ms. Les sculptures partagent des orbites, des cristaux facettés et des perles sur plusieurs plans de profondeur ; un éclat de 760 ms accompagne le survol. Le repère sous l’onglet actif se déplace en 260 ms sans déplacer les boutons. Les aperçus colorés disposent d’une entrée de 230 ms, d’un léger relief et d’un reflet. Les transitions de page gardent une image de fond continue pour éviter le voile gris du double fondu.

Les effets sont finis, sans animation décorative permanente ni lecture de la base à chaque image. Les contrôles, les textes, la saisie et la navigation au clavier restent natifs. Les animations réduites arrêtent les nouveaux mouvements immédiatement. Le masquage des objets et la fermeture libèrent leurs animations ; le changement de thème ou de taille reconstruit uniquement les surfaces concernées.

Les fonds de cartes sont mis en cache avec un plafond de 220 000 pixels par carte, indépendamment de la résolution native du texte et des contrôles. Les figures conservent leurs calques en mémoire à leur taille d’affichage. Les aperçus plafonnent leur capture intermédiaire à 500 000 pixels ; les transitions restent limitées à deux captures de 2 millions de pixels. Les tests ciblés ont réussi leurs **54 contrôles**, couvrant ces limites, la réutilisation des dessins et la conservation du focus, des champs, du défilement et des données.

`Outils/verifier_interface.py` a contrôlé les sept pages, les dialogues et les états interactifs en clair et en sombre, à 1 360 × 900 et 1 024 × 680. Aucun débordement ni erreur Qt n’a été détecté. Les captures de l’accueil, des notes, de Progression et des aperçus ont été inspectées visuellement. Les images sont conservées dans `Verification/Interface-2.16` de l’espace local voisin.

Sur cette machine, le jeu fictif de 2 000 notes, 600 documents et 400 jours d’activités mesure un démarrage de 2 475 ms contre 2 699 ms avant modification ; les rafraîchissements restent proches de la référence (notes 19,77 ms contre 19,84 ms, documents 22,68 ms contre 23,92 ms, Progression 2,09 ms contre 2,16 ms). La capture d’une page reste autour de 15 ms (15,31 contre 14,87 ms). Ces mesures hors écran ne garantissent pas une fréquence d’affichage sur un autre PC. Le banc de dessin mesure une réduction médiane de 63,7 % pour les fonds de cartes mis en cache par rapport à leur reconstruction à chaque image, et de 90 à 91 % pour les nouvelles sculptures d’accueil et de sommeil par rapport au dessin vectoriel à chaque image.

La suite complète de **542 tests** a réussi en 280 secondes. Les 27 contrôles de maintenance ont terminé avec 25 réussites et deux tests ignorés faute de privilège Windows pour créer des liens symboliques. Le programme Windows construit a réussi son autotest natif : sept pages, indicateur de navigation, nouveaux objets, animations réduites, aperçus, plein écran, notes, documents, séances et sauvegardes hors connexion.

La version 2.16.0 est installée dans `Application/PrepaPilot`. Son exécutable possède la même empreinte SHA-256 que la livraison testée. Les trois fichiers de données présents sont identiques avant et après installation. La version 2.15.1 est archivée dans l’espace local voisin ; l’organisation du dossier partagé est conservée.

## Historique de validation — version 2.15.1 du 20 octobre 2026

## Diamant à 80 heures par semaine et 320 heures par mois

Les paliers hebdomadaires passent à 25, 40, 55, 65 et 80 heures ; les mensuels à 100, 160, 220, 260 et 320 heures. Les semaines restent du lundi au dimanche et les mois suivent le calendrier. Le travail cumulé, le sommeil, le sport et les quêtes conservent leurs règles.

Les identifiants des nouveaux paliers hebdomadaires et mensuels sont distincts. Les récompenses précédentes conservent leur objectif d’origine, leur date et leurs XP dans l’historique, sans valider artificiellement les objectifs plus élevés. Le journal existant alimente les nouveaux paliers. Les tests couvrent la restauration locale et Google Drive simulée des deux générations de récompenses, sans doublon de XP lors d’un second import. Une version 2.15.1 ou ultérieure est nécessaire pour restaurer les nouveaux identifiants ; les anciennes sauvegardes restent lisibles.

La suite complète de **526 tests** a réussi en 267 secondes, dont **63 contrôles des succès**. Les seuils sont vérifiés à la minute près, juste avant et au moment de leur atteinte. Les 27 contrôles de maintenance ont terminé avec 25 réussites et deux tests ignorés faute de privilège Windows pour créer des liens symboliques.

Le programme Windows construit a réussi son autotest natif, comprenant une vérification explicite des cinq nouveaux paliers hebdomadaires et mensuels. Le contrôle visuel a capturé les deux thèmes à 1 360 × 900 et 1 024 × 680, sans erreur Qt ni débordement détecté. Les captures des Diamants à 80 h et 320 h et de l’historique des anciens objectifs ont été inspectées. Elles sont conservées dans `Verification/Succes-2.15.1` de l’espace local voisin.

La version 2.15.1 est installée dans `Application/PrepaPilot`. L’empreinte SHA-256 de l’exécutable correspond à celle de la livraison testée. Les trois fichiers de données présents sont identiques avant et après installation. La version 2.15.0 est conservée dans les archives locales voisines.

## Historique de validation — version 2.15.0 du 19 octobre 2026

## Barème de travail renforcé et succès sportifs

Les paliers de travail cumulé passent à 50, 150, 400, 800 et 1 500 heures. Les meilleures semaines visent 25, 35, 45, 55 et 60 heures ; les meilleurs mois 100, 140, 180, 220 et 250 heures, cours compris. Les quêtes de travail demandent désormais 25 heures sur une semaine, cinq jours de deux heures sur une semaine, ou vingt jours de deux heures sur un mois. Le barème de sommeil est conservé.

Deux collections sportives portent le total à trente médailles : 1, 5, 15, 30 et 60 heures cumulées, puis des séries de 2, 4, 8, 12 et 24 semaines consécutives contenant au moins une heure de sport. Les catégories Sport et EPS alimentent ces compteurs, indépendamment du travail. Deux nouvelles quêtes récompensent une heure de sport hebdomadaire et deux journées avec vingt minutes de sport. Les six quêtes et six collections réutilisent leurs cartes et leurs illustrations en mémoire.

Les anciens succès de travail gardent leurs identifiants, leurs dates et leurs XP dans l’historique des anciens barèmes. Les nouveaux seuils ont des identifiants distincts ; une médaille obtenue pour cinq heures ne valide donc pas artificiellement un objectif de cinquante heures. Tout le travail déjà renseigné est pris en compte pour les nouveaux paliers. L’historique affiche au plus cent récompenses, avec l’ancien objectif ou la période de quête, sans supprimer les autres récompenses du registre.

Les sauvegardes Drive et locales transportent ensemble l’ancien barème, le nouveau et les succès sportifs. Les tests vérifient un aller-retour sans journal source, le maintien des XP et l’absence de récompenses réattribuées au deuxième import. Une version 2.15 ou ultérieure est nécessaire pour lire les nouveaux identifiants ; cette version continue à lire les anciennes sauvegardes. Les échanges Drive sont simulés, sans activation d’un compte Google réel.

`Outils/verifier_succes.py` a capturé les six collections, les quêtes, les paliers sportifs et l’historique en thèmes clair et sombre à 1 360 × 900 et 1 024 × 680. Aucun débordement ni erreur Qt n’a été détecté. Les captures sont conservées dans `Verification/Succes-2.15` de l’espace local voisin. Le rendu des cartes sportives, des cinq médailles et de l’historique a été inspecté visuellement.

L’exécutable Windows construit a réussi son autotest natif, avec déblocage et persistance d’une médaille sportive après une heure réalisée, présence des six collections, changements de thème et animations réduites. Les contrôles existants des sept pages, séances, notes, documents, plein écran et sauvegardes hors connexion ont également réussi. Les outils de maintenance ont terminé leurs 27 contrôles : 25 réussites et deux tests ignorés faute de droit Windows de créer des liens symboliques.

La suite complète de **523 tests** a réussi le 19 octobre 2026 en 264 secondes, dont 60 contrôles dédiés aux succès. Elle couvre les seuils exacts du nouveau barème, les séries sportives, les frontières de semaine, la séparation travail/sport, la conservation des anciennes récompenses, les transferts mixtes et les effets visuels. Les tests de rendu comprennent également la lecture des anciens objectifs et des périodes de quête dans l’historique.

La version 2.15.0 est installée dans `Application/PrepaPilot`. L’empreinte SHA-256 de son exécutable correspond à celle de la livraison testée. Les trois fichiers de données présents sont identiques avant et après installation. La version 2.14.0 est conservée dans les archives locales voisines, sans modifier l’organisation du projet.

## Historique de validation — version 2.14.0 du 19 octobre 2026

## Succès, médailles et quêtes

L’espace **Progression → Succès** propose vingt médailles réparties entre le travail total, la meilleure semaine, le meilleur mois et la meilleure série de nuits d’au moins huit heures. Les cinq paliers Bronze, Argent, Or, Platine et Diamant ont des illustrations en relief progressivement enrichies. Quatre quêtes reviennent chaque semaine ou chaque mois. Les XP et niveaux sont dérivés des récompenses acquises, sans compteur indépendant susceptible de doubler lors d’un import.

Le moteur retient uniquement les activités réalisées, terminées et non supprimées. Il prend en compte les matières personnalisées et archivées, les cours et le travail autonome. Il découpe le travail aux frontières des journées, semaines et mois, et regroupe le sommeil par fenêtres de midi à midi attribuées au réveil. Les chevauchements sont dédupliqués. Les quêtes possèdent un identifiant par période ; les médailles et quêtes obtenues restent acquises après correction du journal. Les anciens historiques sont reconnus au démarrage.

Les récompenses sont automatiquement incluses dans toutes les sélections Google Drive, indépendamment du travail et du sommeil. Les restaurations Drive réunissent les collections locale et sauvegardée, gardent la première date d’obtention et n’ajoutent aucun XP en double. Les anciens fichiers restent compatibles. Le transfert local complet contient le registre et restaure l’état de l’archive. Les registres malformés sont rejetés avant remplacement des données. Les tests Drive utilisent un service simulé ; l’activation et le contrôle avec un vrai compte Google restent à effectuer.

Les médailles réutilisent leur dessin en mémoire pendant le survol et la courte célébration. Aucun effet ne tourne en boucle au repos. Le mode de réduction des animations arrête immédiatement les effets ; la fermeture du panneau annule aussi les animations de ses cartes. L’interface conserve ses widgets lors des rafraîchissements et réutilise le rapport lorsque les données et la minute courante restent identiques.

## Vérifications de la livraison

La suite générale de **499 tests** a réussi le 19 octobre 2026 en 275 secondes. Après les ajustements visuels, les **42 tests dédiés aux succès** ont tous réussi, dont six contrôles visuels supplémentaires : cela couvre **505 tests distincts**. Les tests vérifient notamment les frontières calendaires et années bissextiles, les nuits traversant minuit, les corrections, les restaurations sélectives, l’absence de doublons, les caches et les animations réduites. Les 27 contrôles de maintenance ont terminé avec 25 réussites et deux contrôles ignorés faute de droit Windows de créer des liens symboliques.

`Outils/verifier_succes.py` a capturé l’état vide, les quêtes, les collections et les dialogues de paliers dans les deux thèmes à 1 360 × 900 et 1 024 × 680. Aucun débordement horizontal ni erreur Qt n’a été détecté. Les dialogues restent à 600 pixels de hauteur et permettent de parcourir les cinq paliers. Le rendu de la vitrine, des cinq médailles, des collections et des dialogues a été inspecté visuellement.

Le programme Windows construit a réussi son autotest natif : déblocage et persistance d’une médaille depuis une activité, affichage de la collection, changements de thème, animations réduites, ainsi que les contrôles existants des sept pages, séances, notes, documents, plein écran et dialogue Google hors connexion.

La version 2.14.0 est installée dans `Application/PrepaPilot`. Son exécutable possède la même empreinte SHA-256 que la livraison testée. Les trois fichiers de données présents sont identiques avant et après installation. L’ancien programme 2.13.0 est conservé dans les archives locales voisines ; l’organisation du dossier est inchangée.

## Historique de validation — version 2.13.0 du 18 octobre 2026

## Dossiers de documents et recherche globale

La bibliothèque propose des dossiers libres, leur création et leur renommage. Chaque document peut être rangé à l’import, lors d’une modification ou avec le bouton « Ranger » après une sélection simple ou multiple (Ctrl/Maj). Les dossiers sont des classements logiques : changer de dossier ne copie ni ne déplace le fichier original géré. Retirer un dossier demande confirmation et conserve ses documents dans « Sans dossier ». « Tous les documents » reste disponible.

La recherche porte sur le titre, le nom d’origine et la description. « Rechercher partout », coché par défaut, recherche dans tous les documents indépendamment du dossier, de la matière et du type sélectionnés. Les filtres sont temporairement désactivés pendant cette recherche globale. Décocher l’option applique les filtres ; effacer la recherche retrouve le dossier et les filtres choisis. La temporisation de recherche et les effets visuels existants sont conservés.

La migration ajoute le classement sans modifier les documents existants. Les noms sont contrôlés, normalisés en Unicode et uniques sans tenir compte des majuscules. Les déplacements multiples et la suppression d’un dossier sont transactionnels. Une destination supprimée pendant la copie d’un import est détectée avant validation.

L’export complet et les sauvegardes Drive « Documents et fichiers de cours » incluent les dossiers, y compris ceux qui sont vides. Les autres sélections Drive conservent le classement local. Les anciennes sauvegardes restent importables, avec des documents sans dossier. Les identifiants, noms et références invalides sont refusés avant remplacement des données. Les tests Drive utilisent un service simulé, sans activer de compte Google.

La suite complète de **463 tests** a réussi le 18 octobre 2026 en 153 secondes, dont 32 nouveaux contrôles du stockage, des transferts et de l’interface des dossiers. Les 27 contrôles des outils de maintenance ont terminé : 25 réussites et deux contrôles ignorés faute de droit Windows de créer des liens symboliques.

`Outils/verifier_dossiers.py` a rendu la bibliothèque, la recherche globale et les dialogues dans les deux thèmes, à 1 360 × 900 et 1 024 × 680, y compris avec des noms de dossiers de 100 caractères. Aucun débordement ni erreur Qt n’a été détecté ; les dialogues restent sous 640 pixels de hauteur et leurs boutons sont accessibles. La bibliothèque, une recherche dans un autre dossier et le formulaire de modification ont été inspectés visuellement.

L’exécutable Windows 2.13.0 a réussi son autotest natif sur des données temporaires : création des dossiers, recherche par nom d’origine malgré des filtres différents, rangement avec le dialogue, renommage et retrait d’un dossier sans perte de fichier. Les contrôles existants de navigation, notes, séances, bilans, thèmes, animations, plein écran et dialogue Google hors connexion ont également réussi.

La version installée possède la même empreinte SHA-256 que la livraison testée. Les trois fichiers de données présents sont identiques avant et après installation ; la migration du classement s’effectuera à la prochaine ouverture. L’ancien programme 2.12.0 est conservé dans les archives locales voisines. L’organisation du dossier reste inchangée.

## Historique de validation — version 2.12.0 du 16 octobre 2026

## Séances de travail reliées au journal

La carte de concentration de l’accueil propose une matière, le travail autonome ou un minuteur libre, une durée de 1 à 240 minutes et un objectif facultatif. Elle permet de démarrer, mettre en pause, reprendre, terminer avant la fin ou abandonner après confirmation. Une séance terminée attend une validation explicite dans son bilan ; aucun temps n’est ajouté automatiquement au journal.

Le bilan sépare les périodes de travail des pauses. Les horaires, le libellé et la matière peuvent être corrigés ; une période peut être retirée. « Plus tard » conserve les corrections, « Ignorer la séance » supprime le brouillon après confirmation. Le journal travaille à la minute : chaque début est arrondi vers la minute suivante et chaque fin vers la précédente, sans inventer de temps ni remplir les pauses. Les périodes sans minute complète ne sont pas proposées à l’enregistrement. Cette règle est expliquée dans le bilan.

Le minuteur compare l’horloge locale et une horloge monotone. Une interruption ou un saut d’horloge met la séance en pause au dernier instant fiable. Les secondes sont calculées en mémoire ; un point de reprise est conservé environ toutes les 15 secondes. Une fermeture normale conserve le temps observé et met la séance en pause ; après une fermeture inattendue, les dernières secondes non sauvegardées peuvent manquer. Le temps passé hors de l’application n’est pas compté.

L’enregistrement vérifie les horaires et les conflits avant toute insertion. Les activités et le marqueur de validation sont écrits dans une transaction SQLite commune. Une répétition de la validation ne crée pas de doublon ; une instance périmée ne peut pas réécrire un ancien état. Les erreurs de stockage laissent la séance disponible, avec des commandes cohérentes avec son état.

L’export complet conserve le brouillon. Google Drive l’inclut avec « Travail, sport et autres activités », remappe sa matière et ses références au journal lors d’une restauration partielle, et préserve les catégories non sélectionnées. Une séance importée en cours reprend en pause. Les données incohérentes sont refusées avant remplacement. Les contrôles Drive utilisent un service simulé, sans connexion à un compte Google.

`Outils/verifier_seances.py` a rendu l’accueil, la préparation et le bilan dans les deux thèmes, à 1 360 × 900 et 1 024 × 680. Aucun débordement horizontal de l’accueil ni erreur Qt n’a été détecté ; les dialogues restent sous 640 pixels de hauteur. Le bilan et la carte de concentration ont été inspectés visuellement.

Les 27 contrôles des outils de maintenance ont terminé : 25 réussites et deux contrôles ignorés faute de droit Windows de créer des liens symboliques.

La suite complète de **431 tests** a réussi le 16 octobre 2026 en 216 secondes. Elle couvre les fonctions existantes et 55 nouveaux contrôles des séances : pauses, interruptions, erreurs de stockage, enregistrement atomique, absence de doublons, corrections, dialogues, intégration à l’accueil, reprise et transferts locaux ou Drive.

L’exécutable Windows 2.12.0 a réussi son autotest natif avec une base temporaire : fin du minuteur, rendu du bilan, ajout au journal et seconde validation sans doublon. Les contrôles existants des sept pages, notes, bilans, thèmes, animations, plein écran et dialogue Google hors connexion ont également réussi.

La version installée possède la même empreinte SHA-256 que la livraison testée. Les trois fichiers de données présents ont des empreintes identiques avant et après installation. L’ancien programme 2.11.0 est conservé dans les archives locales voisines ; l’organisation du projet est inchangée.

## Historique de validation — version 2.11.0 du 14 octobre 2026

## Moyenne de classe et classement facultatifs

Le formulaire de note comporte deux onglets : Évaluation et Classe · facultatif. La moyenne de classe et le classement sont activés séparément et peuvent être ajoutés, modifiés ou retirés. La moyenne conserve le barème de l’évaluation et accepte zéro ; le classement exige une position et un effectif entiers positifs, avec une position inférieure ou égale à l’effectif. Une modification de barème ne tronque pas silencieusement la moyenne de classe. Ces informations n’interviennent pas dans les statistiques personnelles.

Le graphique des notes ajoute les moyennes connues sur 20 avec des pointillés violets et des marqueurs en losange. Un sélecteur affiche l’évolution du classement absolu, première place en haut, avec position et effectif exacts au survol. Les valeurs inconnues ne deviennent ni zéro ni classement inventé. L’historique conserve le détail et masque les colonnes facultatives entièrement vides. Les caches, le rendu dans les deux thèmes et la réduction des animations sont préservés.

La migration SQLite conserve les notes existantes, leurs identifiants, la séquence, les index et les déclencheurs. Les trois champs ajoutés sont laissés vides sur les anciennes notes. Le CSV, l’export complet et les sauvegardes Google Drive incluant les notes conservent les compléments. Les anciennes archives et sauvegardes Drive restent importables. Les importations refusent les données incohérentes avant de modifier les données locales. Les tests Drive utilisent un service simulé ; ils n’activent aucun compte Google.

La suite complète de **376 tests** a réussi le 14 octobre 2026. Elle couvre la saisie indépendante des options, la moyenne zéro, les barèmes, l’effacement, les classements incomplets et invalides, les migrations, les transferts et sauvegardes, les statistiques inchangées, les boutons des graphiques et l’invalidation des caches.

`Outils/verifier_notes.py` a produit les captures des graphiques, de l’historique, des champs facultatifs et des erreurs de saisie dans les deux thèmes, à 1 360 × 900 et 1 024 × 680. Aucun débordement ni erreur Qt n’a été détecté ; le formulaire et ses boutons restent accessibles sous 640 pixels de hauteur. Les graphiques et le formulaire ont été inspectés visuellement.

L’exécutable Windows 2.11.0 a réussi son autotest natif avec une base temporaire : création d’une note avec moyenne et classement, conversion du barème, bascule et rendu des deux graphiques, réouverture en modification et retrait des informations facultatives. Les contrôles existants des sept pages, thèmes, animations, plein écran et dialogue Google hors connexion ont également réussi.

La version installée possède la même empreinte SHA-256 que la livraison testée. Les trois fichiers de données présents ont des empreintes identiques avant et après installation ; la migration des champs s’exécutera à la prochaine ouverture. L’ancien programme 2.10.0 est conservé dans les archives locales voisines.

## Historique de validation — version 2.10.0 du 12 octobre 2026

## Fluidité et coût des animations

Les figures 3D conservent leurs ombres, couleurs et mouvements. Leurs calques fixes sont réutilisés à la résolution de l’écran, avec invalidation au changement de thème, taille ou densité de pixels. Une seule version des calques est conservée par figure. Les grands fonds de cartes ne sont pas dupliqués en cache. Les titres réutilisent leur mise en page pendant le reflet.

Le graphique des notes prépare ses axes et tracés une fois, puis révèle ces images progressivement. Les infobulles conservent les mêmes données, avec une recherche spatiale des points. Modifier une note, changer d’année, de police, de taille ou de thème renouvelle le rendu. L’historique annuel de Progression distribue les activités entre les mois en un seul passage ; les navigations entre périodes réutilisent l’historique lorsque les données, l’année et la minute de calcul sont inchangées.

Les modifications sont annoncées par domaine : enregistrer un repère ne reconstruit plus les notes, les documents et les bilans. Les imports et les notifications sans domaine conservent un rafraîchissement complet. La lecture de l’année scolaire n’est plus répétée pour chaque note ; les couleurs des matières ne sont plus relues pour chaque document. Les cartes de statistiques des notes restent en place et un tableau inchangé n’est pas reconstruit. Les opérations groupées suspendent les redraws intermédiaires et restaurent les signaux même en cas d’exception. Enregistrer un profil sans changer de thème ne réapplique plus toute la feuille de style.

Le défilement à la molette suit une animation cumulative de 180 ms ; pavé tactile, clavier et glissement des barres restent natifs. Les animations réduites désactivent ce mouvement. Le retour visuel d’une nouvelle ligne ne repeint plus toute la table et ne lit plus SQLite à chaque image.

Les aperçus utilisent une petite image réutilisable, invalidée par les changements de données, thème, géométrie, navigation et état dynamique des pages. Un rendu intermédiaire préserve les textes des champs Qt avant réduction. Les transitions conservent fondu et déplacement, avec des captures bornées à deux millions de pixels chacune ; la page réelle reste affichée à sa résolution native après la transition.

## Mesures reproductibles

`Outils/mesurer_fluidite.py` utilise exclusivement une base temporaire fictive : 2 000 notes, 600 documents, 400 jours d’activités. Les rapports sont dans `Verification/Fluidite` du dossier local voisin. Durées médianes de cinq appels, Qt hors écran à 1 360 × 900, sur cette machine :

| Opération | Avant | Après |
| --- | ---: | ---: |
| Lecture des 2 000 notes de l’année | 113,00 ms ; 4 001 requêtes | 12,46 ms ; 2 requêtes |
| Actualisation des notes inchangées | 371,90 ms | 14,98 ms |
| Actualisation des 600 documents | 162,80 ms ; 605 requêtes | 21,33 ms ; 5 requêtes |
| Notification d’un changement de repère | 451,58 ms | 1,89 ms |
| Notification de changement complet | 575,13 ms | 142,65 ms |

Le benchmark `tests/benchmark_visual_rendering.py` compare les mêmes formes vectorielles, dans le même processus, avec et sans leurs calques : sculpture 9,084 → 0,834 ms/image ; lune 2,777 → 0,233 ; figure d’accueil 2,825 → 0,225 ; score 2,422 → 0,792. Les captures commencent après une phase de chauffe.

Une mesure ciblée du graphique de 2 000 notes et 30 types à 1 000 × 240 donne 387,34 → 0,68 ms par capture médiane après préparation. La première préparation coûte encore environ 248 ms dans ce cas volontairement chargé. Le calcul annuel, testé séparément avec un lecteur fictif non filtré de 21 900 activités, passe de 808 à 93 ms.

Ces résultats mesurent des opérations précises, pas une fréquence garantie pour toute l’application. Les premières préparations, les imports de gros fichiers, la vitesse du disque, la résolution et le matériel influencent toujours les temps de réponse. Aucun effet visuel ni fonction utilisateur n’a été supprimé ; aucune dépendance n’a été ajoutée.

## Contrôles de la version 2.10.0

La suite complète de 351 tests a réussi le 12 octobre 2026. Un dernier contrôle de fraîcheur du minuteur a ensuite été ajouté : les 12 tests des aperçus ont réussi sur le correctif final, portant à 352 le nombre de tests distincts validés. Ils couvrent aussi les nouvelles invalidations des caches, les graphiques, les rafraîchissements ciblés, les signaux imbriqués, la durée de vie des pages, le regroupement des recherches, le défilement, les aperçus passifs et la limitation de mémoire des transitions. Les 27 tests des outils de maintenance ont également terminé : 25 réussites et deux contrôles ignorés faute de droit Windows de créer des liens symboliques.

Les sept pages ont été rendues dans les deux thèmes à 1 360 × 900 et 1 024 × 680. Les captures et le contrôle des zones de contenu ne signalent aucune erreur Qt ni débordement horizontal. L’accueil, les notes, Progression et l’aperçu de navigation ont été inspectés visuellement.

L’exécutable final 2.10.0 a passé l’autotest Windows : configuration, navigation, illustrations, bilans, thèmes, aperçus, réduction des animations, plein écran, dialogue Google sans connexion et rappel hebdomadaire. Son écran de démarrage a également passé le contrôle séparé d’affichage et de fermeture. La version installée possède la même empreinte que la livraison testée. Tous les fichiers de données comparés sont identiques avant et après installation ; l’ancien programme 2.9.0 est conservé dans les archives locales voisines.

Les sections suivantes détaillent les fonctions conservées et leurs validations antérieures.

## Sauvegardes Google Drive

Les Réglages proposent une connexion Google dans le navigateur, un dossier dédié, sept catégories de sauvegarde, l’historique et une restauration après aperçu. Chaque enregistrement et fichier est identifié par son empreinte SHA-256 ; les objets déjà présents et confirmés par Drive sont réutilisés. Un manifeste est publié après validation de tous les objets. Une seconde sauvegarde identique ne crée pas de nouvelle version. Les anciennes versions ne sont pas supprimées automatiquement.

La restauration prépare une copie locale, vérifie les empreintes, les tailles, le schéma et les règles métier, puis remplace seulement les catégories incluses. Les autres catégories sont conservées. La validation refuse les conflits horaires et une préparation devenue périmée après une modification de la base ou d’un document conservé, même édité dans un logiciel externe. L’import conserve le mécanisme de copie complète préalable et de retour en arrière.

Le rappel hebdomadaire est activé par défaut et évalué au lancement puis chaque minute. Il peut être rapproché à un ou trois jours, reporté d’un jour ou désactivé. Aucun transfert n’est déclenché automatiquement. Seule une sauvegarde confirmée, y compris une vérification sans changement, remet son délai à zéro.

OAuth utilise le navigateur système, PKCE, un contrôle d’état et un retour sur l’adresse locale. L’autorisation demandée est `drive.file`. Les jetons restent dans `data/cloud`, protégés par Windows DPAPI, et sont exclus des sauvegardes et distributions. La déconnexion efface uniquement les jetons de ce PC. Le travail réseau est exécuté hors du thread de l’interface, avec annulation, tailles et délais bornés. Aucun nouveau paquet n’a été ajouté.

**Limite de validation :** aucun client OAuth réel n’a été fourni et aucune connexion au compte Google de l’utilisateur n’a été effectuée. Les tests de l’API utilisent un Drive simulé et des réponses réseau contrôlées. DPAPI et le retour OAuth local ont été testés sous Windows. L’activation de Google Cloud et un aller-retour avec un compte autorisé restent à effectuer ; `Documentation/Google-Drive.md` décrit cette étape. Sur un autre PC, il faut le même client OAuth et le même compte pour retrouver ces sauvegardes.

## Animation de démarrage

Un écran léger accompagne l’ouverture de l’application : boussole en relief, couleurs bleues et violettes, sphères et points animés. Il affiche les étapes réelles de préparation, sans pourcentage fictif ni durée minimale imposée. Son affichage indépendant reste fluide pendant le chargement des pages.

Les préférences de thème et de réduction des animations s’appliquent dès leur lecture. L’écran disparaît dès le premier affichage de l’application, avant la configuration initiale ou un message d’erreur. Il se ferme aussi à la fin du processus principal ; une défaillance de cet écran facultatif ne bloque pas le lancement. Il n’accède pas aux données personnelles et n’ajoute aucune dépendance.

Les rendus clair et sombre ont été inspectés. Le contrôle sur l’exécutable Windows compilé confirme l’affichage de la fenêtre, la transmission des préférences, la fermeture sur commande même avec le canal de communication ouvert, puis la fermeture lorsque ce canal est coupé. Aucun processus auxiliaire ne reste après ces contrôles.

## Style étendu à toutes les pages

L’accueil, Notes, Documents, Gestion du temps, Mémoire et Réglages reprennent les couleurs, les dégradés et les volumes de Progression. Chaque espace possède une illustration Qt dédiée : agenda et soleil, carnet et médaille, dossier et feuilles, horloge, cartes et étoile, commandes colorées. Les cartes de contenu et les statistiques reprennent cette palette, tout en conservant les couleurs personnalisées des matières.

Les titres ont un reflet au survol ; les figures réagissent légèrement à la souris. Ces mouvements sont brefs, sans animation permanente, s’arrêtent lorsque le composant est masqué et respectent la réduction des animations. Aucun téléchargement ni nouvelle dépendance n’est nécessaire. Les illustrations sont décoratives et ne représentent pas des résultats fictifs.

Les champs, filtres, boutons et opérations existants sont conservés. Les nouveaux compteurs de Gestion du temps reprennent les durées déjà calculées par le journal. Aucun schéma de données ni formule de score n’a changé.

## Présentation de Progression

La page présente quatre cartes colorées : études en bleu, sommeil en violet, sport en turquoise et détente en ambre. Les illustrations en relief (livres, lune, haltère et tasse) sont dessinées dans l’application, sans ressource externe. Elles réagissent au mouvement de la souris. Le score global apparaît dans une couronne animée et les objectifs dans des jauges colorées. Les détails des comparaisons sont regroupés dans un panneau repliable.

Le graphique annuel utilise la couleur du domaine sélectionné, avec un détail des mois au survol et au clavier (flèches, Début, Fin et Échap). Il distingue les valeurs nulles, les mois sans saisie et les mois futurs. Les animations sont limitées dans le temps et s’arrêtent lorsque les éléments sont masqués ou lorsque l’option de réduction des animations est activée. Les calculs et les données de progression sont conservés.

## Fonctionnement de Progression

La synthèse présente les scores Travail, Sommeil, Récupération et Global. Les vues Semaine, Mois et 3 mois présentent les activités réalisées et leur comparaison avec la période précédente. Les semaines vont du lundi au dimanche ; les trois mois regroupent le mois sélectionné et les deux précédents. Les périodes comparées ont la même durée écoulée, même lorsque les mois n’ont pas le même nombre de jours. Les totaux complets du bilan restent distincts des totaux utilisés pour la comparaison.

Le calcul exclut les activités prévues, supprimées ou non terminées. Les activités traversant minuit sont réparties aux bornes des périodes. Les matières personnalisées et archivées sont prises en compte. Consulter les bilans ne crée aucune activité et ne modifie pas le journal.

Les scores suivent des objectifs personnels, désactivés par défaut. Le temps réalisé est rapporté à l’objectif proratisé, avec un plafond de 100. Récupération est la moyenne des objectifs Sport et Détente actifs ; le score global est la moyenne des composantes actives. L’interface explique la formule et les limites d’un journal incomplet. Le score ne mesure ni les résultats scolaires ni la santé.

Aucun problème neutralise l’indication de baisse pour la période concernée, sans changer les durées ni les scores. Ce choix est réversible. Les objectifs et les indications acceptées sont sauvegardés dans les réglages existants, sans changement de schéma, et transférés par export/import. Les anciennes archives restent compatibles.

L’historique annuel présente les moyennes quotidiennes du temps saisi de septembre à août, avec choix Travail, Sommeil, Sport ou Détente et tableau des valeurs. Les mois futurs et les mois sans activités restent vides.

## Tests automatisés

320 tests de l’application ont réussi le 11 octobre 2026. Les 54 nouveaux tests Google Drive couvrent OAuth, le stockage local des jetons, le transfert et sa reprise, les limites, la déduplication par donnée et fichier, les catégories, la restauration entre deux installations, les corruptions et interruptions, la préservation des données locales, l’annulation dans l’interface et les échéances des rappels.

Les 13 tests du démarrage couvrent la communication, les préférences, les rendus, la réduction des mouvements, l’arrêt de l’animation, les erreurs, la fermeture du processus auxiliaire et le canal Windows lorsque l’exécutable n’a pas de console. Le mode de diagnostic continue à fonctionner sans lancer d’animation.

Les 17 tests introduits dans la version 2.6 couvrent les figures de Progression, la couronne, les couleurs, les valeurs et interactions du graphique, la réduction des animations et la disposition de la page. Les 33 tests de progression introduits dans la version 2.5 couvrent les calculs, les dates limites et années bissextiles, les nuits, les périodes partielles, les objectifs et leur validation, les indications réversibles, l’historique, l’absence d’écriture lors des consultations, les contrôles de l’interface et les transferts.

Les six tests des nouvelles illustrations couvrent leurs palettes, les différents formats de rendu, les deux thèmes et l’arrêt des mouvements. Les tests antérieurs couvrent notamment notes, documents, matières, emploi du temps, vacances, années, animations, plein écran, migrations et restauration après erreur.

Les outils de construction, mise à jour et partage ont passé 25 tests ; deux tests supplémentaires nécessitant le droit Windows de créer des liens symboliques sont ignorés sur cette machine. Le guide Google et l’éventuel client OAuth de bureau sont pris en charge dans la liste explicite des fichiers partageables. Un contrôle dédié vérifie que l’inclusion de cette configuration explicite n’exporte aucun jeton personnel.

## Interface et exécutable Windows

Le panneau Google Drive, sa configuration manquante, ses catégories et la restauration ont été rendus en clair et sombre dans une fenêtre de 740 × 600. Le rappel et la carte des Réglages ont été contrôlés à 1024 × 680. Aucun débordement horizontal ni appel Google n’est nécessaire à cette vérification visuelle.

Lors de la version 2.7, les sept pages ont été rendues à 1360 × 900 et 1024 × 680 dans les thèmes clair et sombre. Les bandeaux ont été vérifiés pour la visibilité des illustrations et la hauteur nécessaire aux textes. Les parties basses de Notes, Documents et Mémoire ont aussi été inspectées à petite résolution : les actions restent accessibles par défilement. Le contrôle ne relève ni erreur Qt ni débordement horizontal. La version 2.8 conserve ces pages et ajoute uniquement l’écran de démarrage.

Les bilans semaine/mois/trois mois, l’acceptation d’une baisse, le graphique annuel et le dialogue des objectifs ont fait l’objet de captures dédiées. Les figures au survol de chaque page, le détail d’un mois sélectionné au clavier et la présentation sans objectifs ont également été vérifiés.

Les cartes de Progression conservent leurs contrôles pendant les actualisations. Un test vérifie leur lisibilité après redimensionnement, changement de thème, changement de période et acceptation d’une baisse. Les animations réduites, les aperçus de navigation et le plein écran restent disponibles.

Les neuf tests des aperçus de navigation ont réussi après correction du premier rendu des pages masquées. Leur disposition est préparée lors des mises à jour de l’interface ; afficher un aperçu conserve la géométrie des pages, le défilement, le focus, les champs et la base de données.

L’exécutable 2.9.0 compilé a réussi le contrôle natif Windows avec une base temporaire : configuration initiale, sept pages et leurs illustrations, bilans, objectifs, thèmes, aperçus, animations réduites, plein écran et retour en fenêtre. Le dialogue Google Drive sans connexion, le rappel après sept jours et son report ont également été vérifiés dans cet exécutable. L’animation de démarrage a passé son contrôle Windows séparé.

## Distribution et rangement

Le projet conserve ses cinq dossiers : Application, Sources, Documentation, Outils et Partage. Compilation, captures et anciennes versions restent dans l’espace local voisin. Les distributions excluent les données personnelles, sauvegardes et caches ; leur manifeste SHA-256 permet de contrôler leur intégrité. Le transfert des données personnelles se fait avec un fichier .prepapilot exporté depuis Réglages.

La mise à jour vers 2.9.0 a conservé chaque fichier du dossier de données, avec comparaison SHA-256 avant et après installation. L’ancienne version 2.8.0 a été archivée dans l’espace local voisin du projet. L’empreinte de l’exécutable installé correspond à celle de la livraison validée.

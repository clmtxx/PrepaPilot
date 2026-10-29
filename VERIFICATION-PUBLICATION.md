# Vérifications de publication — 29 octobre 2026

Ce compte rendu complète les rapports historiques de [vérification de l’application](Sources/PrepaPilot/VERIFICATION.md) et de [distribution Windows](VERIFICATION-DISTRIBUTION.md). Il décrit les contrôles réalisés les 28 et 29 octobre 2026 sur les sources, les installateurs **2.26.0 et 2.26.1**, un parcours Google réel et les téléchargements publics. La [Release stable 2.26.1](https://github.com/clmtxx/PrepaPilot/releases/tag/v2.26.1) est publiée sur le dépôt public [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot).

## État actuel — Google et distribution configurés

### Correctif 2.26.1 — téléchargement GitHub

La [construction par tag de 2.26.0](https://github.com/clmtxx/PrepaPilot/actions/runs/40850546992) a réussi : **911 tests sur 911**, construction Windows, diagnostics et vérification réelle de l’installateur, puis ajout des trois fichiers à la Release. Le test public a ensuite détecté correctement la version mais refusé le téléchargement : GitHub utilise désormais le chemin CDN `/github-production-release-asset/`, alors que le validateur n’acceptait que son ancien préfixe.

La version corrective **2.26.1** ajoute ce préfixe sur les deux hôtes CDN GitHub déjà autorisés, uniquement après une redirection provenant du dépôt configuré. Les contrôles HTTPS, de domaine, de taille, d’empreinte et de format de l’installateur restent actifs. Les URL CDN initiales et les redirections de l’API vers un CDN restent interdites. Les vérifications de cette version corrective sont consignées séparément ci-dessous.

Le nouveau cas a reproduit le refus avant correction. Après correction, **40 tests ciblés** passent : 24 du moteur de mises à jour, quatre d’intégration et douze d’interface. Le moteur corrigé a ensuite téléchargé réellement la Release 2.26.0 : détection depuis 2.25.0, taille, SHA-256 et format du Setup, préparation sans lancement, puis taille, SHA-256 et CRC du ZIP, canal et présence du client applicatif commun. Les fichiers publics 2.26.0 n’ont pas été modifiés par cet essai. Les deux nouveaux tests portent le périmètre applicatif de 2.26.1 à **855 tests**, soit **913 contrôles** avec les scripts et les outils.

### Livraison finale 2.26.1 — validée

La [construction du tag v2.26.1](https://github.com/clmtxx/PrepaPilot/actions/runs/40898589889), au commit `82915513f469b66a5a457d935ec08005995c43bd`, a terminé avec succès le 29 octobre à **15:25 UTC** : **855 tests applicatifs, 23 tests des scripts et 35 tests des outils**, soit **913 réussites, aucun échec et aucun test ignoré**. La construction Windows, les diagnostics compilés français et anglais, l’installation, le lancement, la réinstallation et la désinstallation ont réussi. Les trois fichiers ont ensuite été joints à la Release, passée en version stable et dernière version du dépôt.

À **15:28 UTC**, un essai public avec le moteur corrigé a détecté **2.26.1 depuis 2.26.0**, téléchargé et validé l’installateur, puis vérifié sa préparation sans le lancer. Le ZIP public a aussi été téléchargé et a passé les contrôles de taille, SHA-256 et CRC ; le canal officiel et le client applicatif Google commun sont présents, aucun chemin de données personnelles ou de diagnostic n’a été détecté. Les empreintes téléchargées correspondent aux métadonnées GitHub et au fichier de sommes :

| Fichier public | Octets | SHA-256 |
| --- | ---: | --- |
| `PrepaPilot-2.26.1-Setup.exe` | 28 711 086 | `505e702bbd8e30e060f0e0d4b87173ab0c0565c4b0dc0067cb9b17e168c9d35a` |
| `PrepaPilot-2.26.1-Windows-portable.zip` | 39 165 979 | `a284f6263a5e28ef99768cdab9c8b322384f727a45ba535a5d2a01d91f07d090` |
| `SHA256SUMS.txt` | 201 | `dbc36d534e8405ed714820154631e2178c19edf23c26838ee369436060b04eb3` |

La construction locale 2.26.1 a également passé les diagnostics français et anglais, depuis le programme compilé et le ZIP extrait, puis une vraie mise à jour isolée **2.26.0 → 2.26.1** : lancement normal, langue anglaise et données fictives conservées, désinstallation et retrait de l’inscription Windows. La copie portable de travail a été remplacée par cette construction locale ; ses **trois fichiers de données ont des empreintes identiques avant et après**. Les fichiers locaux et ceux de GitHub sont issus de constructions distinctes, chacune avec ses propres sommes.

Le moteur contenu dans les anciens binaires **2.26.0** reste inchangé : leurs utilisateurs doivent télécharger manuellement l’installateur ou le ZIP 2.26.1 pour cette première mise à jour. Les essais publics ci-dessus n’ont lancé aucun fichier téléchargé, lu aucune donnée utilisateur ni utilisé d’identifiant Google. Le parcours Google réel du 28 octobre est distinct et n’a pas été répété pour ce seul correctif de téléchargement.

### Vérifications Google et constructions 2.26.0

Le client OAuth de bureau commun est créé, l’application Google est **en production** et le secret GitHub Actions **`GOOGLE_OAUTH_CLIENT_JSON`** est enregistré. Les distributions finales reçoivent ce client et `clmtxx/PrepaPilot` comme canal de mises à jour. Google reste facultatif et aucun compte n’est connecté d’office. La [notice de confidentialité](PRIVACY.md) décrit le stockage, les sauvegardes et les requêtes réseau.

Un parcours avec un vrai compte Google et uniquement des données applicatives fictives a réussi : connexion OAuth avec PKCE et protection locale DPAPI des jetons ; première sauvegarde de **14 objets** ; seconde sauvegarde avec **0 envoi et 14 objets réutilisés**, sans nouvelle version ; restauration des données et du document avec comparaison exacte vers un espace local distinct. Les jetons de l’essai ont été effacés. L’essai sur un autre ordinateur et avec un autre compte reste à effectuer.

Une première construction configurée a passé les diagnostics compilés français et anglais, les mêmes diagnostics depuis le ZIP extrait, la réinstallation 2.26.0 → 2.26.0 et la mise à jour 2.25.0 → 2.26.0 avec conservation des données fictives. L’installateur de cet essai porte l’empreinte SHA-256 `ac5526074dd47542096f21f4167efcf1b3e3ee38a134bc343995b9243675ee8e`. Ces parcours ont été répétés avec succès sur la construction locale finale du 29 octobre, après le correctif de chemins Windows, avec l’empreinte `f6ec40158dae4f75cad0da7e2d68bdc6f2db0fd3b1f34d8078360be0a4e50244`. Les empreintes à diffuser sont toujours celles du **`SHA256SUMS.txt` associé aux fichiers de la Release**, chaque construction ayant ses propres empreintes.

## Historique — campagne locale et correctifs initiaux 2.26.0

| Périmètre | Cas découverts | Réussis | Ignorés |
| --- | ---: | ---: | ---: |
| Application | 853 | 853 | 0 |
| Scripts de distribution | 23 | 23 | 0 |
| Outils de maintenance et de préparation | 35 | 33 | 2 |
| **Total** | **911** | **909** | **2** |

Les résultats sont consolidés par identifiant de test, avec comparaison aux cas effectivement découverts : aucun résultat ne manque et les répétitions après interruption ne sont pas additionnées. Les deux cas ignorés nécessitent le privilège Windows de création de liens symboliques.

Les essais utilisent **Python 3.12.14 x64**, **PySide6 6.11.2**, Qt hors écran et des données fictives séparées. Des chemins temporaires trop longs ont causé des erreurs initiales ; les cas concernés passent avec un chemin temporaire court. Le seul test de retour OAuth local a d’abord été bloqué par `WinError 10013`, puis a réussi séparément avec l’accès local autorisé : **1 test en 0,526 s**, sans navigateur ni appel à Google.

Une fixture de `Outils/test_mise_a_jour.py` a été corrigée, dans les sources historiques et la copie GitHub : elle fournit ses chemins fictifs `source` et `workspace` au vrai validateur de sortie. Les protections du validateur et la logique produit sont conservées.

### Correctif de construction CI — chemins Windows courts

Le nettoyage de `scripts/build_release.py` refusait les chemins Windows 8.3, comme `RUNNER~1`, lorsqu’ils désignaient le même répertoire qu’un chemin long. Le problème a été reproduit localement avec de vrais alias 8.3. Les deux chemins sont maintenant normalisés **après** le contrôle des liens symboliques et des jonctions dans tous leurs ancêtres. La suppression reste limitée à un enfant direct nommé `release-*` du répertoire temporaire de construction.

Deux tests de régression ont été ajoutés : variantes réelles de chemins courts pour la racine et la cible ; refus de jonctions réelles dans la cible, la racine ou un ancêtre, avec conservation d’un fichier témoin. Le contrôle existant des bornes de suppression vérifie aussi les dossiers étrangers et les sous-dossiers imbriqués. La suite des scripts passe ses **23 tests en 0,351 s** ; la création des jonctions fictives a nécessité l’accès local autorisé. Les résultats applicatifs et d’outils ci-dessus proviennent de la campagne précédente du même jour ; ces deux périmètres n’ont pas été relancés pour ce changement du constructeur.

### Finalisation du 29 octobre — chemins Windows et erreurs de test

Les deux premières exécutions GitHub ont été interrompues au bout de trente minutes : une erreur de chemin dans le test d’installation ouvrait une boîte de dialogue qui attendait une réponse. Les noms Windows abrégés et longs désignaient pourtant le même fichier. Le lancement des mises à jour accepte maintenant ces alias après vérification de tous les ancêtres contre les liens symboliques et les jonctions. Les contrôles du répertoire de téléchargement, du nom, de la version, de la taille et de l’empreinte sont conservés.

Deux nouveaux tests vérifient les alias Windows 8.3 réels et les jonctions réelles. Les tests d’intégration échouent immédiatement en cas de boîte d’erreur inattendue et interdisent tout démarrage d’installateur réel. Les fixtures de documents et de transferts utilisent également des chemins canoniques, comme les données de l’application. Les deux échecs de comparaison ont été reproduits avant correction.

Les **53 tests ciblés de mises à jour** et les **42 tests de documents et de transferts** passent avec de vrais chemins temporaires Windows abrégés. Les deux nouveaux cas portent le périmètre applicatif à **853 tests distincts**. Le tableau consolide la campagne du 28 octobre et les contrôles ciblés du 29 octobre sans compter les répétitions. Le résultat de la construction GitHub finale est contrôlé séparément avant la fin de la publication.

La campagne GitHub du correctif a ensuite confirmé **853/853 tests applicatifs** et **23/23 tests de distribution**. Les derniers problèmes concernaient uniquement les racines temporaires non canoniques de quatre fixtures des outils. Leurs sept échecs ont été reproduits avec un vrai chemin Windows 8.3, puis corrigés sans modifier les outils de production : la suite complète passe avec **33 réussites et deux contrôles de liens ignorés**, dans les sources historiques et la copie GitHub. La publication par tag exécute à nouveau les trois suites avant de construire ses fichiers Windows.

## Historique — premiers essais réels de l’installateur Windows

Deux parcours ont réussi avec `scripts/verify_installer.ps1`, dans un répertoire de programme temporaire et un espace de données utilisateur isolé :

- **Mise à jour 2.25.0 → 2.26.0**, sans désinstallation intermédiaire.
- **Installation puis réinstallation 2.26.0 → 2.26.0**.

Chaque parcours vérifie le lancement normal, la version du programme installé, le stockage des données dans l’espace utilisateur isolé, les autotests compilés français et anglais, puis la désinstallation. Les empreintes de la base fictive et d’un fichier témoin restent identiques après remplacement et désinstallation ; la préférence anglaise est conservée après remplacement. L’exécutable installé et son inscription Windows sont retirés à la désinstallation. Ces essais n’utilisent pas les données personnelles de l’application de travail.

L’installateur testé est **`PrepaPilot-2.26.0-Setup.exe`**, avec l’empreinte SHA-256 :

```text
c17b0ffccea0249e7596647fa5265f87abbd92120de94b33eec265d4fdfc21cc
```

Les anciens rapports indiquant que l’installation ou la désinstallation n’avaient pas été exécutées décrivent leur validation à leur date. Les deux parcours ci-dessus apportent cette validation supplémentaire pour ce fichier précis.

## Portée et preuves locales

Les preuves locales sont conservées dans `.local/Verification/Publication-2026-10-28` : `bilan-tests-final.json` décrit la campagne initiale de 907 contrôles ; `test-ci-short-path-before.log` reproduit le refus avant correctif et `tests-scripts-ci-short-path-final.log` consigne les 23 tests du constructeur corrigé. Les journaux d’application, d’outils et les deux journaux d’installation sont conservés au même endroit. Les résultats détaillés de l’installateur sont dans ses répertoires temporaires `.build/installer-tests`. Ces preuves locales ne sont pas nécessaires à l’utilisation de l’application.

Les échanges Google et GitHub des tests automatisés restent simulés ; le parcours Google réel séparé est décrit en début de document. Ces essais ne constituent pas une campagne sur plusieurs ordinateurs.

La construction locale finale du 29 octobre a passé les diagnostics compilés français et anglais, puis les mêmes diagnostics depuis le ZIP extrait. Le ZIP a passé ses contrôles de CRC, d’empreintes, de canal de mises à jour et d’absence de données personnelles. La copie portable de travail a été actualisée à partir de ce ZIP ; les empreintes de ses trois fichiers de données sont identiques avant et après. Ces preuves sont distinctes de celles de la construction GitHub et du téléchargement public.

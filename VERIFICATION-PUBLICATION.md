# Vérifications avant publication — 28 octobre 2026

Ce compte rendu complète les rapports historiques de [vérification de l’application](Sources/PrepaPilot/VERIFICATION.md) et de [distribution Windows](VERIFICATION-DISTRIBUTION.md). Il décrit les contrôles réalisés sur les sources et l’installateur local **2.26.0**. Il ne constitue pas une validation d’un compte Google réel ni d’une Release GitHub publique.

## Tests des sources

| Périmètre | Cas découverts | Réussis | Ignorés |
| --- | ---: | ---: | ---: |
| Application | 851 | 851 | 0 |
| Scripts de distribution | 23 | 23 | 0 |
| Outils de maintenance et de préparation | 35 | 33 | 2 |
| **Total** | **909** | **907** | **2** |

Les résultats sont consolidés par identifiant de test, avec comparaison aux cas effectivement découverts : aucun résultat ne manque et les répétitions après interruption ne sont pas additionnées. Les deux cas ignorés nécessitent le privilège Windows de création de liens symboliques.

Les essais utilisent **Python 3.12.14 x64**, **PySide6 6.11.2**, Qt hors écran et des données fictives séparées. Des chemins temporaires trop longs ont causé des erreurs initiales ; les cas concernés passent avec un chemin temporaire court. Le seul test de retour OAuth local a d’abord été bloqué par `WinError 10013`, puis a réussi séparément avec l’accès local autorisé : **1 test en 0,526 s**, sans navigateur ni appel à Google.

Une fixture de `Outils/test_mise_a_jour.py` a été corrigée, dans les sources historiques et la copie GitHub : elle fournit ses chemins fictifs `source` et `workspace` au vrai validateur de sortie. Les protections du validateur et la logique produit sont conservées.

### Correctif de construction CI — chemins Windows courts

Le nettoyage de `scripts/build_release.py` refusait les chemins Windows 8.3, comme `RUNNER~1`, lorsqu’ils désignaient le même répertoire qu’un chemin long. Le problème a été reproduit localement avec de vrais alias 8.3. Les deux chemins sont maintenant normalisés **après** le contrôle des liens symboliques et des jonctions dans tous leurs ancêtres. La suppression reste limitée à un enfant direct nommé `release-*` du répertoire temporaire de construction.

Deux tests de régression ont été ajoutés : variantes réelles de chemins courts pour la racine et la cible ; refus de jonctions réelles dans la cible, la racine ou un ancêtre, avec conservation d’un fichier témoin. Le contrôle existant des bornes de suppression vérifie aussi les dossiers étrangers et les sous-dossiers imbriqués. La suite des scripts passe ses **23 tests en 0,351 s** ; la création des jonctions fictives a nécessité l’accès local autorisé. Les résultats applicatifs et d’outils ci-dessus proviennent de la campagne précédente du même jour ; ces deux périmètres n’ont pas été relancés pour ce changement du constructeur.

## Essais réels de l’installateur Windows

Deux parcours ont réussi avec `scripts/verify_installer.ps1`, dans un répertoire de programme temporaire et un espace de données utilisateur isolé :

- **Mise à jour 2.25.0 → 2.26.0**, sans désinstallation intermédiaire.
- **Installation puis réinstallation 2.26.0 → 2.26.0**.

Chaque parcours vérifie le lancement normal, la version du programme installé, le stockage des données dans l’espace utilisateur isolé, les autotests compilés français et anglais, puis la désinstallation. Les empreintes de la base fictive et d’un fichier témoin restent identiques après remplacement et désinstallation ; la préférence anglaise est conservée après remplacement. L’exécutable installé et son inscription Windows sont retirés à la désinstallation. Ces essais n’utilisent pas les données personnelles de l’application de travail.

L’installateur testé est **`PrepaPilot-2.26.0-Setup.exe`**, avec l’empreinte SHA-256 :

```text
c17b0ffccea0249e7596647fa5265f87abbd92120de94b33eec265d4fdfc21cc
```

Les anciens rapports indiquant que l’installation ou la désinstallation n’avaient pas été exécutées décrivent leur validation à leur date. Les deux parcours ci-dessus apportent cette validation supplémentaire pour ce fichier précis.

## Portée et étapes suivantes

Les preuves locales sont conservées dans `.local/Verification/Publication-2026-10-28` : `bilan-tests-final.json` décrit la campagne initiale de 907 contrôles ; `test-ci-short-path-before.log` reproduit le refus avant correctif et `tests-scripts-ci-short-path-final.log` consigne les 23 tests du constructeur corrigé. Les journaux d’application, d’outils et les deux journaux d’installation sont conservés au même endroit. Les résultats détaillés de l’installateur sont dans ses répertoires temporaires `.build/installer-tests`. Ces preuves locales ne sont pas nécessaires à l’utilisation de l’application.

Les échanges Google et GitHub des tests automatisés sont simulés. Aucun aller-retour avec un véritable compte Google, aucun téléchargement depuis une Release publique et aucune campagne sur plusieurs ordinateurs ne sont validés par ce compte rendu.

Une **future construction intégrant le dépôt public et le client OAuth Google** devra être vérifiée à nouveau : diagnostics compilés français et anglais, ZIP extrait, installation/mise à jour/désinstallation et nouvelles empreintes. La configuration du client ne remplace pas les essais réels de connexion, sauvegarde et restauration Google. La première Release publique devra également permettre de vérifier le canal réel de mises à jour.

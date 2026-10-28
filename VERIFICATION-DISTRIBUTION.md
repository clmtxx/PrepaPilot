# Distribution Windows 2.26.0 — 27 octobre 2026

Le suivi souris est corrigé sur les sept pages, y compris au-dessus des textes et des contrôles. Les illustrations suivent leur carte ; les couleurs et dégradés de Progression sont conservés. Les 60 tests existants ciblés et les 8 nouveaux tests de suivi passent. Les 28 contrôles visuels produisent 11 artefacts sans erreur.

Les fichiers **PrepaPilot-2.26.0-Setup.exe**, **PrepaPilot-2.26.0-Windows-portable.zip** et **SHA256SUMS.txt** ont été générés par la même construction. L’exécutable et ses ressources de version indiquent 2.26.0. Les diagnostics compilés français et anglais ont réussi dans le constructeur et le ZIP extrait. La copie du projet a été mise à jour avec une archive de l’ancien programme et des empreintes de données inchangées. L’installation et la désinstallation de l’installateur sur le compte Windows actif n’ont pas été exécutées dans cette validation. Aucune publication en ligne n’a été effectuée ; la configuration Google réelle reste en attente.

## Historique — livraison 2.25

La livraison **2.25.0** simplifie le parcours Google Drive : configuration d’application commune intégrée par l’éditeur, connexion et autorisation du compte par chaque utilisateur, import de configuration personnelle conservé dans les options avancées. Les transitions directionnelles, les notifications et les réglages d’animation de la version 2.24 sont conservés.

Les fichiers **PrepaPilot-2.25.0-Setup.exe**, **PrepaPilot-2.25.0-Windows-portable.zip** et **SHA256SUMS.txt** ont été générés par la même construction. Les autotests compilés français et anglais ont réussi, notamment le rappel masqué sans client Google et disponible après préparation. Les résultats applicatifs sont aussi consignés dans [le compte rendu actuel](Sources/PrepaPilot/VERIFICATION.md). Les chiffres et empreintes des sections historiques ci-dessous ne constituent pas la validation de cette livraison.

## Contrôles des modifications 2.25

| Contrôle ciblé | Résultat |
| --- | --- |
| Sauvegardes Drive, dialogue et préférences | 38 tests réussis |
| Authentification Google | 16 tests réussis ; l’essai du retour de connexion local a nécessité une exécution autorisant ce serveur de test |
| Nouveaux contrôles de préparation Google | 4 tests réussis |
| Traduction progression et Google Drive | 6 tests réussis |
| Centre d’aide | 6 tests réussis |
| Validation de configuration du constructeur | 6 tests réussis |
| Préparation des distributions | 21 tests réussis |
| Outils du projet | Suite réussie ; deux contrôles de liens Windows ignorés |

Ces tests utilisent des configurations et des réponses simulées ; ils ne connectent pas de compte Google réel. Les onze tests de transferts Drive simulés passent également. Le ZIP extrait a passé les diagnostics français et anglais ; la copie du projet a été mise à jour en conservant les empreintes de tous les fichiers de données et une archive de l’ancien programme. L’exécutable et les ressources de version annoncent 2.25.0. Les empreintes de l’installateur et du ZIP sont fournies dans SHA256SUMS.txt. L’installation et la désinstallation de l’installateur sur le compte Windows actif n’ont pas été exécutées dans cette validation.

La construction accepte **`--google-oauth-client CHEMIN`** pour intégrer la configuration normalisée du client de bureau et **`--require-google-drive`** pour l’exiger. Le workflow fournit le JSON via **`GOOGLE_OAUTH_CLIENT_JSON`**, depuis une variable ou un secret GitHub, et impose un client valide pour une publication par tag. Une construction manuelle de développement peut rester sans Google. Aucun `credentials.bin`, jeton personnel ou dossier `data/cloud` ne doit être fourni à ce mécanisme.

**Limite actuelle :** les livrables locaux ne contiennent pas de client Google réel et ne permettent donc pas encore la connexion Google. Les essais réels de connexion, sauvegarde et restauration restent à réaliser après la préparation par l’éditeur. Aucune publication GitHub ni validation réelle d’un compte Google n’est confirmée par ce document. L’installateur reste sans certificat de signature d’éditeur.

## Historique — livraison 2.20 du 26 octobre 2026

La livraison **2.20.0** contient les améliorations de l’accueil, la recherche globale Ctrl+F, la palette Ctrl+K, la barre de séance disponible dans les autres espaces et l’aide F1. Les ressources de version de l’exécutable et de l’installateur indiquent 2.20.0.

Les fichiers actuels à distribuer sont **PrepaPilot-2.20.0-Setup.exe**, **PrepaPilot-2.20.0-Windows-portable.zip** et **SHA256SUMS.txt**. Ils sont reconstruits depuis les sources synchronisées. Le builder a réussi les autotests natifs français et anglais ; le ZIP extrait a réussi trois essais supplémentaires (32,22 s en français, 12,33 s en anglais, 13,80 s en haute résolution ×2). Le diagnostic compilé vérifie aussi les nouveaux parcours, sur données temporaires.

Le bilan applicatif comporte **765 scénarios validés après correction et relance ciblée**, **30 tests des outils**, **17 tests de distribution** et **104 captures sans erreur** ; deux contrôles de liens symboliques sont ignorés. Le détail des exécutions, de la fixture corrigée et du diagnostic asynchrone retiré est dans [le compte rendu actuel](Sources/PrepaPilot/VERIFICATION.md).

Les fichiers sont préparés pour une diffusion directe. Il n’y a encore ni dépôt public de mises à jour ni configuration Google OAuth. Aucune donnée personnelle n’est incluse. L’installateur est sans certificat de signature d’éditeur ; l’installation et la désinstallation sur le compte Windows actif n’ont pas été exécutées dans cette validation.

## Historique — livraison du 24 octobre 2026

**Sources synchronisées le 25 octobre 2026 après l’audit.** Le code corrigé, les 63 nouveaux tests et le [rapport d’audit](Documentation/Audit-2026-10-25.md) sont présents dans ce dossier. L’audit a validé 711 tests applicatifs, 30 tests des outils et 17 tests de distribution ; deux contrôles de liens symboliques ont été ignorés. Les fichiers Windows de `A-publier` restent ceux de la construction du 24 octobre et n’intègrent pas encore ces corrections. La synchronisation locale ne publie rien sur GitHub. Les vérifications et empreintes ci-dessous décrivent cette ancienne construction.

Version **2.19.0**, construite avec Python **3.12.14 x64**, PySide6 Essentials **6.11.2**, PyInstaller **6.22.3** et Inno Setup **6.7.3**.

## Mises à jour

La version installée propose une notification, une recherche manuelle dans **Réglages → Mises à jour**, puis **Télécharger et installer**. La recherche automatique peut être désactivée et se limite à une fois par jour. Le téléchargement vérifie les adresses GitHub, la taille, le SHA256 et le format de l’installateur ; son intégrité est encore contrôlée avant le lancement. L’application confirme la fermeture, conserve sa séance, ferme sa base et libère son verrou avant d’ouvrir l’installateur. Les données et paramètres sont conservés sans désinstallation. Le portable donne accès à la page de la nouvelle version et au transfert des données.

**Première publication :** le dépôt GitHub du propriétaire n’existe pas encore. Les fichiers locaux de **A-publier** restent donc sans canal en ligne. Pour activer les mises à jour chez les utilisateurs, utilise les fichiers que le workflow construira depuis le futur dépôt : il injecte automatiquement son adresse. Le guide **PUBLIER.md** décrit cette première publication. Une construction locale peut aussi recevoir le dépôt avec **--repository propriétaire/dépôt**. Aucun dépôt fictif ni jeton n’est incorporé.

## Vérifications

| Contrôle | Résultat |
| --- | --- |
| Suite complète | **648 tests réussis** en 427 secondes |
| Tests de distribution | **17 réussis** |
| Outils de maintenance et ressources de construction | **32 contrôles : 30 réussis et 2 ignorés** (privilège de liens Windows absent) |
| Nouveaux contrôles des mises à jour | 51 tests du moteur, des préférences, des traitements, de l’installation et de la fermeture |
| Contrôle visuel | **41 états** FR/EN, clair/sombre, 1024×680 et 1360×900 ; quatre captures inspectées |
| Programme compilé | Autotests français et anglais réussis, sans réseau |
| Installation réelle | Installation 2.17.0 puis remplacement par 2.19.0 dans le même dossier, sans désinstallation intermédiaire |
| Version remplacée | Version du fichier vérifiée, autotests français/anglais de la nouvelle version réussis avec marqueurs frais |
| Conservation | Préférence anglaise, empreintes de la base et du témoin fictifs inchangées après mise à jour et désinstallation |
| Téléchargement | Vérification du véritable Setup 2.19 avec trois GET GitHub simulés, SHA256 réel et commande de lancement contrôlée |
| Archive portable | CRC et SHA256 vérifiés, sans données ni marqueur d’installation, guides FR/EN présents |
| Copie de travail | Exécutable identique au ZIP ; quatre modules de mise à jour vérifiés dans l’archive Python du programme |
| Données personnelles | **3 fichiers inchangés**, ancien programme 2.18 archivé |

Les tests de réseau utilisent des services simulés. L’essai contre le futur dépôt public reste à effectuer après sa création et sa première Release. Les essais Windows utilisent uniquement des données fictives et ne créent pas de raccourcis.

## Fichiers dans A-publier

| Fichier | Taille exacte |
| --- | ---: |
| PrepaPilot-2.19.0-Setup.exe | 28743372 octets |
| PrepaPilot-2.19.0-Windows-portable.zip | 39486689 octets |
| SHA256SUMS.txt | 201 octets |

SHA256 de l’installateur testé :

```text
73d2a19a38a00ba9e07821f583e61bc2773b62a002d432a926c0cb884252f4c7
```

Conserve ensemble les trois fichiers d’une même construction. Les résultats locaux et les données restent exclus du dépôt. Aucun certificat de signature Windows n’est fourni. L’activation réelle Google Drive reste décrite dans **Documentation/Google-Drive.md** ; elle est indépendante de cette fonction de mise à jour.

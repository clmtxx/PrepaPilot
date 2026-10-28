# PrépaPilot

**Version 2.26.0**

**Livraison finale préparée le 28 octobre 2026 :** les sources sont disponibles sur [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot). La livraison est configurée pour ce dépôt et pour Google Drive ; la première Release publique reste à publier pour proposer les téléchargements. Aucun compte Google n’est connecté d’office.

PrépaPilot est une application Windows, disponible avec un installateur et en version portable, pour organiser tes études : notes, documents, repères personnels et temps consacré à tes activités. Elle s’adapte à tes matières et à ton parcours, au lycée, en licence, en BTS, en prépa ou dans une autre formation. Le nom PrépaPilot est conservé pour le moment.

## Ouvrir l’application

Depuis **Releases** sur le dépôt GitHub du projet, télécharge le fichier dont le nom se termine par **`-Setup.exe`**, ouvre-le et suis l’installation. Tu pourras ensuite lancer **PrépaPilot** depuis le menu Démarrer. Python n’est pas nécessaire. Le dossier **PrepaPilot-GitHub** contient le projet prêt pour cette distribution ; son fichier `PUBLIER.md` explique la première publication.

Si tu choisis l’archive portable, extrais-la entièrement puis ouvre `PrepaPilot/PrepaPilot.exe`. Garde le dossier `PrepaPilot` complet, avec son sous-dossier `_internal`.

Un écran animé accompagne le chargement et disparaît dès que la fenêtre est prête, sans attente ajoutée. Il reste fluide pendant la préparation des pages. Le thème et la réduction des animations sont appliqués dès la lecture de tes préférences. Au premier lancement, cet écran laisse la place à la configuration de ton espace.

Au premier lancement, choisis **Français** ou **English**, puis indique ton prénom ou ton pseudo et, si tu le souhaites, ton parcours. Configure ensuite tes matières et ton emploi du temps : **Partir de zéro** ouvre un espace vide ; **Utiliser un exemple** propose une base modifiable. Tu peux laisser le planning vide et le compléter plus tard. Une installation existante conserve sa configuration et propose le choix de langue si aucune langue n’a encore été enregistrée.

La traduction anglaise couvre toute l’interface. Pour changer de langue, ouvre **Réglages → Langue**, puis clique sur **Enregistrer mon profil** ; en anglais, **Settings → Language → Save preferences**. Le changement s’applique immédiatement, sans redémarrage, et reste mémorisé pour les ouvertures suivantes. Les matières, titres, objectifs et textes que tu as saisis ainsi que le contenu des documents restent inchangés.

Depuis la version 2.19, les versions reliées au dépôt public de PrépaPilot recherchent les mises à jour au démarrage, au plus une fois par jour. Une notification indique quand une nouvelle version est disponible. **Réglages → Mises à jour** permet aussi une recherche manuelle. Avec la version installée, **Télécharger et installer** récupère l’installateur, vérifie son empreinte, puis propose de fermer l’application et de lancer l’installation. Mets une séance en cours en pause et enregistre tes modifications avant de continuer. L’installateur conserve tes notes, documents et paramètres, sans désinstallation préalable. Tu peux également télécharger et ouvrir toi-même l’installateur depuis **Releases**.

Le portable ouvre la page **Releases** pour télécharger le nouveau ZIP. Extrais-le dans un nouveau dossier et utilise l’export puis l’import complet pour transférer ton espace ; conserve l’ancienne copie jusqu’à la vérification. La livraison finale utilise `clmtxx/PrepaPilot` comme dépôt de mises à jour. Les anciennes copies non configurées peuvent encore l’indiquer dans les Réglages ; elles doivent recevoir une distribution configurée.

La navigation horizontale donne accès aux espaces principaux. Le thème clair est proposé au départ ; un thème déjà choisi est conservé. Le thème sombre et les animations réduites se règlent dans **Réglages**.

Depuis la version **2.26**, les reflets lumineux suivent la souris sur toute la surface des cartes, dans tous les espaces, même lorsque le pointeur passe sur un texte, un champ ou un bouton. Les illustrations réagissent depuis leur carte. **Progression** conserve les couleurs et dégradés du travail, du sommeil, du sport et du repos ; chaque reflet reprend la couleur de sa carte. L’amplitude reste limitée et les zones de clic et de saisie restent stables. **Réglages → Réduire les animations** arrête ces mouvements ; les cartes masquées ou désactivées cessent aussi de réagir.

La version **2.24** ajoute une transition de panneaux lors des changements de page : l’écran sortant recule légèrement, puis le suivant glisse et se pose avec une ombre de tranche. Le sens suit l’ordre des onglets. Tu peux cliquer ou écrire immédiatement ; une nouvelle action interrompt l’effet et atteint directement la page choisie. Les brouillons, la position de défilement et la séance de travail restent conservés. Les infobulles des onglets indiquent aussi leur raccourci clavier.

Les notifications sont plus compactes et leur texte peut être sélectionné ou copié avec le bouton **Copier le message**. Les messages longs disposent d’une zone défilable ; leur durée d’affichage est adaptée à leur longueur et se met en pause quand tu les survoles ou les sélectionnes. Un champ actif est signalé par un cadre plus net et un fond légèrement teinté, pour retrouver facilement où tu écris.

La version **2.23** réintroduit davantage de couleur tout en gardant les fonds papier chaud et ardoise. Les en-têtes et les coins des cartes portent des teintes bleu, framboise, jade, ambre, violet et olive ; le centre de lecture reste sobre. L’onglet actif et les reflets des boutons reprennent la couleur de leur espace. Les illustrations reposent sur un médaillon de verre teinté, avec de fines graduations. Doubles liserés, incrustations et tranches complètent les finitions en relief introduites dans la version 2.22.

Les boutons présentent une lèvre claire et une tranche inférieure : une pression comprime visuellement le relief, puis un petit retour élastique accompagne le relâchement. Le pointeur oriente les reflets ; quelques scintillements passent sur le bord au survol et au clic. Les textes et les zones de clic restent stables. Les liens et les onglets inactifs gardent une présentation plus légère.

Laisse la souris environ une demi-seconde sur un onglet pour voir un aperçu de sa page, puis clique pour l’ouvrir. Les illustrations réagissent à la souris et les cartes présentent de brefs reflets de bord. Les effets se terminent après l’interaction, sans animation permanente au repos. **Réglages → Réduire les animations** les arrête immédiatement et conserve les matériaux, les illustrations et les aperçus sous forme fixe ; les pages s’ouvrent alors directement.

Le bouton **Plein écran** permet d’agrandir l’espace de travail. **F11** bascule entre la fenêtre et le plein écran ; **Échap** permet de quitter le plein écran.

Le défilement à la molette est progressif ; le pavé tactile, le clavier et les barres de défilement conservent leur fonctionnement habituel. Les illustrations, les fonds de cartes et les graphiques réutilisent leurs éléments fixes pour alléger les animations. Les pages concernées sont mises à jour après chaque modification, sans reconstruire les autres espaces. La recherche de documents attend une courte pause dans la frappe ; Entrée applique immédiatement le filtre.

## Tes espaces

### Un accueil qui aide à passer à l’action

La version **2.20** ajoute une **recherche globale · Ctrl+F** dans les titres et informations des documents, les évaluations de l’année sélectionnée et les repères personnels. Les résultats ouvrent directement le bon élément. Aucun fichier n’est envoyé sur Internet et le contenu des fichiers de documents n’est pas indexé.

Pendant une séance, une **barre de concentration** reste disponible dans les autres espaces : temps restant, pause, reprise et retour à la séance. Le bilan y reste accessible lorsqu’il est à vérifier. **Aide · F1** explique les premiers pas, les raccourcis et les sauvegardes ; **À propos** affiche la version et permet de copier un résumé technique sans données personnelles.

L’encart **Ton prochain pas** suit ta séance : commencer, retrouver le minuteur en cours, reprendre après une pause ou vérifier le bilan. Retrouver une séance en cours la laisse tourner. La carte **Ton élan de la semaine** présente les durées réellement enregistrées sur sept jours et ton objectif de travail si tu en as choisi un dans Progression. Les jours à venir restent distincts ; le repos a aussi sa place.

**Ton espace prend forme** propose trois premières découvertes : importer un document, ajouter une note et enregistrer une séance. Les étapes reflètent tes données sauvegardées et deviennent des raccourcis une fois réalisées. Le travail autonome est pris en compte et les notes des années précédentes restent reconnues.

Le bouton **Actions rapides · Ctrl+K** ouvre une recherche parmi les espaces et les actions : séance, activité, note, document ou repère. La recherche accepte plusieurs mots et ignore les accents. Utilise les flèches pour choisir, **Entrée** pour ouvrir et **Échap** pour fermer. Ces ajouts sont disponibles en français et en anglais, dans les deux thèmes, avec les animations réduites.

La sauvegarde Google Drive se trouve dans **Réglages → Gérer mes sauvegardes Google Drive**. Elle complète l’export portable décrit plus bas.

- **Aujourd’hui** : une vue d’ensemble, tes dernières notes et des séances de travail à valider dans ton journal.
- **Progression** : tes bilans de temps, tes objectifs personnels et tes succès avec médailles, niveaux et quêtes de régularité.
- **Notes** : tes matières, évaluations, barèmes, coefficients, statistiques et graphique annuel. Les valeurs d’origine et la conversion sur 20 sont conservées.
- **Documents** : tes fichiers originaux, rangés dans tes dossiers et classés par matière et type : cours, travaux dirigés, travaux pratiques, devoirs, projets, examens, stages, oraux ou autres. Import, recherche dans toute la bibliothèque, ouverture dans le logiciel associé, export et suppression. L’application conserve une copie gérée du fichier ; déplacer le fichier d’origine ne casse pas la bibliothèque.
- **Gestion du temps** : journal d’activités prévues ou réalisées, cours issus de ton emploi du temps, durées et répartition par catégorie. Les activités peuvent traverser minuit. Les chevauchements sont signalés pour éviter de compter deux fois le même temps.
- **Mémoire** : tes objectifs, difficultés et autres repères personnels, modifiables sur ton PC.
- **Réglages** : prénom, parcours facultatif, apparence, animations, export des notes en CSV, transfert complet de tes données et sauvegardes Google Drive.

## Ranger et retrouver tes documents

Dans **Documents**, crée un dossier avec le nom de ton choix, par exemple « Thermodynamique », « Examens du semestre » ou « Projet de groupe ». Les dossiers sont indépendants des matières et n’ont pas de sous-dossiers. Chaque document peut appartenir à un seul dossier ; ses informations de matière et de type restent disponibles.

Choisis un dossier lorsque tu importes un fichier ou modifies sa fiche. Pour ranger des fichiers déjà présents, sélectionne plusieurs lignes avec **Ctrl** ou **Maj**, puis utilise **Ranger** pour choisir leur destination. Ce classement ne recopie pas les fichiers. Tu peux renommer un dossier ou le supprimer : supprimer le dossier conserve ses documents dans **Sans dossier**.

**Tous les documents** affiche toute la bibliothèque et **Sans dossier** retrouve les fichiers qui ne sont pas encore rangés. Les documents importés avec une ancienne version apparaissent initialement dans **Sans dossier**. Tu peux toujours filtrer par dossier, matière et type.

La barre de recherche retrouve un document à partir de son **titre, du nom du fichier d’origine ou de ses mots-clés**. Avec **Rechercher partout**, coché par défaut, une recherche porte sur toute la bibliothèque, même si un dossier, une matière ou un type est sélectionné. Décoche cette option pour chercher seulement dans les filtres choisis. Une courte pause dans la frappe applique la recherche ; **Entrée** l’applique immédiatement.

Les dossiers et leur classement font partie de l’export complet `.prepapilot`. Ils sont aussi inclus dans les sauvegardes Google Drive lorsque les **documents** sont sélectionnés. Ils restent donc disponibles après un transfert vers un autre PC, avec les fichiers de la bibliothèque.

### Ranger ses cours avec une IA

Depuis la version **2.21**, **Documents → Ranger avec une IA** permet de confier un classement à un assistant ayant accès aux fichiers de ton ordinateur, puis de vérifier sa proposition dans PrépaPilot. L’application prépare les fichiers et applique le classement localement. Elle ne contient pas de moteur IA et n’envoie rien elle-même à un service d’IA. Le fonctionnement de l’assistant choisi détermine si le modèle travaille entièrement sur ton ordinateur ou utilise un service distant.

1. **Prépare un espace de rangement** depuis le dialogue. PrépaPilot crée un nouveau dossier dans `data/Rangement-IA`, avec des copies de tes cours rangées par dossier, matière et type. L’inventaire `catalogue.json` indique leurs titres, leurs dossiers et le chemin exact de chaque original ; `NOTICE-IA.md` explique le travail à l’assistant.
2. **Copie la consigne pour ton assistant**, puis demande-lui de lire la notice et de compléter `proposition.json`. Pour ajouter des cours qui sont ailleurs sur ton ordinateur, l’assistant en place des copies dans `A-importer` et les ajoute à la proposition.
3. **Lis la proposition dans PrépaPilot**, vérifie les changements affichés, puis applique le classement. Les cours importés deviennent des copies gérées de la bibliothèque ; les fichiers de départ restent à leur emplacement.

Le dialogue affiche les chemins des données, des originaux et de l’espace préparé. Tu peux reprendre une session existante pour lire le travail d’un assistant. Préparer un autre espace crée une nouvelle session sans écraser la précédente.

Les copies de `Bibliotheque` servent à consulter le contenu : les modifier ou les déplacer n’applique aucun classement. C’est `proposition.json` qui décrit les titres, matières, types et dossiers à enregistrer. Le classement conserve les fichiers gérés et ne permet pas de les supprimer. Les dossiers de l’application restent sur un seul niveau.

Si la bibliothèque change après la préparation, prépare un nouvel espace pour obtenir une proposition à jour. Si la proposition ou un fichier à importer change après l’aperçu, relis la proposition avant de l’appliquer. Une proposition déjà appliquée ne peut pas être rejouée.

Le classement appliqué et les cours importés sont inclus dans les sauvegardes habituelles. Les espaces de rangement et leurs copies de travail restent sur ce PC ; ils occupent de la place et peuvent être supprimés une fois le travail terminé. Pour transférer le résultat sur un autre PC, utilise l’export complet après avoir appliqué le classement.

## Séances de travail

Depuis **Aujourd’hui**, clique sur **Démarrer** dans la carte **Un instant de concentration**. Choisis une matière, **Travail autonome · sans matière** ou **Minuteur libre · sans enregistrement**, puis une durée de **1 à 240 minutes**. L’objectif est facultatif : « Revoir le chapitre 3 » ou « Terminer deux exercices », par exemple. Clique sur **Commencer**.

**Pause** suspend le décompte et **Reprendre** ouvre une nouvelle période de travail. Les pauses sont exclues du temps travaillé. **Terminer** permet d’arrêter avant la durée choisie et d’ouvrir le bilan. Lorsque le décompte arrive à zéro, **Voir le bilan** devient disponible sur l’accueil ; rien n’est ajouté automatiquement au journal.

Le bilan présente séparément les périodes entre les pauses. Tu peux changer la matière ou le nom de l’activité, corriger chaque début et fin, et retirer une période. Le journal utilise des horaires à la minute : les secondes de chaque période sont retirées en arrondissant le début à la minute suivante et la fin à la minute précédente. Une période sans minute entière n’est pas proposée à l’enregistrement. Vérifie et ajuste les horaires si nécessaire.

**Ajouter au journal** enregistre les périodes comme activités réalisées dans **Gestion du temps** et actualise **Progression**. Une matière ou **Travail autonome** doit être sélectionné, même si tu avais lancé un minuteur libre. Les chevauchements avec des activités déjà présentes sont signalés avant tout ajout. Une même séance ne peut pas être enregistrée deux fois.

**Plus tard** conserve le bilan et ses corrections pour le reprendre depuis l’accueil. **Ignorer la séance** le supprime après confirmation. Tu peux aussi **Abandonner** une séance en cours. Il faut enregistrer ou ignorer la séance précédente avant d’en commencer une autre.

Une fermeture ou une interruption, comme la mise en veille, laisse la séance en pause : le temps d’absence n’est pas ajouté. Le décompte est sauvegardé environ toutes les 15 secondes pendant le travail ; une fermeture inattendue peut donc perdre les dernières secondes depuis cette sauvegarde. À la prochaine ouverture, reprends la séance ou termine-la pour vérifier le bilan.

La séance en attente fait partie de l’export complet `.prepapilot` et des sauvegardes Google Drive lorsque **Travail, sport et autres activités** est coché. Après un import, une séance qui était en cours revient en pause. Les séances déjà validées sont conservées comme les autres activités du journal. Mets le minuteur en pause avant un transfert pour conserver son état le plus récent.

## Matières et évaluations

Dans **Notes → + Matière**, ajoute une matière avec son nom et sa couleur : biologie, droit, économie, langue, atelier… **Modifier la matière** permet de la renommer ou de changer sa couleur. Ces informations sont communes aux notes, aux documents et à l’emploi du temps.

Avec **Ajouter une note**, choisis la matière, saisis la note et son barème, puis la date. Le coefficient vaut 1 par défaut et peut être ajusté. Tu peux choisir un type proposé — contrôle, examen écrit, oral, projet, travaux pratiques ou autre — ou saisir ton propre type, comme « Soutenance » ou « Compte rendu de laboratoire ». Le nom de l’évaluation est facultatif et libre.

Toutes les matières acceptent ces types d’évaluation. Une note sur 10, 20 ou 100 garde son barème d’origine et est convertie sur 20 pour les statistiques. La moyenne tient compte des coefficients ; elle reste indicative. Tu peux modifier ou supprimer une note depuis l’historique, puis exporter l’ensemble en CSV depuis **Réglages**.

Dans le formulaire d’ajout ou de modification d’une note, l’onglet **Classe · facultatif** propose deux options indépendantes : **Je connais la moyenne de la classe** et **Je connais mon classement**. Saisis la moyenne sur le même barème que ta note ; pour le classement, indique ta position et l’effectif, par exemple **5 sur 32**. Laisse les options décochées si ces informations sont inconnues. Tu peux les compléter plus tard, ou les retirer en décochant l’option puis en enregistrant. Elles ne changent pas le calcul de ta moyenne personnelle.

Le graphique **Notes et moyenne de classe** ajoute une courbe violette en pointillés pour les moyennes renseignées, ramenées sur 20. Le bouton **Classement** affiche l’évolution de ta position, avec la première place en haut. Le survol précise **position / effectif** ; l’axe indique la position absolue, même si l’effectif varie entre les évaluations. Seules les valeurs connues sont tracées. L’historique affiche aussi ces informations lorsqu’elles existent.

Ces champs sont conservés dans le CSV, l’export complet et les sauvegardes Google Drive incluant les notes. Les anciennes données et sauvegardes restent lisibles : les champs inconnus sont laissés vides.

## Emploi du temps et suivi du temps

Dans **Gestion du temps → Mon emploi du temps**, configure deux modèles du lundi au dimanche. Le bouton **Renommer** permet de leur donner des noms adaptés à ton organisation : « Cours », « Stage », « Trimestre 1 »… Pour chaque créneau, choisis le jour, le début, la fin, la matière et la répétition : toutes les semaines, semaine A ou semaine B. L’aperçu hebdomadaire utilise les couleurs de tes matières. Les filtres permettent de voir une semaine ou une journée sans supprimer les autres créneaux.

Choisis un lundi dont tu connais la semaine A. L’alternance continue à partir de cette référence, y compris aux changements d’année et pendant les vacances. Les pauses suspendent les cours, sans décaler A/B. Dans **Gestion du temps → Changer de planning**, sélectionne le modèle à utiliser et sa date d’effet. Les journées passées et les corrections manuelles sont conservées.

Dans l’éditeur d’emploi du temps, **Retour aux matières** permet également d’ajouter ou renommer une matière, de choisir sa couleur ou de l’archiver. Archiver une matière retire ses futurs cours automatiques et la masque pour les nouvelles saisies, en conservant ses notes, ses documents et son historique. Tu peux la réactiver.

Les cours ajoutés au journal sont d’abord prévus ; ils ne deviennent pas automatiquement du travail réalisé. Vérifie les cours annulés ou déplacés avant d’utiliser **Valider les activités passées**.

Le journal conserve l’historique des journées : une modification du modèle ne réécrit pas les cours passés. Les activités modifiées ou annulées restent personnalisées lorsque les cours sont de nouveau générés. Ajuste les catégories, horaires et statuts à ta journée réelle.

## Année scolaire, vacances et pauses

Le sélecteur d’année commence à l’année scolaire actuelle, calculée à partir de septembre. Le bouton **+** ajoute l’année suivante. Les années et notes anciennes restent enregistrées même lorsqu’une année passée n’est plus proposée dans le sélecteur. Les choix d’années sont inclus dans l’export complet.

Dans **Gestion du temps → Vacances et pauses**, indique un nom et les dates de début et de fin, toutes deux incluses. Une période classique propose deux semaines, que tu peux ajuster. Pour les vacances d’été, choisis explicitement la date de fin. Aucun calendrier de zone scolaire ni aucune date officielle n’est appliqué automatiquement.

Pendant la période choisie, les cours automatiques sont suspendus. Tu peux continuer à ajouter tes propres activités. L’historique, les activités personnelles et les cours que tu as personnalisés sont conservés. **Reprendre ce jour** reprend l’emploi du temps à la date affichée ; les autres pauses déjà programmées restent en place. Les périodes sont sauvegardées et transférées avec tes données.

## Progression et objectifs personnels

### Succès, médailles et quêtes

Dans **Progression → Succès**, six collections proposent chacune cinq médailles : **Bronze, Argent, Or, Platine et Diamant**. Le relief, les facettes et les ornements s’enrichissent à chaque palier. Clique sur une collection pour consulter les cinq objectifs et les dates de déblocage. Les médailles de sport portent des symboles dédiés à l’activité et à la régularité.

| Collection | Bronze | Argent | Or | Platine | Diamant |
| --- | --- | --- | --- | --- | --- |
| Travail total | 50 h | 150 h | 400 h | 800 h | 1 500 h |
| Meilleure semaine de travail | 25 h | 40 h | 55 h | 65 h | 80 h |
| Meilleur mois de travail | 100 h | 160 h | 220 h | 260 h | 320 h |
| Série de nuits d’au moins 8 h | 3 nuits | 7 nuits | 14 nuits | 21 nuits | 30 nuits |
| Sport cumulé | 1 h | 5 h | 15 h | 30 h | 60 h |
| Semaines consécutives avec au moins 1 h de sport | 2 | 4 | 8 | 12 | 24 |

Les médailles rapportent respectivement 100, 200, 400, 700 et 1 000 XP. Chaque tranche de 500 XP fait gagner un niveau. Six quêtes reviennent à chaque période : travailler 25 h dans la semaine, travailler au moins 2 h sur cinq journées de la semaine, renseigner trois nuits d’au moins 8 h dans la semaine, travailler au moins 2 h sur vingt journées du mois, cumuler 1 h de sport dans la semaine, et faire au moins 20 min de sport sur deux journées de la semaine. Une quête ne rapporte ses points qu’une fois par période et par barème. Tes récompenses ne sont jamais retirées si tu corriges ensuite ton journal ; les compteurs, eux, reflètent les données actuelles.

Depuis la version 2.15, les anciens succès et quêtes de travail restent consultables dans **l’historique des anciens barèmes**, avec leurs dates et leurs XP. Ils ne débloquent pas artificiellement les nouveaux objectifs. Les nouveaux paliers sont évalués depuis tout le travail déjà renseigné dans ton journal : tu n’as pas besoin de repartir de zéro. Les médailles et quêtes de sommeil gardent leur barème et leurs dates. L’historique affiche les cent récompenses anciennes les plus récentes lorsque la collection est plus grande ; toutes restent sauvegardées.

La version 2.15.1 porte le Diamant hebdomadaire à **80 h** et le mensuel à **320 h**, avec des seuils intermédiaires rééquilibrés. Les médailles des anciens barèmes hebdomadaires et mensuels rejoignent cet historique avec leurs XP. Le mois reste un mois du calendrier ; ses objectifs correspondent à quatre fois les objectifs hebdomadaires.

Le sport regroupe les catégories **Sport** et **EPS**, sans les compter comme du travail. Tu peux répartir l’heure hebdomadaire sur plusieurs séances, par exemple deux fois trente minutes. La série retient le meilleur nombre de semaines consécutives atteignant une heure ; la semaine courante peut déjà compter une fois l’objectif atteint. Une semaine passée sans heure enregistrée interrompt la série calculée, sans retirer les récompenses déjà obtenues.

Seules les activités **réalisées, terminées et non supprimées** comptent, dans toutes tes matières, cours compris, ainsi que le travail autonome. Une séance de concentration compte après validation de son bilan dans le journal. Les semaines vont du lundi au dimanche ; les mois suivent le calendrier. Le temps traversant minuit est réparti entre les journées. Pour le sommeil, une nuit est regroupée entre midi la veille et midi le jour du réveil : dormir de 23 h à 7 h vaut donc 8 h pour ce réveil. Une journée non renseignée interrompt la série calculée, sans retirer les médailles déjà acquises. Ces paliers sont des défis facultatifs ; aucun objectif supplémentaire n’est nécessaire au-delà du dernier palier.

Les succès reconnaissent aussi les activités déjà présentes au premier lancement de cette version. Le journal des récompenses est conservé indépendamment des activités : **toute sauvegarde Google Drive l’inclut automatiquement**, même si tu ne coches pas le travail ou le sommeil. Une restauration Drive réunit les succès sauvegardés et ceux déjà acquis sur ce PC, sans doubler les XP. Pour retrouver aussi les compteurs et le détail des périodes sur un autre appareil, inclus les activités et le sommeil. La connexion seule ne restaure pas les données : il faut sauvegarder puis importer. L’export complet `.prepapilot` contient également les succès ; son import remplace tout l’espace par l’état archivé.

### Bilans et objectifs

Les quatre domaines ont chacun leur couleur et leur illustration en relief : études en bleu, sommeil en violet, sport en turquoise et détente en ambre. Les figures réagissent discrètement à la souris, le score global apparaît dans une couronne et les barres du graphique reprennent la couleur du domaine sélectionné. Le survol et les touches fléchées du graphique donnent accès au détail des mois. L’option **Réduire les animations** conserve les illustrations et désactive leurs mouvements.

Le panneau **Détails du bilan** rassemble les périodes exactes comparées et les explications des écarts. Les actions et les calculs restent les mêmes dans cette présentation.

L’onglet **Progression** s’ouvre sur une synthèse de la semaine en cours. Le sous-menu permet de consulter la semaine du lundi au dimanche, le mois calendaire ou trois mois calendaires : le mois sélectionné et les deux précédents. Change la date de référence pour retrouver un ancien bilan, puis reviens à la période actuelle.

Les quatre indicateurs sont **Travail**, **Sommeil**, **Sport** et **Détente**. Le travail regroupe les matières, y compris celles archivées, les évaluations, le temps collectif et le travail autonome. Les cours ne sont comptés qu’une fois marqués **Réalisé** dans Gestion du temps. Les activités prévues, supprimées ou non terminées sont exclues. Une activité traversant minuit est répartie selon le temps réellement situé dans chaque période.

La comparaison porte sur la même durée écoulée : le mardi à 19 h se compare au mardi précédent à 19 h. Pour les mois de longueurs différentes, seule la durée commune est utilisée pour l’écart ; les totaux de chaque bilan restent complets. Les dates exactes de comparaison sont affichées. Un journal incomplet ne permet pas de conclure à une baisse réelle d’activité.

Le bouton **Aucun problème** permet d’accepter une baisse pour cette période. Le message devient neutre ; les durées et les scores restent identiques. Ce choix est réversible et ne masque pas les baisses des périodes suivantes.

Avec **Mes objectifs**, choisis le temps que tu souhaites consacrer au travail, au sommeil, au sport et à la détente. Un objectif à zéro désactive l’axe correspondant. Aucun objectif n’est imposé au premier lancement. Les scores apparaissent après personnalisation et saisie d’activités réalisées.

Pour chaque axe actif, le score correspond au temps saisi divisé par l’objectif ramené à la durée écoulée, multiplié par 100 et plafonné à 100. Le score Récupération est la moyenne des axes Sport et Détente actifs. Le score global est la moyenne des composantes Travail, Sommeil et Récupération actives. Dépasser un objectif ne procure pas de points supplémentaires. Ce score mesure le suivi de tes objectifs de temps ; il ne mesure ni ton niveau scolaire ni ton état de santé.

Le graphique annuel suit la moyenne quotidienne du temps saisi, de septembre à août pour l’année sélectionnée. La moyenne divise le temps enregistré par les jours calendaires écoulés du mois. Les mois futurs ou sans activité restent vides. Le détail par matière permet de voir la répartition du travail.

Les objectifs et les choix **Aucun problème** sont inclus dans le transfert complet des données. Les statistiques sont recalculées depuis le journal après chaque correction ou import.

## Changer de PC sans perdre tes données

1. Sur le premier PC, ouvre **Réglages → Exporter toutes mes données**.
2. Enregistre le fichier `.prepapilot` et copie-le sur le second PC.
3. Sur le second PC, ouvre **Réglages → Importer mes données** et sélectionne ce fichier.
4. Lis le nombre de notes, documents, repères et activités détectés, puis confirme le remplacement.

L’export rassemble la base de données et les fichiers originaux de ta bibliothèque avec leurs dossiers et leur classement, ainsi que les matières et leurs couleurs, les types et noms d’évaluations, ton parcours, les deux plannings et leurs noms, les historiques et les préférences. Les documents utilisent des chemins relatifs : ils restent accessibles lorsque l’application change de dossier ou de PC.

L’import vérifie le format, l’intégrité des fichiers et la cohérence des données avant de proposer le remplacement. Il remplace l’ensemble des données présentes ; il ne fusionne pas deux bases. Annuler avant confirmation laisse ton espace intact.

Avant chaque import confirmé, une sauvegarde complète de l’état actuel est créée dans le sous-dossier `backups` de tes données : `%LOCALAPPDATA%/PrepaPilot/data/backups` avec la version installée, ou `data/backups` à côté de l’exécutable avec la version portable. Pour revenir en arrière, importe le fichier `avant-import-….prepapilot` correspondant. Si le remplacement échoue, l’application tente de remettre l’état précédent ; la sauvegarde automatique reste disponible.

Utilise la même version de PrépaPilot sur les deux PC. Le format accepte au plus 10 000 fichiers, 2 Go décompressés au total, 512 Mo par document et 128 Mo pour la base. Les archives incompatibles ou dépassant ces limites sont refusées avec une explication. Le fichier `.prepapilot` contient tes données personnelles ; conserve-le dans un emplacement de confiance.

## Partager l’application avec quelqu’un

Partage la page **Releases** du dépôt GitHub : le destinataire choisit l’installateur Windows, ou l’archive portable à extraire entièrement avant d’ouvrir `PrepaPilot/PrepaPilot.exe`. Ces distributions contiennent le programme et son guide, sans tes données personnelles.

Pour transmettre aussi le code, les outils et la documentation, utilise le dossier **PrepaPilot-GitHub**. Son fichier `README.md` explique chaque partie et `PUBLIER.md` décrit sa mise en ligne. Cette copie exclut les données personnelles, les anciennes versions, les caches et les fichiers de travail.

L’archive Windows distribue le logiciel. Le fichier `.prepapilot` transporte tes données entre tes propres installations. Le code source est fourni dans `Sources/PrepaPilot` et peut être partagé séparément avec ses licences.

## Sauvegardes Google Drive

Dans **Réglages → Gérer mes sauvegardes Google Drive**, connecte ton compte dans ton navigateur puis crée ou retrouve ton dossier PrépaPilot. Google Drive pour ordinateur n’est pas nécessaire.

L’accès Google commun est intégré à la livraison finale et l’application Google est en production. Clique sur **Se connecter à Google** et autorise l’application : tu n’as pas à créer de projet Google Cloud ni à fournir de fichier JSON. Google reste facultatif ; chacun utilise son propre compte et aucun compte n’est connecté d’office. Le 28 octobre 2026, une connexion réelle, une sauvegarde de 14 objets, une seconde sans nouvel envoi ni nouvelle version et une restauration exacte des données et documents ont réussi dans des espaces fictifs distincts. L’essai sur un autre PC et avec un autre compte reste à effectuer. Le guide `Documentation/Google-Drive.md` donne les étapes ; la [notice de confidentialité](https://github.com/clmtxx/PrepaPilot/blob/main/PRIVACY.md) décrit les données et les transferts.

Coche les catégories à envoyer : documents originaux avec leurs dossiers et leur classement, notes, sommeil, autres activités, emploi du temps et vacances, repères, profil et préférences. Les matières et années nécessaires sont incluses. **Sauvegarder maintenant** vérifie les éléments déjà présents : seuls les nouveaux éléments ou les modifications sont envoyés. Les anciennes versions restent disponibles ; une sauvegarde identique ne crée pas de doublon.

Un rappel apparaît après sept jours sans sauvegarde vérifiée, ou à la prochaine ouverture si l’application était fermée. Tu peux choisir un rappel quotidien ou tous les trois jours, le reporter à demain ou le désactiver. Aucun envoi ne se déclenche automatiquement.

Sur l’autre PC, installe une version préparée avec le même accès Google de PrépaPilot, puis connecte-toi au même compte. Choisis le dossier, puis **Afficher les sauvegardes → Vérifier et importer…**. Le récapitulatif précise les catégories remplacées ; les autres restent conservées. Une copie locale complète est créée avant l’import pour permettre un retour en arrière. Il s’agit d’une sauvegarde et d’une restauration, sans fusion automatique des modifications de plusieurs PC.

Le dossier Drive contient des éléments techniques réutilisés entre les versions : conserve ses fichiers ensemble. Les jetons de connexion restent dans `data/cloud`, protégés par la session Windows, et sont exclus des exports. **Déconnecter ce PC** laisse les sauvegardes et les autres PC intacts. Sur un nouvel ordinateur, reconnecte ton compte.

## Données et sauvegardes

La version installée conserve les données actives dans `%LOCALAPPDATA%/PrepaPilot/data`. Pour ouvrir ce dossier, colle ce chemin dans la barre d’adresse de l’Explorateur Windows. La version portable conserve son dossier `data` à côté de `PrepaPilot.exe` : les données déjà présentes dans `Application/PrepaPilot/data` restent à leur place et continuent d’être utilisées par cet ancien portable.

Les deux modes ont des espaces séparés. Une nouvelle installation ne copie pas automatiquement les données d’un portable : utilise l’export puis l’import `.prepapilot` pour les transférer. Dans chaque dossier de données, `mpsi.sqlite3` contient les enregistrements et les réglages ; `documents` contient les fichiers de ta bibliothèque. Ne copie pas uniquement la base si tu veux conserver les documents.

L’export complet reste la méthode recommandée pour sauvegarder et déplacer ton espace. Pour une copie manuelle, ferme l’application puis copie tout le dossier `data`.

Les versions précédentes sont conservées à côté du projet, dans le dossier portant son nom suivi de « - fichiers locaux », puis dans `Archives`. La reprise initiale des données préserve les originaux. Les anciennes fiches dont le document original n’avait pas été conservé deviennent des fichiers texte, avec une indication de leur provenance.

## Sources et construction

L’interface repose sur PySide6/Qt et les données sur SQLite. Les licences tierces sont fournies dans `licenses`. Les fonctions locales restent utilisables sans service distant ; Google Drive nécessite Internet uniquement pour la connexion et les transferts.

Pour développer, suis `Documentation/Developpement.md`. Crée un environnement Python séparé et installe `requirements-dev.txt`, puis utilise `Outils/lancer_sources.py` pour travailler avec des données de développement indépendantes. Depuis `Sources/PrepaPilot`, les tests se lancent avec `python -B -m unittest discover -s tests -v`.

`python Sources/PrepaPilot/build_windows.py` prépare la nouvelle version dans l’espace local voisin, sous `Livraison/PrepaPilot`, avec les fichiers temporaires dans `Construction`. Après les tests, `Outils/mettre_a_jour_application.py` installe la livraison validée et conserve l’ancien programme dans `Archives` de cet espace local. Le dossier `data` reste en place ; ferme PrépaPilot avant cette étape. `Outils/partager_application.py` prépare l’application seule et `Outils/preparer_projet.py` prépare le projet complet dans `Partage`, avec contrôle de leur intégrité.

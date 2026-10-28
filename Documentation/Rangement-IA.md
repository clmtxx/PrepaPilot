# Ranger ses cours avec une IA

**Disponible depuis PrépaPilot 2.21 · Documents → Ranger avec une IA**

PrépaPilot peut préparer tes cours pour un assistant ayant accès aux fichiers de ton ordinateur. L’assistant propose leur rangement ; tu vérifies les changements dans l’application avant de les enregistrer. Tu peux aussi lui demander de préparer l’ajout de cours qui sont encore dans Téléchargements ou dans un autre dossier.

PrépaPilot ne contient pas de moteur IA. La préparation, les vérifications et l’application du classement fonctionnent sur ton ordinateur, sans connexion à un service d’IA. Ton assistant peut employer un modèle installé sur ce PC ou un service distant : cela dépend de celui que tu choisis.

## 1 · Préparer les fichiers

Ouvre **Documents → Ranger avec une IA**, puis **Préparer un nouvel espace**. PrépaPilot crée une session dans `data/Rangement-IA`. Son chemin exact apparaît dans le dialogue, avec celui des données et celui des originaux. **Ouvrir l’espace** affiche ses fichiers dans l’Explorateur Windows.

Chaque session contient :

| Fichier ou dossier | Utilité |
| --- | --- |
| `NOTICE-IA.md` | Notice que l’assistant doit lire avant de travailler |
| `AGENTS.md` | Repère qui dirige les assistants vers la notice |
| `catalogue.json` | Inventaire des cours, de leurs chemins et de leurs dossiers, matières et types |
| `Bibliotheque` | Copies lisibles pour consulter le contenu des cours |
| `proposition.json` | Proposition de classement à compléter |
| `A-importer` | Copies des nouveaux fichiers que l’assistant souhaite ajouter à la bibliothèque |

Les copies sont regroupées par **dossier → matière → type**, avec le titre et un identifiant dans leur nom. L’inventaire permet de retrouver l’original correspondant, même si plusieurs cours portent le même titre. Les noms utilisés sur le disque peuvent être raccourcis ou adaptés à Windows ; les libellés complets restent dans l’inventaire.

Les originaux gérés restent dans `data/documents`, sous des noms techniques. Leur dossier dans l’application, leur titre, leur matière et leur type sont enregistrés dans la bibliothèque. Le catalogue rend cette correspondance explicite.

Dans la copie portable du projet, les données sont dans `Application/PrepaPilot/data`. Avec l’installateur Windows, elles sont dans `%LOCALAPPDATA%/PrepaPilot/data`. Utilise les chemins affichés par ton application pour être sûr de travailler sur le bon espace.

## 2 · Donner la consigne à ton IA

Clique sur **Copier la consigne pour mon IA**, puis colle-la dans ton assistant. Précise le classement souhaité et, si tu veux ajouter des cours extérieurs, les dossiers où les chercher.

Exemple de demande à adapter :

> Lis la notice de cet espace PrépaPilot et son catalogue. Propose un rangement par matière et par chapitre, avec des titres clairs. Vérifie le contenu des fichiers dont le nom est ambigu et conserve les informations que tu ne peux pas déterminer. Pour les nouveaux cours, cherche uniquement dans le dossier que je t’indique, copie les fichiers utiles dans A-importer et prépare leur ajout dans proposition.json. Présente-moi les choix incertains.

L’assistant utilise les copies de `Bibliotheque` pour consulter les cours. Il complète `proposition.json` pour proposer de nouveaux titres, matières, types ou dossiers. Pour un cours extérieur, il place une copie dans `A-importer` et décrit son ajout dans cette proposition. Un fichier placé dans `A-importer` sans entrée correspondante ne sera pas ajouté.

Modifier ou déplacer les copies de `Bibliotheque` ne change pas les cours dans PrépaPilot. L’assistant ne doit pas modifier directement la base ni les originaux gérés. La proposition ne prévoit pas de suppression de cours.

## 3 · Vérifier et appliquer

Reviens au dialogue et clique sur **Lire la proposition**. L’aperçu présente les changements et les cours à importer. Vérifie les titres, matières, types et dossiers, puis clique sur **Appliquer le classement**.

Les dossiers manquants sont créés lors de l’application. L’application conserve un seul niveau de dossiers : un nom comme « Maths · Intégrales » désigne un dossier, sans créer de sous-dossier.

Les nouveaux cours sont copiés dans la bibliothèque gérée. Les cours déjà présents gardent leurs fichiers, et les fichiers extérieurs restent à leur emplacement de départ. Le classement est enregistré comme un ensemble : si une entrée est invalide, aucun changement du lot n’est appliqué.

**Reprendre un espace…** permet de sélectionner une session préparée auparavant, par exemple après avoir fermé l’application. Préparer un nouvel espace crée une autre session et conserve le travail déjà présent.

Si tu modifies la bibliothèque pendant que l’assistant travaille, la proposition peut devenir périmée. Prépare alors un nouvel espace et demande à l’assistant de reprendre son classement à partir du nouveau catalogue. Si la proposition ou un fichier à importer change après l’aperçu, clique à nouveau sur **Lire la proposition**. Une proposition déjà appliquée ne peut pas être appliquée une seconde fois.

## Sauvegardes et place sur le disque

Le classement appliqué et les cours importés sont inclus dans l’export complet et dans les sauvegardes Google Drive contenant les documents. Pour transférer le résultat vers un autre PC, applique d’abord le classement, puis effectue une sauvegarde habituelle.

Les dossiers de session, leurs copies et les propositions en attente restent sur ce PC ; les fichiers de ces espaces ne font pas partie de l’export complet ni des sauvegardes Google Drive. Si tu souhaites conserver un travail en attente, garde son dossier de session. Une fois le classement terminé et vérifié, tu peux supprimer cette session depuis l’Explorateur pour récupérer la place occupée par les copies, en vérifiant bien que tu sélectionnes le dossier de session dans `Rangement-IA`.

## Format de proposition pour les assistants

La référence à suivre est toujours `NOTICE-IA.md` dans la session préparée par l’application. Le catalogue fournit les identifiants autorisés des matières et des types ; les noms de dossiers sont du texte. Conserve la version et l’identifiant de session générés.

Le modèle ci-dessous illustre un document existant à ranger et un nouveau cours à importer. Remplace les identifiants, les noms et le chemin par ceux de la session réelle :

```json
{
  "version": 1,
  "session_id": "identifiant-de-la-session-generee",
  "documents": [
    {
      "id": 42,
      "title": "Intégrales — cours",
      "subject": "maths",
      "kind": "cours",
      "description": "Méthodes et propriétés des intégrales.",
      "folder": "Mathématiques · Intégrales"
    }
  ],
  "imports": [
    {
      "source": "A-importer/TD-integrales.pdf",
      "title": "Intégrales — TD",
      "subject": "maths",
      "kind": "td",
      "description": "Exercices du chapitre.",
      "folder": "Mathématiques · Intégrales"
    }
  ]
}
```

- `documents` désigne des cours déjà présents par leur `id` stable. Un document omis garde son classement.
- `imports` décrit uniquement des nouveaux fichiers copiés dans `A-importer`. `source` est un chemin relatif à la session, sans sortie de ce dossier ni lien vers un autre emplacement.
- `folder` est le nom d’un dossier de l’application ; `null` signifie **Sans dossier**. Un même nom permet de ranger plusieurs cours ensemble.
- `subject` et `kind` sont les identifiants du catalogue, sans traduction ni invention. Une matière à créer ou à réactiver doit d’abord être configurée dans l’application, puis l’espace doit être préparé à nouveau.
- `title` est limité à 240 caractères, `description` à 10 000 et les noms de dossiers à 100. Les formats de fichiers autorisés sont indiqués dans la notice.

Le catalogue sert à comprendre les fichiers. Il ne permet pas de changer leur emplacement géré : aucun chemin d’original, aucune commande et aucune suppression ne doivent être ajoutés à la proposition. Les copies de consultation ne sont jamais réimportées implicitement.

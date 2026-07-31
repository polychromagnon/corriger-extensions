# SPEC — corriger-extensions

> **Règle d'or — rien ne s'affirme sans sa preuve.** Chaque preuve est un fait vérifiable et falsifiable.

---

## 1. Description globale — ce que fait le code

Corrige le **NOM** des fichiers dont l'extension est **dupliquée** et/ou en **majuscules**, cassée par de mauvais transferts : `photo.JPG.JPG → photo.jpg`, `clip.MP4.MP4.MP4 → clip.mp4`. Il ne fait QUE ça : pure lecture des noms + renommage. Il ne lit **jamais** le contenu, ne déplace rien, ne supprime rien, ne vérifie pas si l'extension « correspond » au format réel.

Pour qui : moi, pour assainir des archives photo/vidéo après transferts foireux, **sans le moindre risque pour les données ni les dates**. État actuel : v4.0.0, marqué « Définitif », licence MIT.

**Domaines sensibles** : **fichiers** (entrées de répertoire, inode, collisions de noms, casse de système de fichiers insensible à la casse comme APFS par défaut).

## 2. Fonctionnalités attendues + preuves

### Fusion d'extensions dupliquées identiques
- **Quoi** — `photo.jpg.jpg → photo.jpg`, `clip.mp4.mp4.mp4 → clip.mp4` (N occurrences identiques → 1).
- **Preuve** — entrée `x.jpg.jpg` → sortie `x.jpg`. Deux extensions **différentes** (`photo.jpg.png`) sont laissées **intactes** (on ne devine pas laquelle garder).

### Mise en minuscules des extensions connues uniquement
- **Quoi** — `PHOTO.JPG → photo.jpg`, mais une extension inconnue (`Notes.IMPORTANT`) n'est pas touchée.
- **Preuve** — `a.JPG` → `a.jpg` ; `Notes.IMPORTANT` inchangé. Le renommage de casse pure se fait en **deux temps** (via nom temporaire) avec **retour arrière automatique** si la 2ᵉ étape échoue (FS insensible à la casse).

### Intégrité totale des données et dates
- **Quoi** — renommer = modifier l'entrée de répertoire, pas le fichier.
- **Preuve** — après renommage : octets de données identiques (hash inchangé), mtime inchangé, birthtime inchangé, xattr (tags Finder) inchangés. Seul le `ctime` (« Attributs modifiés », non affiché par le Finder) change — attendu et sans rapport avec les dates EXIF.

### Pipeline SCAN → APERÇU → CONFIRMATION → APPLICATION
- **Quoi** — liste figée à l'étape SCAN ; aperçu + journal écrits AVANT toute écriture ; confirmation o/N (défaut NON) ; application n'agit QUE sur la liste figée.
- **Preuve (corrigée post-spar1)** — la liste appliquée est un **sous-ensemble** de la liste figée : **aucune action hors liste figée** (l'égalité stricte `==` est fausse car toute abstention à l'application — inode changé, source disparue, cible occupée — retire un élément). Confirmation vide/autre touche → aucune écriture (`--dry-run` n'applique rien).

### Re-vérification d'identité avant chaque renommage
- **Quoi** — juste avant de renommer, re-vérifier que la source est le même fichier (identité par **`(st_dev, st_ino)`**, plus fort que l'inode seul) et que la cible **n'existe pas**.
- **Preuve** — si la cible existe déjà → suffixe `_2`, `_3`… ; **jamais** d'écrasement d'un fichier existant. Si l'inode source a changé entre SCAN et APPLICATION → abstention sur ce fichier.

## 3. Interdictions & limites + preuves

- **Ne jamais ouvrir/lire le contenu** — preuve : aucune ouverture de fichier en lecture de données dans l'exécution (pur `os`/`pathlib` sur les noms).
- **Ne jamais écraser un fichier existant** — preuve : §2, conflit → suffixe incrémental.
- **Ne jamais renommer un dossier** — preuve : seuls des fichiers sont renommés ; un dossier `x.JPG/` est ignoré.
- **Refus des zones système** — preuve : refus de tourner sur `/`, `/System`, `/Library`, `/usr`… ; ne descend pas dans les paquets macOS (`.app`, `.photoslibrary`, `.pages`), ni `Library`, ni les corbeilles ; ignore les liens symboliques (fichiers et dossiers).
- **Fusion seulement si extensions identiques** — preuve : `photo.jpg.png` intact.
- **Journal écrit hors du disque scanné** (dossier courant) — preuve : aucun fichier ajouté sur le volume cible.

## 4. Risques d'interaction + preuves

- **Liste figée (SCAN) ↔ application** — un fichier renommé/supprimé/remplacé entre SCAN et APPLICATION ne doit pas être renommé sur la foi de l'ancienne liste : l'identité par inode bloque l'action (sinon on renomme le mauvais fichier).
- **Mise en minuscules ↔ FS insensible à la casse** — `PHOTO.JPG → photo.jpg` sur APFS (insensible mais préservant la casse) ne doit pas se voir refuser comme « cible déjà existante » : d'où le renommage en deux temps + rollback.
- **Suffixe anti-collision ↔ idempotence** — relancer l'outil sur un dossier déjà corrigé ne doit créer aucun `_2` parasite (rien à faire = rien fait).
- **[spar1] racine (point d'entrée) ↔ filtres de descente (paquets macOS / `Library`)** — `est_racine_interdite()` ne garde que les chemins **système absolus** (`/System`, `/usr`…) ; `EXT_DOSSIERS_OPAQUES` et `NOMS_DIR_IGNORES` ne s'appliquent qu'en **descente**, jamais à la **racine** passée en argument. Pointer la racine directement sur un paquet (`Photos.photoslibrary`, `.app`, `.pages`) ou sur `~/Library` est aujourd'hui **autorisé** : le scan entre dedans et renomme le contenu du paquet. Vérifié à la source : `est_racine_interdite('/Volumes/A/Photos.photoslibrary') == False`. **> à vérifier —** comportement attendu : refus net de la racine si son nom est dans `NOMS_DIR_IGNORES` ou si son suffixe est dans `EXT_DOSSIERS_OPAQUES`, comme pour les zones système. *Test :* lancer sur un `.photoslibrary`/`~/Library` → refus, aucune action.
- **[spar1] journal (`cwd`) ↔ volume scanné** — `choisir_journal()` écrit `rename_log_*.txt` dans `Path.cwd()` (repli : `home`), **sans aucun rapport avec le volume de `racine`**. Si `cwd` est sur (ou sous) le volume scanné — cas courant : `cd /Volumes/Archive` puis scan de `/Volumes/Archive` — un fichier **est** ajouté sur le volume cible : la preuve §3 « aucun fichier ajouté sur le volume cible » **tombe**, et la propriété §5 « nb fichiers avant == après » aussi (+1 journal). `--dry-run` écrit ce journal lui aussi (avant le court-circuit). **> à vérifier —** journal forcé hors-volume (`home`/`tempdir`) ou refus/avertissement si `cwd` est sur le même volume que `racine`. *Test :* `cwd` sur le volume scanné → `nb_fichiers(volume)` après == avant.
- **[spar1] garde anti-écrasement ↔ atomicité du renommage** — en chemin non-casse, `appliquer()` teste `cible.exists()` **puis** appelle `src.rename(cible)` ; `os.rename` POSIX **écrase silencieusement** une cible existante. Entre le test et le rename (TOCTOU), une cible apparue (autre process, Finder, second instance) serait écrasée : la garantie « jamais d'écrasement » n'est **pas atomique** (ni `RENAME_NOREPLACE`/`renamex_np` `RENAME_EXCL`). **> à vérifier —** tolérable en strict mono-utilisateur ? sinon renommage atomique sans remplacement. *Test :* créer la cible juste avant le rename → l'octet/inode préexistant n'est pas perdu.

## 5. Tests de robustesse

- Idempotence : 2ᵉ passage = 0 renommage.
- Entrées exotiques (classe) : noms Unicode, espaces, points multiples (`a.b.c.JPG.JPG`), fichiers sans extension, extensions très longues — aucun crash ; seuls les cas ciblés sont modifiés.
- Jamais de perte : sur un grand dossier, le nombre de fichiers avant == après (renommage, pas suppression) ; aucun octet de donnée modifié.
- Sécurité de chemin : un argument pointant vers une zone interdite → refus net, aucune action.
- Rollback : simuler l'échec de la 2ᵉ étape du renommage de casse → l'état initial est restauré.

## 6. Livrables attendus

- Script `corriger_extensions.py` exécutable, options `--dry-run`, `--tout` (afficher toute la liste), `--oui` (non interactif). (déjà présentes)
- README : ce que ça fait / ne fait PAS, la garantie d'intégrité, les filets de sécurité, l'emplacement du journal.
- Conserver la licence MIT et la mention de version/état.

## 7. Ce que je fournis _(facultatif)_

- Le code est marqué « Définitif v4.0.0 » : le SPEC sert surtout à **graver le contrat existant** et à le rendre testable, pas à étendre.
- Donnée réelle utile : un dossier-jouet reproduisant mes cas réels (`.JPG.JPG`, `.MP4.MP4.MP4`, `photo.jpg.png`, `Notes.IMPORTANT`, un nom avec inode partagé/lien dur).

### Décision build/buy (scout)

**Construire — verdict net.** La transformation nom→nom est banale (zmv en 1 ligne, Perl `rename`, NameChanger GUI), mais **100 % de la valeur est l'enveloppe de sûreté** (re-vérif inode · refus zones/paquets macOS · rollback de casse sur FS insensible · journal hors volume · fusion conditionnée · idempotence). **Aucun outil ne fournit ne serait-ce que 2 des 6 invariants** ; certains les **violent** (util-linux `rename` écrase ; Perl `rename`/`detox` trébuchent sur le pli de casse APFS). Recommandation scout : ajouter au README une section « Pourquoi pas `rename`/`zmv` ? » et **recentrer la Description sur « renommage à intégrité garantie »**. Confirme : figer v4.0.0 sans ajouter de feature est défendable.

---

## ⚠ À TRANCHER — je vide cette section avant de lancer

- La liste des extensions « connues » à mettre en minuscules : figée où, et faut-il pouvoir l'étendre ?
- Comportement souhaité sur `a.JPG.jpg` (même extension, casse différente) : fusionner en `a.jpg` ou laisser ?
- Le projet étant « Définitif », accepte-t-on que le SPEC fige sans rien ajouter (zéro feature) ?
- **[spar1] Preuve Pipeline « liste appliquée == liste figée » vs Re-vérification d'identité.** Les deux fonctionnalités se contredisent : dès qu'un fichier est ignoré à l'APPLICATION (inode changé, source disparue, cible occupée depuis le scan), la liste **appliquée** est un **sous-ensemble** de la figée, jamais égale. La propriété juste est « **appliquée ⊆ figée** » (aucune action **hors** de la liste figée), pas l'égalité. Garde-t-on l'égalité stricte (alors elle est falsifiable-et-fausse au premier abstention) ou bascule-t-on en inclusion ?
- **[spar1] Que recouvre exactement « fusion SEULEMENT si extensions identiques » ?** Vérifié à la source, le code fuse : (a) les **synonymes** `photo.jpeg.jpg → photo.jpg` (jpeg ≠ jpg comme chaîne, rendus égaux par `NORMALISER_JPEG`) ; (b) la **même extension en casse différente** `a.JPG.jpg → a.jpg` (déjà ouvert plus haut). Mais il **ne fuse pas** quand le basename contient un point non-extension : `IMG.2024.JPG.JPG → IMG.2024.JPG.jpg` (le doublon `.JPG.JPG` **survit**, car `tous_connus` exige que **toutes** les parties pointées soient des extensions connues). La preuve §2 ne couvre que `x.jpg.jpg`. Définir « duplication fusionnable » = *run final d'extensions identiques après normalisation des synonymes* ? Puis graver une preuve qui couvre (a), (b) et le cas `IMG.2024.JPG.JPG`.

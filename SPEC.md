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
- **Preuve (définition gravée, [sail])** — « duplication fusionnable » = *toutes* les parties pointées après le premier point sont des extensions connues **et** se réduisent à une seule forme après normalisation de casse et des synonymes. Couvre donc : `photo.jpeg.jpg → photo.jpg` (synonyme), `a.JPG.jpg → a.jpg` (casse). Ne couvre **pas** `IMG.2024.JPG.JPG` (la partie `2024` n'est pas une extension connue) : seule la casse finale est corrigée, `IMG.2024.JPG.jpg`, et le doublon survit — limite assumée, gravée telle quelle.

### Mise en minuscules des extensions connues uniquement
- **Quoi** — `PHOTO.JPG → photo.jpg`, mais une extension inconnue (`Notes.IMPORTANT`) n'est pas touchée.
- **Preuve** — `a.JPG` → `a.jpg` ; `Notes.IMPORTANT` inchangé. Le renommage de casse pure se fait en **deux temps** (via nom temporaire) avec **retour arrière automatique** si la 2ᵉ étape échoue (FS insensible à la casse).

### Intégrité totale des données et dates
- **Quoi** — renommer = modifier l'entrée de répertoire, pas le fichier.
- **Preuve** — après renommage : octets de données identiques (hash inchangé), mtime inchangé, birthtime inchangé, xattr (tags Finder) inchangés. Seul le `ctime` (« Attributs modifiés », non affiché par le Finder) change — attendu et sans rapport avec les dates EXIF.
- **Preuve exécutable ([sail], plateforme de test Linux)** — hash SHA-256 des octets inchangé, `st_mtime_ns` inchangé, xattr du namespace `user.*` inchangés, `st_ino` inchangé. **Non vérifiable ici** : `st_birthtime` (absent de `os.stat_result` sous Linux/CPython 3.11) et les tags Finder — marqués « non vérifié sur cette plateforme, vérification manuelle macOS requise », jamais simulés.

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
- **Refus de la racine elle-même si elle est une zone protégée ([sail])** — preuve : la racine passée en argument subit les mêmes filtres que la descente ; suffixe dans les paquets macOS (`Photos.photoslibrary`, `X.app`, `Y.pages`) ou nom dans `Library`/`.Trash`/`.Trashes` → refus net, code de sortie non nul, aucune action.
- **Fusion seulement si extensions identiques** — preuve : `photo.jpg.png` intact.
- **Journal écrit hors du volume scanné ([sail], preuve renforcée)** — preuve : l'emplacement du journal est choisi par comparaison de `st_dev` avec la racine ; si aucun emplacement candidat n'est sur un autre volume, aucun journal n'est écrit et l'absence est annoncée à l'écran. Test : `cwd` sur le volume scanné → le nombre de fichiers du volume après == avant, y compris en `--dry-run`.
- **Jamais d'écrasement, garanti par l'appel système ([sail])** — preuve : le renommage utilise un appel qui échoue si la cible existe (`renameat2`/`RENAME_NOREPLACE` sous Linux, `renamex_np`/`RENAME_EXCL` sous macOS) ; le test `exists()` seul n'est pas une preuve (TOCTOU). Repli documenté si l'appel est indisponible. Test : cible créée entre le scan et le renommage → le fichier préexistant est intact et le cas est reporté comme ignoré.
- **Aucun nom temporaire ne survit à un run ([sail])** — preuve : après toute sortie du programme, normale ou interrompue, aucune entrée `__rename_tmp_*` ne subsiste sur la racine scannée ; le compteur « renommé(s) » annoncé est égal au nombre de noms réellement changés sur le disque.

## 4. Risques d'interaction + preuves

- **Liste figée (SCAN) ↔ application** — un fichier renommé/supprimé/remplacé entre SCAN et APPLICATION ne doit pas être renommé sur la foi de l'ancienne liste : l'identité par inode bloque l'action (sinon on renomme le mauvais fichier).
- **Mise en minuscules ↔ FS insensible à la casse** — `PHOTO.JPG → photo.jpg` sur APFS (insensible mais préservant la casse) ne doit pas se voir refuser comme « cible déjà existante » : d'où le renommage en deux temps + rollback.
- **Suffixe anti-collision ↔ idempotence** — relancer l'outil sur un dossier déjà corrigé ne doit créer aucun `_2` parasite (rien à faire = rien fait).
- **[spar1] racine (point d'entrée) ↔ filtres de descente (paquets macOS / `Library`)** — `est_racine_interdite()` ne garde que les chemins **système absolus** (`/System`, `/usr`…) ; `EXT_DOSSIERS_OPAQUES` et `NOMS_DIR_IGNORES` ne s'appliquent qu'en **descente**, jamais à la **racine** passée en argument. Pointer la racine directement sur un paquet (`Photos.photoslibrary`, `.app`, `.pages`) ou sur `~/Library` est aujourd'hui **autorisé** : le scan entre dedans et renomme le contenu du paquet. Vérifié à la source : `est_racine_interdite('/Volumes/A/Photos.photoslibrary') == False`. **> à vérifier —** comportement attendu : refus net de la racine si son nom est dans `NOMS_DIR_IGNORES` ou si son suffixe est dans `EXT_DOSSIERS_OPAQUES`, comme pour les zones système. *Test :* lancer sur un `.photoslibrary`/`~/Library` → refus, aucune action.
- **[spar1] journal (`cwd`) ↔ volume scanné** — `choisir_journal()` écrit `rename_log_*.txt` dans `Path.cwd()` (repli : `home`), **sans aucun rapport avec le volume de `racine`**. Si `cwd` est sur (ou sous) le volume scanné — cas courant : `cd /Volumes/Archive` puis scan de `/Volumes/Archive` — un fichier **est** ajouté sur le volume cible : la preuve §3 « aucun fichier ajouté sur le volume cible » **tombe**, et la propriété §5 « nb fichiers avant == après » aussi (+1 journal). `--dry-run` écrit ce journal lui aussi (avant le court-circuit). **> à vérifier —** journal forcé hors-volume (`home`/`tempdir`) ou refus/avertissement si `cwd` est sur le même volume que `racine`. *Test :* `cwd` sur le volume scanné → `nb_fichiers(volume)` après == avant.
- **[spar1] garde anti-écrasement ↔ atomicité du renommage** — en chemin non-casse, `appliquer()` teste `cible.exists()` **puis** appelle `src.rename(cible)` ; `os.rename` POSIX **écrase silencieusement** une cible existante. Entre le test et le rename (TOCTOU), une cible apparue (autre process, Finder, second instance) serait écrasée : la garantie « jamais d'écrasement » n'est **pas atomique** (ni `RENAME_NOREPLACE`/`renamex_np` `RENAME_EXCL`). **> à vérifier —** tolérable en strict mono-utilisateur ? sinon renommage atomique sans remplacement. *Test :* créer la cible juste avant le rename → l'octet/inode préexistant n'est pas perdu.
- **[spar1] renommage de casse en 2 temps ↔ liens durs (identité par inode)** — `case_safe` est décidé au SCAN par `nom.lower() == nouveau.lower() and meme_fichier(src, cible)`. Or `meme_fichier` (= `samefile`, donc même inode) est vrai dans **deux** situations distinctes : (a) le pli de casse d'un FS insensible (cas visé), (b) **deux liens durs** dont les noms ne diffèrent que par la casse, sur un FS **sensible** (ext4, APFS sensible) — cas explicitement présent dans le jeu de données de §7 (« un nom avec inode partagé/lien dur »). En (b), la 2ᵉ étape `temp.rename(cible)` porte sur deux entrées du **même inode** : POSIX impose alors « succès, aucune autre action » → **aucune exception, donc aucun rollback** ; le fichier reste nommé `__rename_tmp_…`, et `renommes += 1` **annonce un succès qui n'a pas eu lieu**. Comme `scanner()` ignore les noms commençant par `__rename_tmp_`, l'orphelin est **invisible à toute relance** : ni corrigé, ni compté, ni signalé. Reproduit à la source (ext4) : `A.jpg` + `ln A.jpg A.JPG` → après run, `A.jpg` + `__rename_tmp_A.jpg`, écran « 1 fichier(s) renommé(s) », relance « À corriger : 0 ». Même racine dans la branche non-casse : `if cible.exists() and not meme_fichier(src, cible)` laisse passer un `rename` entre liens durs, no-op POSIX compté comme renommage. **> à vérifier —** comportement attendu : abstention nette quand source et cible sont deux liens durs du même inode, et aucun `__rename_tmp_*` ne survit à un run. *Test :* dossier avec `A.jpg` et son lien dur `A.JPG` → après run, aucun `__rename_tmp_*` ne subsiste et le compteur annoncé == nombre de noms réellement changés.
- **[spar1] fenêtre du renommage en 2 temps ↔ filtre de scan `__rename_tmp_`** — le rollback de `appliquer()` n'est armé que par `except OSError`. Une interruption (Ctrl-C / SIGINT, `KeyboardInterrupt`, arrêt du process) entre `src.rename(temp)` et `temp.rename(cible)` n'est **pas** un `OSError` : aucun retour arrière, le fichier reste `__rename_tmp_…` et devient invisible aux relances (filtre du scan). La preuve §5 « simuler l'échec de la 2ᵉ étape » ne couvre que l'échec `OSError` et passerait au vert malgré ce trou. **> à vérifier —** comportement attendu : le nom temporaire ne survit à aucune sortie du process, ou il est repris/signalé au run suivant. *Test :* faire lever `KeyboardInterrupt` par la 2ᵉ étape → l'état initial est restauré (ou l'orphelin est listé au run suivant), pas d'entrée `__rename_tmp_*` muette.
- **[spar1] journal indisponible ↔ aperçu tronqué (`SEUIL_APERCU`) ↔ confirmation** — `choisir_journal()` renvoie `None` **en silence** si ni `cwd` ni `home` ne sont inscriptibles (le message `⚠️ Journal non écrit` ne couvre que l'échec d'écriture *ultérieur*, pas ce cas). Au-delà de 200 renommages, `afficher_apercu()` n'affiche que 40 lignes et imprime **inconditionnellement** « Liste intégrale dans le journal ci-dessus (ouvre-le pour tout vérifier) », alors qu'aucun journal n'existe. L'utilisateur voit donc 40 lignes sur 250, sans avertissement, avec un renvoi vers un fichier inexistant, juste avant le prompt o/N d'une action irréversible : le filet « ce que tu vois est exactement ce qui sera fait » (§2, pipeline) **tombe**. Reproduit : `cwd` et `HOME` en lecture seule + 250 fichiers `*.JPG` → sortie sans ligne « Liste complète (journal) » mais avec « Liste intégrale dans le journal ci-dessus ». **> à vérifier —** comportement attendu : journal absent **et** liste tronquée → pas de confirmation proposée (ou `--tout` imposé), et jamais de renvoi à un journal inexistant. *Test :* journal impossible + 250 modifs → la sortie ne mentionne aucun journal et aucune application n'est proposée.

## 5. Tests de robustesse

- Idempotence : 2ᵉ passage = 0 renommage.
- Entrées exotiques (classe) : noms Unicode, espaces, points multiples (`a.b.c.JPG.JPG`), fichiers sans extension, extensions très longues — aucun crash ; seuls les cas ciblés sont modifiés.
- Jamais de perte : sur un grand dossier, le nombre de fichiers avant == après (renommage, pas suppression) ; aucun octet de donnée modifié.
- Sécurité de chemin : un argument pointant vers une zone interdite → refus net, aucune action.
- Rollback : simuler l'échec de la 2ᵉ étape du renommage de casse → l'état initial est restauré.
- Rollback élargi ([sail]) : la 2ᵉ étape lève une `BaseException` (interruption clavier) → l'état initial est restauré et l'exception continue de remonter ; aucun `__rename_tmp_*` ne subsiste.
- Liens durs ([sail]) : un fichier et son lien dur dont les noms ne diffèrent que par la casse → abstention nette sur ce couple, aucun `__rename_tmp_*`, compteur annoncé == renommages réels.
- Journal indisponible ([sail]) : aucun emplacement inscriptible hors volume → l'écran annonce l'absence de journal, ne renvoie jamais vers un journal inexistant, et aucune application n'est proposée si la liste affichée est tronquée.

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

## Décisions de gel — prises par `sail` en l'absence du PO, à revoir

> Section **jetable** : elle remplace « À TRANCHER », vidé pour permettre le gel en full-auto.
> Aucune politique (`policy.md`) n'a été trouvée → **défauts conservateurs** appliqués :
> features **SANS** (MVP strict), rival **OFF**, parallèle **OFF**, doute de périmètre → option minimale et réversible.
> Chaque ligne = *choix · alternative écartée · raison*. Toutes réversibles par `git revert`.

1. **Liste `KNOWN_EXTS`** — figée en dur dans le script, non configurable. *Écarté* : la rendre extensible (fichier de conf, option). *Raison* : feature, déjà refoulée au `backlog.md` ; la politique impose le MVP strict.
2. **`a.JPG.jpg`** — fusionné en `a.jpg`. *Écarté* : laisser intact. *Raison* : c'est le comportement du code v4.0.0 ; le cycle grave l'existant, il ne le change pas.
3. **Zéro feature** — le SPEC fige sans rien ajouter. *Écarté* : promouvoir un item du backlog. *Raison* : politique features SANS + intention déclarée en §7.
4. **Liste appliquée vs liste figée** — la propriété gravée est l'**inclusion** (« appliquée ⊆ figée », aucune action hors liste figée). *Écarté* : l'égalité stricte. *Raison* : l'égalité est fausse dès la première abstention légitime ; garder une preuve fausse serait un faux vert.
5. **Définition de « duplication fusionnable »** — gravée telle que le code la met en œuvre, y compris sa limite (`IMG.2024.JPG.JPG` non fusionné). *Écarté* : élargir la fusion aux run finaux d'extensions. *Raison* : élargir change le comportement sur des fichiers réels, c'est-à-dire une feature, hors périmètre du gel. La limite est écrite noir sur blanc en §2 plutôt que masquée.
6. **Preuves d'intégrité non mesurables sous Linux** — les tests prouvent hash, `st_mtime_ns`, xattr `user.*`, `st_ino` ; `st_birthtime` et les tags Finder sont déclarés « non vérifié sur cette plateforme ». *Écarté* : exiger une exécution macOS avant de graver, ou simuler ces attributs. *Raison* : simuler serait maquiller le vert ; bloquer sur une machine indisponible arrêterait tout le cycle. La lacune est déclarée, pas comblée.
7. **Les six coutures de §4 sont traitées comme des défauts, pas comme des features** — le code est corrigé pour tenir les garanties que le SPEC et son propre docstring affichent déjà (jamais d'écrasement, journal hors volume, rollback, « ce que tu vois est ce qui sera fait »). *Écarté* : affaiblir les garanties du contrat pour les faire correspondre au code. *Raison* : affaiblir une preuve pour passer au vert est explicitement interdit.
8. **Version** — passage à **4.1.0**, état « Définitif — correctifs de sûreté ». *Écarté* : rester en 4.0.0. *Raison* : le comportement change sur des cas limites ; garder le même numéro rendrait les deux versions indiscernables.

> ⚠ **Limite du full-auto** : aucun humain n'a validé que ce SPEC capture le *bon* problème. Essaie le produit sur un dossier-jouet pour vérifier qu'il fait ce que tu voulais.

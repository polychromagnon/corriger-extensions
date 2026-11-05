# corriger-extensions

Corrige le **nom** des fichiers dont l'extension a été cassée par de mauvais transferts : extension dupliquée et/ou en majuscules. `photo.JPG.JPG` devient `photo.jpg`, `clip.MP4.MP4.MP4` devient `clip.mp4`.

Version 4.2.0, état « Définitif — correctifs de sûreté ». Licence MIT.

## Ce que ça fait

Une seule chose : lire les noms de fichiers d'une arborescence et renommer ceux dont l'extension est cassée. La correction couvre la fusion d'extensions empilées identiques (`photo.jpg.jpg` → `photo.jpg`, y compris le synonyme `jpeg` → `jpg` et la casse `a.JPG.jpg` → `a.jpg`) et la mise en minuscules d'une extension connue (`PHOTO.JPG` → `photo.jpg`). Une pile d'extensions toutes identiques est fusionnée et mise en minuscules quel que soit le type de fichier, même si l'extension est inconnue (`b.ZIP.ZIP` → `b.zip`, `x.FOO.FOO` → `x.foo`).

Extensions connues (69) : photos et images (jpg, jpeg, png, gif, heic, heif, tiff, tif, bmp, webp, raw, cr2, nef, arw, dng, orf, rw2, srw, svg, psd, avif), vidéos (mp4, mov, avi, mkv, m4v, wmv, mpg, mpeg, 3gp, webm, flv, m2ts), audio (mp3, wav, flac, aac, m4a, ogg), documents et bureautique (pdf, doc, docx, txt, rtf, xls, xlsx, ppt, pptx, odt, ods, odp, pages, numbers, key, epub), archives (zip, rar, 7z, tar, gz, dmg, iso), web et données (html, htm, csv, json, xml, md), sidecar Apple Photos (aae).

## Ce que ça ne fait PAS

Le contenu des fichiers n'est jamais ouvert ni lu. Rien n'est déplacé, rien n'est supprimé. L'outil ne vérifie pas si l'extension correspond au format réel du fichier. Deux extensions différentes empilées (`photo.jpg.png`) sont laissées intactes : on ne devine pas laquelle garder. Une extension inconnue seule (`Notes.IMPORTANT`) n'est pas touchée. Un doublon fait uniquement de chiffres (`version.1.1`, `rapport.2024.2024`) n'est jamais fusionné, ni un doublon qui contient autre chose que des lettres ASCII et des chiffres (`x.été.été`, `x.final version.final version`). Une pile qui n'est pas entièrement identique et où une partie intermédiaire n'est pas une extension connue (`IMG.2024.JPG.JPG`) n'est corrigée que sur la casse finale (`IMG.2024.JPG.jpg`) : le doublon survit, c'est une limite assumée. Seule la dernière extension change de casse : `x.TAR.GZ` devient `x.TAR.gz`.

## Garantie d'intégrité des données et des dates

Renommer, c'est modifier l'entrée de répertoire (le lien nom vers fichier), pas le fichier. Les octets de données, le mtime (date de modification), le birthtime (date de création Finder) et les attributs étendus (tags Finder) ne sont pas touchés. Sur le fichier, le seul horodatage que tout renommage POSIX met à jour est le ctime (« Attributs modifiés »), qui n'est pas affiché par le Finder et n'a aucun rapport avec les dates EXIF, lesquelles vivent dans le contenu jamais lu. Le dossier qui contient un fichier renommé voit en revanche sa date de modification passer à l'heure du renommage, comme pour tout renommage : un tri des dossiers par date de modification dans le Finder en sera changé.

Vérifié par les tests sur plateforme Linux : hash SHA-256 des octets inchangé, `st_mtime_ns` inchangé, attributs étendus `user.*` inchangés, inode inchangé. Non vérifiable sur cette plateforme, donc à confirmer manuellement sous macOS : `st_birthtime` (absent de `os.stat` sous Linux) et les tags Finder.

## Filets de sécurité

Le déroulement est en une seule commande : SCAN (lecture des noms, liste figée), APERÇU (décompte et liste écrits, journal produit), CONFIRMATION (o/N, défaut NON), APPLICATION (uniquement sur la liste figée). Ce que l'aperçu montre est exactement ce qui sera fait.

- Lecture seule des noms ; le contenu n'est jamais ouvert.
- Refus de tourner sur `/`, un dossier système (`/System`, `/usr`…), un paquet macOS (`.app`, `.photoslibrary`, `.photolibrary` d'iPhoto, `.pages`…) ou `Library` et les corbeilles (dont `$RECYCLE.BIN` de Windows), y compris quand c'est le dossier passé en argument ou un dossier situé à l'intérieur d'un paquet ou d'une corbeille.
- Ne descend jamais dans les paquets macOS, `Library` ni les corbeilles (`.Trash`, `.Trashes`, `$RECYCLE.BIN`) ; ne renomme jamais un dossier.
- Les liens symboliques ne sont ni suivis en source, ni écrasés en cible. Une entrée symbolique, même cassée, qui occupe le nom cible provoque une abstention nette.
- Aucun fichier existant n'est jamais écrasé. Le renommage passe par un appel système qui échoue si la cible existe déjà (`renameat2` avec `RENAME_NOREPLACE` sous Linux, `renamex_np` avec `RENAME_EXCL` sous macOS), ce qui ferme la fenêtre entre le test et le renommage. Un conflit avec un autre fichier ajoute un suffixe `_2`, `_3`…
- Le renommage de casse pure passe par un nom temporaire avec retour arrière automatique, y compris si le programme est interrompu (Ctrl-C). Aucun nom temporaire `__rename_tmp_*` ne survit à une sortie rattrapable ; un tel reste laissé par un run non rattrapable (coupure de courant, `SIGKILL`) est signalé au run suivant, jamais renommé en silence.
- Un Ctrl-C pendant l'application arrête proprement : le journal reçoit une section INTERROMPU qui dit combien de fichiers de la liste ont été traités, et les suivants ne sont pas touchés.
- Sur un système de fichiers sans renommage atomique (exFAT, partages réseau), l'outil retombe sur un test d'existence puis renommage et affiche un avertissement disant que la garantie anti-écrasement n'est plus atomique.
- Relancer l'outil sur un dossier déjà corrigé ne fait rien (idempotence).

## Emplacement du journal

Le journal (`rename_log_AAAA-MM-JJ_HH-MM-SS.txt`) liste exactement la liste figée, écrite avant toute modification (y compris en `--dry-run`). Il n'est jamais écrit sous la racine scannée : l'emplacement est choisi dans l'ordre dossier courant, dossier personnel, dossier temporaire, en préférant un candidat situé sur un autre volume que la racine. À défaut de tout emplacement possible, le journal n'est pas écrit et la liste est alors affichée en entier à l'écran, jamais tronquée.

## Usage

```
python3 corriger_extensions.py "/Volumes/MonArchive"
python3 corriger_extensions.py "/Volumes/MonArchive" --dry-run   # liste seule, n'applique rien
python3 corriger_extensions.py "/Volumes/MonArchive" --tout      # affiche toute la liste à l'écran
python3 corriger_extensions.py "/Volumes/MonArchive" --oui       # non interactif, applique sans demander
```

## Tests

```
python3 -m pytest test_corriger_extensions.py
```

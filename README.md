# corriger-extensions

Corrige le **nom** des fichiers dont l'extension a été cassée par de mauvais transferts : extension dupliquée et/ou en majuscules. `photo.JPG.JPG` devient `photo.jpg`, `clip.MP4.MP4.MP4` devient `clip.mp4`.

Version 5.0.0, état « Définitif — correctifs de sûreté ». Licence MIT.

## Ce que ça fait

Une seule chose : lire les noms de fichiers d'une arborescence et renommer ceux dont l'extension est cassée. La correction couvre la fusion d'extensions empilées identiques (`photo.jpg.jpg` → `photo.jpg`, y compris le synonyme `jpeg` → `jpg` et la casse `a.JPG.jpg` → `a.jpg`) et la mise en minuscules d'une extension connue (`PHOTO.JPG` → `photo.jpg`). Un doublon d'extension en fin de nom est fusionné et mis en minuscules quel que soit le type de fichier, même si l'extension est inconnue, et même quand le nom contient d'autres points : `b.ZIP.ZIP` → `b.zip`, `x.FOO.FOO` → `x.foo`, `IMG.2024.JPG.JPG` → `IMG.2024.jpg`, `Scan 12.5.PDF.PDF` → `Scan 12.5.pdf`. Un `.jpeg` seul devient `.jpg` (`photo.jpeg` → `photo.jpg`).

L'aperçu et le journal signalent aussi, sans jamais les renommer : les fichiers compagnons qui risquent de ne plus retrouver un fichier renommé (`IMG.JPG.JPG.xmp` de darktable ou digiKam, `IMG.JPG.xmp` de Lightroom), les liens symboliques de l'arborescence qui pointent vers lui, et ce que l'outil laisse de côté, avec la raison : liens non suivis, dossiers `Library`, corbeilles, paquets macOS et dossiers cachés non parcourus, journaux `rename_log_*`, fichier dont le nom corrigé est déjà pris par un lien. Les fichiers cachés (`.DS_Store`, `._photo.jpg`) et les entrées qui ne sont ni des fichiers ni des dossiers ne sont ni touchés ni listés. Les alias Finder ne sont pas détectés.

Extensions connues (69) : photos et images (jpg, jpeg, png, gif, heic, heif, tiff, tif, bmp, webp, raw, cr2, nef, arw, dng, orf, rw2, srw, svg, psd, avif), vidéos (mp4, mov, avi, mkv, m4v, wmv, mpg, mpeg, 3gp, webm, flv, m2ts), audio (mp3, wav, flac, aac, m4a, ogg), documents et bureautique (pdf, doc, docx, txt, rtf, xls, xlsx, ppt, pptx, odt, ods, odp, pages, numbers, key, epub), archives (zip, rar, 7z, tar, gz, dmg, iso), web et données (html, htm, csv, json, xml, md), sidecar Apple Photos (aae).

## Ce que ça ne fait PAS

Le contenu des fichiers n'est jamais ouvert ni lu. Rien n'est déplacé, rien n'est supprimé. L'outil ne vérifie pas si l'extension correspond au format réel du fichier. Deux extensions différentes empilées (`photo.jpg.png`) sont laissées intactes : on ne devine pas laquelle garder. Une extension inconnue seule (`Notes.IMPORTANT`) n'est pas touchée. Un doublon fait uniquement de chiffres (`version.1.1`, `rapport.2024.2024`) n'est jamais fusionné, ni un doublon qui contient autre chose que des lettres ASCII et des chiffres (`x.été.été`, `x.final version.final version`). Hors doublon, seule la dernière extension change de casse : `x.TAR.GZ` devient `x.TAR.gz`. Les fichiers compagnons et les liens signalés ne sont pas renommés.

## Garantie d'intégrité des données et des dates

Renommer, c'est modifier l'entrée de répertoire (le lien nom vers fichier), pas le fichier. Les octets de données, le mtime (date de modification), le birthtime (date de création Finder) et les attributs étendus (tags Finder) ne sont pas touchés. Sur le fichier, le seul horodatage que tout renommage POSIX met à jour est le ctime (« Attributs modifiés »), qui n'est pas affiché par le Finder et n'a aucun rapport avec les dates EXIF, lesquelles vivent dans le contenu jamais lu. Le dossier qui contient un fichier renommé voit sa date de modification passer à l'heure du renommage, comme pour tout renommage : l'outil relève les dates de chaque dossier touché avant d'agir et les remet ensuite, y compris après un Ctrl-C. Un dossier dont la date n'a pas pu être remise est signalé comme erreur. La « Date d'ajout » qu'affiche le Finder n'est pas vérifiée.

Vérifié par les tests sur plateforme Linux : hash SHA-256 des octets inchangé, `st_mtime_ns` inchangé, attributs étendus `user.*` inchangés, inode inchangé, date de modification des dossiers touchés inchangée. Non vérifiable sur cette plateforme, donc à confirmer manuellement sous macOS : `st_birthtime` (absent de `os.stat` sous Linux) et les tags Finder.

## Filets de sécurité

Le déroulement est en une seule commande : SCAN (lecture des noms, liste figée), APERÇU (décompte et liste écrits, journal produit), CONFIRMATION (o/N, défaut NON), APPLICATION (uniquement sur la liste figée). Ce que l'aperçu montre est exactement ce qui sera fait.

- Lecture seule des noms ; le contenu n'est jamais ouvert.
- Refus de tourner sur `/`, un dossier système (`/System`, `/usr`…), un paquet macOS (`.app`, `.photoslibrary`, `.photolibrary` d'iPhoto, `.pages`…) ou `Library` et les corbeilles (dont `$RECYCLE.BIN` de Windows), y compris quand c'est le dossier passé en argument ou un dossier situé à l'intérieur d'un paquet ou d'une corbeille. Un dossier situé sous `Library` mais pas dans un paquet, comme iCloud Drive (`~/Library/Mobile Documents/com~apple~CloudDocs`), est accepté.
- Ne descend jamais dans les paquets macOS, `Library` ni les corbeilles (`.Trash`, `.Trashes`, `$RECYCLE.BIN`) ; ne renomme jamais un dossier.
- Les liens symboliques ne sont ni suivis en source, ni écrasés en cible. Une entrée symbolique, même cassée, qui occupe le nom cible provoque une abstention nette.
- Aucun fichier existant n'est jamais écrasé. Le renommage passe par un appel système qui échoue si la cible existe déjà (`renameat2` avec `RENAME_NOREPLACE` sous Linux, `renamex_np` avec `RENAME_EXCL` sous macOS), ce qui ferme la fenêtre entre le test et le renommage. Un conflit avec un autre fichier ajoute un suffixe `_2`, `_3`… placé avant l'extension, y compris composée (`a.tar.gz.gz` devient `a_2.tar.gz` si `a.tar.gz` existe).
- Le renommage de casse pure passe par un nom temporaire avec retour arrière automatique, y compris si le programme est interrompu (Ctrl-C). Aucun nom temporaire `__rename_tmp_*` ne survit à une sortie rattrapable ; un tel reste laissé par un run non rattrapable (coupure de courant, `SIGKILL`) est signalé au run suivant, jamais renommé en silence.
- Un Ctrl-C, la fermeture du Terminal ou un arrêt demandé par le système (SIGTERM) pendant l'application n'interrompt jamais un fichier en cours de renommage : l'arrêt est lu entre deux fichiers, puis les dates des dossiers sont remises et le journal reçoit une section INTERROMPU qui dit la cause et combien de fichiers de la liste ont été traités ; les suivants ne sont pas touchés. Lancé sous `nohup`, l'outil continue quand le Terminal se ferme. Un Ctrl-C pendant l'analyse, avant tout renommage, arrête l'outil sans rien modifier (code de sortie 130).
- Un nom qui contient un caractère de contrôle (retour à la ligne, séquence d'échappement du terminal) ou d'inversion du sens d'écriture s'affiche échappé (`\n`, `\x1b`, `\u202e`), pour que l'aperçu ne puisse pas être brouillé ; un nom mal encodé s'affiche lui aussi échappé.
- Sur un système de fichiers sans renommage atomique (exFAT, partages réseau), l'outil retombe sur un test d'existence puis renommage et affiche un avertissement disant que la garantie anti-écrasement n'est plus atomique.
- Relancer l'outil sur un dossier déjà corrigé ne fait rien (idempotence).

## Emplacement du journal

Le journal (`rename_log_AAAA-MM-JJ_HH-MM-SS.txt`) liste exactement la liste figée, écrite avant toute modification (y compris en `--dry-run`), puis les compagnons et liens à vérifier, ce qui a été laissé de côté et les dossiers illisibles. À l'écran, ces deux dernières listes ne sont détaillées que si elles tiennent en 40 lignes ; au-delà, elles restent entières dans le journal. Il n'est jamais écrit sous la racine scannée : l'emplacement est choisi dans l'ordre dossier courant, dossier personnel, dossier temporaire, en préférant un candidat situé sur un autre volume que la racine. À défaut de tout emplacement possible, le journal n'est pas écrit et la liste est alors affichée en entier à l'écran, jamais tronquée.

## Usage

```
python3 corriger_extensions.py "/Volumes/MonArchive"
python3 corriger_extensions.py "/Volumes/MonArchive" --dry-run   # liste seule, n'applique rien
python3 corriger_extensions.py "/Volumes/MonArchive" --tout      # affiche toute la liste à l'écran
python3 corriger_extensions.py "/Volumes/MonArchive" --oui       # non interactif, applique sans demander
```

Code de sortie : 0 si tout s'est bien passé (fichiers ignorés par prudence compris) ; 1 en cas de refus, d'usage invalide, d'erreur de renommage ou de dossier illisible ; 130 après un Ctrl-C ; 128 + numéro du signal après une fermeture du Terminal (129) ou un SIGTERM (143).

## Tests (Linux)

La suite automatique est prévue pour Linux : elle crée des noms qui ne diffèrent que par la casse (impossible sur un disque Mac insensible à la casse), utilise `/dev/shm` comme second volume et place ses dossiers d'essai dans `/tmp`, que l'outil refuse sur Mac (zone système `/private`). Sur Mac, elle se déclare sautée.

```
python3 -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q test_corriger_extensions.py
```

## Mutation (Linux)

Pour vérifier que les tests attrapent une erreur introduite dans le code, l'outil mutmut modifie le script de mille façons et relance la suite à chaque fois. Configuration dans `setup.cfg` :

```
.venv/bin/python -m pip install mutmut
.venv/bin/mutmut run
.venv/bin/mutmut results
```

mutmut ne voit pas les tests qui lancent un second processus (arrêt par signal) : les mutants qu'eux seuls tuent apparaissent survivants et se vérifient un par un avec `MUTANT_UNDER_TEST=<nom> python -m pytest` dans le dossier `mutants/`.

## Vérification sur ton Mac

Ce que la suite Linux ne peut pas prouver (date de création, tags Finder, renommage de casse sur APFS, appel système macOS), cet essai le montre sur un dossier jetable. Depuis le dossier du projet, dans le Terminal :

```
python3 --version
```

L'outil exige Python 3.9 ou plus récent.

```
mkdir ~/Desktop/essai-corrext
touch ~/Desktop/essai-corrext/{photo.JPG.JPG,clip.MP4,b.ZIP.ZIP,c.XLSX,version.1.1,Notes.IMPORTANT}
```

Dans le Finder, mets une étiquette de couleur sur `photo.JPG.JPG` et sur `clip.MP4`. Puis :

```
stat -f '%N  créé %SB  modifié %Sm' ~/Desktop/essai-corrext ~/Desktop/essai-corrext/*
mdls -name kMDItemDateAdded ~/Desktop/essai-corrext/*
python3 corriger_extensions.py ~/Desktop/essai-corrext --oui
sleep 15
stat -f '%N  créé %SB  modifié %Sm' ~/Desktop/essai-corrext ~/Desktop/essai-corrext/*
mdls -name kMDItemDateAdded ~/Desktop/essai-corrext/*
```

Attendu : aucune ligne d'erreur ; les fichiers s'appellent maintenant `photo.jpg`, `clip.mp4`, `b.zip`, `c.xlsx`, `version.1.1` et `Notes.IMPORTANT` ; les dates « créé » et « modifié » de chaque fichier, et la date « modifié » du dossier `essai-corrext`, sont les mêmes avant et après ; note si la « Date d'ajout » (`kMDItemDateAdded`) change ; les étiquettes sont toujours visibles dans le Finder. Même essai possible sur un disque externe exFAT en remplaçant `~/Desktop/essai-corrext` par un dossier de ce disque : l'outil y affiche alors l'avertissement de renommage non atomique. L'attente de 15 secondes compte : sur un disque FAT32, macOS Sonoma remet la date de modification d'un fichier renommé à l'heure courante quelques secondes après le renommage (fil Apple Developer Forums 759757, bug FB14464931, jugé régression par un ingénieur Apple) ; l'outil ne peut pas l'empêcher. exFAT n'y est pas testé : c'est ce que l'essai vérifie. Supprime le dossier d'essai ensuite.

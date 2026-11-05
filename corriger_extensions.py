#!/usr/bin/env python3
# menu: Correction des extensions cassées (photo.JPG.JPG → photo.jpg)
# input: folder
"""Nettoie les extensions de fichiers cassées par de mauvais transferts.

Ce script NE FAIT QU'UNE chose : corriger le NOM des fichiers dont l'extension
est dupliquée et/ou en majuscules (photo.JPG.JPG → photo.jpg, clip.MP4.MP4.MP4
→ clip.mp4). Il ne lit JAMAIS le contenu des fichiers, ne déplace rien, ne
supprime rien, ne vérifie pas si l'extension « correspond » au format réel.
Pure lecture des NOMS + renommage du NOM. Rien d'autre.

GARANTIE D'INTÉGRITÉ
    Renommer = modifier une entrée de répertoire (le lien nom → fichier), pas le
    fichier. Les octets de données, le mtime (date de modification), le birthtime
    (date de création Finder) et les attributs étendus (tags Finder, etc.) ne
    sont PAS touchés. Le seul horodatage que tout renommage POSIX met à jour est
    le ctime (« Attributs modifiés ») : il n'est pas affiché par le Finder et n'a
    aucun rapport avec tes dates EXIF (qui sont dans le contenu, jamais lu).

DÉROULEMENT (en une seule commande)
    1. SCAN — parcourt l'arborescence en lisant uniquement les noms de fichiers,
       et dresse la liste exacte des renommages à effectuer.
    2. APERÇU — affiche le décompte (à corriger / déjà corrects) et la liste de
       tout ce qui sera modifié, et écrit cette liste complète dans un journal.
    3. CONFIRMATION — demande o/N. Par défaut (entrée vide, autre touche) : NON.
    4. APPLICATION — n'agit QUE sur la liste figée à l'étape 1. Avant chaque
       renommage, re-vérifie que le fichier source est bien le même (identité par
       (st_dev, st_ino)) et renomme par un appel système qui ÉCHOUE si la cible
       existe déjà (renameat2/RENAME_NOREPLACE sous Linux, renamex_np/RENAME_EXCL
       sous macOS) : aucun fichier ni aucune entrée existante n'est jamais écrasé.

FILETS DE SÉCURITÉ
    - Lecture seule des noms ; le contenu n'est jamais ouvert.
    - Refus de tourner sur « / », un dossier système (/System, /usr…), un paquet
      macOS (.app, .photoslibrary, .pages…) ou « Library »/corbeilles, même quand
      c'est le dossier passé en argument.
    - Ne descend pas dans les dossiers-paquets macOS, ni « Library », ni corbeilles.
    - Ignore les liens symboliques : ni suivis en source, ni écrasés en cible
      (une entrée symbolique, même cassée, qui occupe le nom cible → abstention).
    - Ne renomme jamais un dossier, seulement des fichiers.
    - Fusion d'extensions UNIQUEMENT si elles se réduisent à une seule forme
      (photo.jpg.jpg → photo.jpg). Deux extensions différentes (photo.jpg.png)
      sont laissées intactes : on ne devine pas laquelle garder. Une pile
      d'extensions toutes identiques est fusionnée même si l'extension est
      inconnue (x.FOO.FOO → x.foo), sauf si elle n'est faite que de chiffres
      (version.1.1 intact).
    - Ne met en minuscules que les extensions connues (Notes.IMPORTANT intact).
    - Conflit de nom avec un autre fichier → suffixe _2, _3… ; jamais d'écrasement.
    - Renommage de casse (PHOTO.JPG → photo.jpg) en deux temps, avec retour
      arrière automatique si la seconde étape échoue, y compris sur interruption.
    - La liste figée + le journal sont produits AVANT toute écriture : ce que tu
      vois est exactement ce qui sera fait. Sans journal possible, la liste est
      affichée en entier (jamais tronquée).
    - Le journal est écrit hors de la racine scannée, de préférence sur un autre
      volume, pour ne rien ajouter sous le dossier corrigé.
    - Sur un système de fichiers sans renommage atomique (exFAT, partages réseau),
      repli sur un test d'existence puis renommage, avec avertissement explicite.

USAGE
    python3 corriger_extensions.py "/Volumes/MonArchive"
    python3 corriger_extensions.py "/Volumes/MonArchive" --dry-run   # liste seule, n'applique rien
    python3 corriger_extensions.py "/Volumes/MonArchive" --tout      # affiche TOUTE la liste à l'écran
    python3 corriger_extensions.py "/Volumes/MonArchive" --oui       # non interactif : applique sans demander

Version : 4.2.0 — 05/11/2026
État : Définitif — correctifs de sûreté
Licence : MIT
"""

import ctypes
import errno
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from collections import namedtuple


# ----------------------------------------------------------------------------
# Réglages
# ----------------------------------------------------------------------------

# True : .jpeg → .jpg. (jpg et jpeg = exactement le même format ; ce renommage
# ne change que l'étiquette du nom, jamais le contenu.) Mettre False pour garder .jpeg.
NORMALISER_JPEG = True

# Extensions reconnues. Une pile d'extensions mêlées n'est fusionnée que si elles
# sont toutes ici ET se réduisent à une seule forme. On ne met en minuscules QUE ces
# extensions (hors fusion d'une pile identique, voir _doublon_fusionnable).
KNOWN_EXTS = {
    # Images
    "jpg", "jpeg", "png", "gif", "heic", "heif", "tiff", "tif",
    "bmp", "webp", "raw", "cr2", "nef", "arw", "dng", "orf", "rw2", "srw",
    # Vidéos
    "mp4", "mov", "avi", "mkv", "m4v", "wmv", "mpg", "mpeg",
    "3gp", "webm", "flv", "m2ts",
    # Audio
    "mp3", "wav", "flac", "aac", "m4a", "ogg",
    # Documents
    "pdf", "doc", "docx", "txt", "rtf",
    # Sidecar Apple Photos
    "aae",
    # Archives
    "zip", "rar", "7z", "tar", "gz", "dmg", "iso",
    # Bureautique
    "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "pages", "numbers", "key", "epub",
    # Web et données
    "html", "htm", "csv", "json", "xml", "md",
    # Images (suite)
    "svg", "psd", "avif",
}

NORMALISATIONS = {"jpeg": "jpg"} if NORMALISER_JPEG else {}

# Dossiers « paquets » macOS (présentés comme un seul fichier par le Finder) :
# on ne descend JAMAIS dedans. Format = suffixe en minuscules avec le point.
EXT_DOSSIERS_OPAQUES = {
    ".app", ".bundle", ".framework", ".plugin", ".kext", ".prefpane",
    ".qlgenerator", ".mdimporter", ".component", ".scptd",
    ".photoslibrary", ".aplibrary", ".migratedaplibrary",
    ".tvlibrary", ".theater", ".imovielibrary", ".fcpbundle",
    ".musiclibrary", ".band",
    ".pages", ".numbers", ".key", ".rtfd",
    ".sparsebundle", ".pkg", ".mpkg",
    ".xcodeproj", ".xcworkspace", ".playground", ".dsym", ".xcassets",
}

# Dossiers (par NOM) jamais parcourus. « Library » contient des données d'apps.
# Édite cet ensemble si tu as un dossier de DONNÉES légitimement nommé « Library ».
NOMS_DIR_IGNORES = {"Library", ".Trash", ".Trashes"}

# Emplacements système où le script REFUSE de tourner.
RACINES_INTERDITES = (
    "/System", "/Library", "/usr", "/bin", "/sbin",
    "/private", "/Applications", "/cores", "/opt",
)

# Au-delà de ce nombre de renommages, on n'affiche qu'un aperçu à l'écran (la
# liste complète reste dans le journal). --tout, ou l'absence de journal, force
# l'affichage intégral.
SEUIL_APERCU = 200

# Préfixe des noms temporaires du renommage de casse en deux temps.
PREFIXE_TMP = "__rename_tmp_"


# Une ligne de renommage prévue. Figée au scan, exécutée telle quelle.
#   rel       : chemin relatif (pour l'affichage)
#   src       : chemin absolu du fichier source
#   cible     : chemin absolu du nom cible
#   cible_nom : nom de fichier cible (sans le dossier)
#   case_safe : True si c'est un simple changement de casse (renommage en 2 temps)
#   dev, ino  : identité physique du fichier au moment du scan (anti-confusion)
Modif = namedtuple("Modif", "rel src cible cible_nom case_safe dev ino")


# ----------------------------------------------------------------------------
# Renommage sans écrasement (atomique quand le système le permet)
# ----------------------------------------------------------------------------
#
# La garantie « jamais d'écrasement » ne peut pas reposer sur un test
# `cible.exists()` suivi de `os.rename` : entre les deux, une cible peut
# apparaître (autre process, Finder), et `os.rename` POSIX l'écrase en silence
# (TOCTOU). On demande donc au noyau de refuser lui-même une cible existante.

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1          # Linux renameat2
_RENAME_EXCL = 0x00000004      # macOS renamex_np ; 0x2 est RENAME_SWAP (xnu bsd/sys/stdio.h)

_LIBC = None
try:
    if sys.platform.startswith("linux"):
        _LIBC = ctypes.CDLL("libc.so.6", use_errno=True)
        _LIBC.renameat2.restype = ctypes.c_int
        _LIBC.renameat2.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        ]
    elif sys.platform == "darwin":
        _LIBC = ctypes.CDLL("libSystem.dylib", use_errno=True)
        _LIBC.renamex_np.restype = ctypes.c_int
        _LIBC.renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
except (OSError, AttributeError):
    _LIBC = None

# Errno signalant « ce FS ne sait pas refuser une cible existante » → repli.
_ERRNO_NON_ATOMIQUE = {
    errno.ENOSYS, errno.EINVAL, errno.ENOTSUP,
    getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
}


class Interrompu(KeyboardInterrupt):
    """Ctrl-C pendant l'application : porte les résultats partiels jusqu'au journal."""

    def __init__(self, resultats, traites: int):
        super().__init__()
        self.resultats = resultats
        self.traites = traites


class _AtomicIndisponible(Exception):
    """Le renommage atomique n'est pas supporté ici : il faut le repli."""


def _rename_atomic(src: str, dst: str) -> None:
    """Renomme via l'appel système anti-écrasement. FileExistsError si dst existe."""
    if _LIBC is None:
        raise _AtomicIndisponible
    if sys.platform == "darwin":
        r = _LIBC.renamex_np(os.fsencode(src), os.fsencode(dst), _RENAME_EXCL)
    else:
        r = _LIBC.renameat2(
            _AT_FDCWD, os.fsencode(src), _AT_FDCWD, os.fsencode(dst), _RENAME_NOREPLACE,
        )
    if r == 0:
        return
    e = ctypes.get_errno()
    if e == errno.EEXIST:
        raise FileExistsError(e, os.strerror(e), dst)
    if e in _ERRNO_NON_ATOMIQUE:
        raise _AtomicIndisponible
    raise OSError(e, os.strerror(e), dst)


def _rename_fallback(src: str, dst: str) -> None:
    """Repli non atomique : test d'existence (liens cassés compris) puis renommage.

    Non atomique : garde une fenêtre TOCTOU, d'où l'avertissement affiché quand
    ce chemin est emprunté.
    """
    if os.path.lexists(dst):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), dst)
    os.rename(src, dst)


def _rename_no_overwrite(src: str, dst: str) -> bool:
    """Renomme src→dst sans jamais écraser dst. Renvoie True si le repli a servi.

    Lève FileExistsError si dst est déjà occupé par n'importe quelle entrée de
    répertoire (fichier, dossier, lien symbolique même cassé).
    """
    if os.environ.get("CORREXT_FORCE_NON_ATOMIC") == "1":
        _rename_fallback(src, dst)
        return True
    try:
        _rename_atomic(src, dst)
        return False
    except _AtomicIndisponible:
        _rename_fallback(src, dst)
        return True


# ----------------------------------------------------------------------------
# Calcul du nom propre (aucune lecture de contenu)
# ----------------------------------------------------------------------------

def _doublon_fusionnable(suffixes: list[str]) -> bool:
    forme = suffixes[0].lower()
    return (len(suffixes) > 1
            and all(s.lower() == forme for s in suffixes)
            and forme.isascii() and forme.isalnum()
            and not forme.isdigit())


def nouveau_nom(nom: str) -> str:
    """Nom corrigé pour un fichier, ou le nom inchangé s'il est déjà propre.

    - extensions empilées toutes connues et réductibles à une seule forme → fusion ;
    - extensions empilées toutes identiques (casse ignorée), même inconnues → fusion,
      sauf partie faite uniquement de chiffres (version.1.1) ou hors [A-Za-z0-9] ;
    - sinon, casse de la dernière extension normalisée SI elle est connue ;
    - si la dernière partie n'est pas une extension connue → rien n'est touché.
    """
    if "." not in nom:
        return nom

    parties = nom.split(".")
    if parties[0] == "":            # nom caché (.qqch) : sécurité, on ne touche pas
        return nom

    suffixes = parties[1:]
    tous_connus = all(s.lower() in KNOWN_EXTS for s in suffixes)

    derniere = parties[-1]
    derniere_norm = NORMALISATIONS.get(derniere.lower(), derniere.lower())
    derniere_connue = derniere.lower() in KNOWN_EXTS

    if tous_connus:
        formes = {NORMALISATIONS.get(s.lower(), s.lower()) for s in suffixes}
        if len(formes) == 1:        # duplication réductible à UNE forme → fusion
            return f"{parties[0]}.{derniere_norm}"

    if _doublon_fusionnable(suffixes):
        return f"{parties[0]}.{derniere.lower()}"

    if derniere_connue:             # on normalise juste la casse de l'extension finale
        return f"{'.'.join(parties[:-1])}.{derniere_norm}"

    return nom                      # dernière partie inconnue → intact


def meme_fichier(a: Path, b: Path) -> bool:
    """True si a et b sont le même fichier physique (même inode)."""
    try:
        return a.samefile(b)
    except OSError:
        return False


def _nom_libre(cible: Path, reserves: set) -> Path:
    """cible_2, cible_3… en évitant le disque ET les cibles déjà réservées.

    « occupé » inclut les liens symboliques cassés (os.path.lexists), qu'un simple
    exists() manquerait, et la casse insensible (comparaison en minuscules).
    """
    def occupe(p: Path) -> bool:
        return os.path.lexists(p) or str(p).lower() in reserves

    if not occupe(cible):
        return cible
    parent, base, ext = cible.parent, cible.stem, cible.suffix
    n = 2
    while True:
        cand = parent / f"{base}_{n}{ext}"
        if not occupe(cand):
            return cand
        n += 1


# ----------------------------------------------------------------------------
# Étape 1 — SCAN (lecture des noms uniquement)
# ----------------------------------------------------------------------------

def est_racine_interdite(racine: Path) -> bool:
    """True si la racine est une zone protégée : système, paquet macOS ou corbeille.

    La racine passée en argument subit les mêmes filtres que la descente : pointer
    directement sur un .photoslibrary ou ~/Library est refusé, pas seulement évité
    en descendant.
    """
    s = str(racine)
    if s == "/":
        return True
    if any(s == p or s.startswith(p + "/") for p in RACINES_INTERDITES):
        return True
    if racine.name in NOMS_DIR_IGNORES:
        return True
    if racine.suffix.lower() in EXT_DOSSIERS_OPAQUES:
        return True
    return False


def scanner(racine: Path):
    """Parcourt l'arborescence et renvoie (modifs, nb_deja_ok, erreurs_acces, orphelins).

    N'ouvre aucun fichier. Utilise os.scandir (rapide sur gros volumes : le type
    de chaque entrée est connu sans appel système supplémentaire). `orphelins`
    liste les noms temporaires __rename_tmp_* laissés par un run précédent interrompu.
    """
    modifs: list[Modif] = []
    deja_ok = 0
    erreurs_acces: list[str] = []
    orphelins: list[str] = []

    pile = [str(racine)]
    while pile:
        dossier = pile.pop()
        try:
            with os.scandir(dossier) as it:
                entrees = list(it)
        except OSError as e:
            erreurs_acces.append(str(e))
            continue

        sous_dossiers: list[str] = []
        fichiers = []
        for e in entrees:
            try:
                if e.is_symlink():
                    continue                      # on ne suit jamais les liens
                if e.is_dir(follow_symlinks=False):
                    nm = e.name
                    if nm.startswith(".") or nm in NOMS_DIR_IGNORES \
                       or Path(nm).suffix.lower() in EXT_DOSSIERS_OPAQUES:
                        continue                  # élagage
                    sous_dossiers.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    fichiers.append(e)
            except OSError as ex:
                erreurs_acces.append(str(ex))

        # Fichiers du dossier traités triés, avec réservation des cibles LOCALE
        # au dossier (deux fichiers du même dossier ne peuvent pas viser le même nom).
        reserves: set = set()
        for e in sorted(fichiers, key=lambda x: x.name):
            nom = e.name
            if nom.startswith(".") or nom.startswith("rename_log_"):
                continue
            if nom.startswith(PREFIXE_TMP):
                orphelins.append(_rel(Path(e.path), racine))
                continue

            nouveau = nouveau_nom(nom)
            if nouveau == nom:
                deja_ok += 1
                continue

            src = Path(e.path)
            ideal = src.with_name(nouveau)

            # Une entrée symbolique (même cassée) occupe le nom cible : on ne la
            # détruit pas, et on ne suffixe pas autour (ce nom EST la correction
            # voulue) — abstention nette sur ce fichier.
            if os.path.islink(ideal):
                continue

            cible = ideal
            case_safe = False
            if str(cible).lower() in reserves:
                cible = _nom_libre(cible, reserves)         # conflit dans le lot
            elif os.path.lexists(cible):
                if nom.lower() == nouveau.lower() and meme_fichier(src, cible):
                    case_safe = True                        # pli de casse OU lien dur
                else:
                    cible = _nom_libre(cible, reserves)     # conflit avec un autre fichier
            reserves.add(str(cible).lower())

            try:
                st = e.stat(follow_symlinks=False)
            except OSError as ex:
                erreurs_acces.append(str(ex))
                continue

            modifs.append(Modif(_rel(src, racine), str(src), str(cible), cible.name,
                                case_safe, st.st_dev, st.st_ino))

        pile.extend(sorted(sous_dossiers, reverse=True))

    modifs.sort(key=lambda m: m.rel)
    return modifs, deja_ok, erreurs_acces, orphelins


def _rel(src: Path, racine: Path) -> str:
    try:
        return str(src.relative_to(racine))
    except ValueError:
        return str(src)


# ----------------------------------------------------------------------------
# Étape 4 — APPLICATION (uniquement sur la liste figée)
# ----------------------------------------------------------------------------

def _temp_libre(src: Path, cible_nom: str) -> Path:
    temp = src.with_name(f"{PREFIXE_TMP}{cible_nom}")
    if os.path.lexists(temp):
        temp = _nom_libre(temp, set())
    return temp


def appliquer(modifs: list[Modif]):
    """Exécute les renommages de la liste.

    Renvoie (nb_renommes, ignores, erreurs, repli_non_atomique). L'appelé n'agit
    QUE sur la liste figée ; il s'abstient sur tout élément dont l'état a changé
    depuis le scan (identité, cible occupée). Une interruption (Ctrl-C) pendant le
    renommage de casse en deux temps est rattrapée : l'état est restauré avant que
    l'exception ne remonte, aucun __rename_tmp_* ne survit.
    """
    renommes = 0
    ignores: list[tuple[str, str]] = []
    erreurs: list[tuple[str, str]] = []
    repli = False
    traites = 0
    try:
        for m in modifs:
            renommes, repli = _appliquer_un(m, renommes, ignores, erreurs, repli)
            traites += 1
    except KeyboardInterrupt as e:
        raise Interrompu((renommes, ignores, erreurs, repli), traites) from e
    return renommes, ignores, erreurs, repli


def _appliquer_un(m: Modif, renommes: int, ignores, erreurs, repli: bool):
    src = Path(m.src)
    cible = Path(m.cible)

    # --- Re-vérifications de sécurité (l'état a-t-il changé depuis le scan ?) ---
    try:
        if not src.exists() or src.is_symlink():
            ignores.append((m.rel, "source disparue ou devenue un lien"))
            return renommes, repli
        st = src.stat()
        if (st.st_dev, st.st_ino) != (m.dev, m.ino):
            ignores.append((m.rel, "source remplacée depuis le scan"))
            return renommes, repli
    except OSError as e:
        erreurs.append((m.rel, str(e)))
        return renommes, repli

    # --- Renommage ---
    if m.case_safe:
        # Changement de casse : passage par un nom temporaire, avec retour
        # arrière si la 2e étape échoue OU si le process est interrompu.
        temp = _temp_libre(src, m.cible_nom)
        try:
            repli |= _rename_no_overwrite(str(src), str(temp))       # étape 1
        except OSError as e:
            erreurs.append((m.rel, str(e)))
            return renommes, repli
        try:
            repli |= _rename_no_overwrite(str(temp), str(cible))     # étape 2
        except FileExistsError:
            os.rename(str(temp), str(src))                          # rollback, abstention
            ignores.append((m.rel, "cible occupée (lien dur / apparue depuis le scan)"))
            return renommes, repli
        except OSError as e:
            os.rename(str(temp), str(src))                          # rollback, erreur
            erreurs.append((m.rel, str(e)))
            return renommes, repli
        except BaseException:
            # Ctrl-C / SIGINT entre les deux étapes : on restaure avant de remonter.
            try:
                os.rename(str(temp), str(src))
            except OSError:
                pass
            raise
        renommes += 1
    else:
        try:
            repli |= _rename_no_overwrite(str(src), str(cible))
        except FileExistsError:
            ignores.append((m.rel, "cible occupée depuis le scan"))
            return renommes, repli
        except OSError as e:
            erreurs.append((m.rel, str(e)))
            return renommes, repli
        renommes += 1

    return renommes, repli


# ----------------------------------------------------------------------------
# Affichage + journal
# ----------------------------------------------------------------------------

AVERTISSEMENT_NON_ATOMIQUE = (
    "⚠️  Système de fichiers sans renommage atomique (exFAT / partage réseau) : "
    "la garantie anti-écrasement a reposé sur un test d'existence, non atomique."
)


def choisir_journal(racine: Path):
    """Choisit où écrire le journal. Renvoie (chemin | None, meme_volume: bool).

    Ordre de préférence : un candidat (cwd, home, dossier temporaire) HORS de la
    racine scannée ET sur un autre volume ; à défaut, hors de la racine mais même
    volume (meme_volume=True, annoncé à l'écran) ; à défaut, None. On n'écrit
    JAMAIS sous la racine scannée.
    """
    nom = f"rename_log_{datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
    try:
        dev_racine = racine.stat().st_dev
    except OSError:
        dev_racine = None

    hors_volume = None
    meme_volume = None
    for base in (Path.cwd(), Path.home(), Path(tempfile.gettempdir())):
        try:
            base_res = base.resolve()
        except OSError:
            continue
        if base_res == racine or racine in base_res.parents:
            continue                                  # jamais sous la racine scannée
        cand = base_res / nom
        if not _inscriptible(cand):
            continue
        try:
            dev_base = base_res.stat().st_dev
        except OSError:
            continue
        if dev_racine is not None and dev_base != dev_racine:
            hors_volume = hors_volume or cand
        else:
            meme_volume = meme_volume or cand

    if hors_volume:
        return hors_volume, False
    if meme_volume:
        return meme_volume, True
    return None, False


def _inscriptible(cand: Path) -> bool:
    try:
        with cand.open("w"):
            pass
        cand.unlink()
        return True
    except OSError:
        return False


def ecrire_journal_prevu(journal: Path, racine, modifs, deja_ok, erreurs_acces, orphelins) -> None:
    with journal.open("w", encoding="utf-8") as f:
        f.write(f"Journal de nettoyage d'extensions — {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Racine : {racine}\n")
        f.write("État : LISTE PRÉVUE (rien n'a encore été renommé)\n")
        f.write("=" * 78 + "\n\n")
        f.write(f"À CORRIGER — {len(modifs)} fichier(s)\n")
        f.write("-" * 78 + "\n")
        for m in modifs:
            f.write(f"{m.rel}\n  → {m.cible_nom}\n\n")
        f.write(f"\nDÉJÀ CORRECTS — {deja_ok} fichier(s) (nom déjà propre)\n")
        if orphelins:
            f.write(f"\nORPHELINS D'UN RUN INTERROMPU — {len(orphelins)} (jamais renommés)\n")
            f.write("-" * 78 + "\n")
            for rel in orphelins:
                f.write(f"{rel}\n")
        if erreurs_acces:
            f.write(f"\nDOSSIERS INACCESSIBLES (ignorés) — {len(erreurs_acces)}\n")
            f.write("-" * 78 + "\n")
            for msg in erreurs_acces:
                f.write(f"{msg}\n")


def ajouter_resultats(journal: Path, renommes, ignores, erreurs, repli, interruption=None) -> None:
    with journal.open("a", encoding="utf-8") as f:
        f.write("\n\n" + "=" * 78 + "\n")
        f.write(f"RÉSULTATS — {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write("=" * 78 + "\n")
        if interruption:
            traites, total = interruption
            f.write(f"INTERROMPU (Ctrl-C) après {traites} fichier(s) traité(s) sur {total}, dans "
                    "l'ordre de la liste ci-dessus. Le fichier en cours au moment de l'arrêt "
                    "peut avoir été renommé ou non ; les suivants n'ont pas été touchés.\n")
        f.write(f"Renommés avec succès : {renommes}\n")
        if repli:
            f.write(f"\n{AVERTISSEMENT_NON_ATOMIQUE}\n")
        if ignores:
            f.write(f"\nIGNORÉS (état changé depuis le scan, par prudence) — {len(ignores)}\n")
            f.write("-" * 78 + "\n")
            for rel, why in ignores:
                f.write(f"{rel} : {why}\n")
        if erreurs:
            f.write(f"\nERREURS — {len(erreurs)}\n")
            f.write("-" * 78 + "\n")
            for rel, why in erreurs:
                f.write(f"{rel} : {why}\n")


def afficher_apercu(racine, modifs, deja_ok, erreurs_acces, orphelins, journal, meme_volume, tout) -> None:
    print()
    print(f"📁 Racine                  : {racine}")
    print(f"🔧 À corriger              : {len(modifs)}")
    print(f"✅ Déjà corrects           : {deja_ok}")
    if erreurs_acces:
        print(f"🚫 Dossiers inaccessibles  : {len(erreurs_acces)} (ignorés)")
    if orphelins:
        print(f"🧹 Restes d'un run interrompu (__rename_tmp_*, jamais renommés) : {len(orphelins)}")
        for rel in orphelins:
            print(f"      · {rel}")
    if journal:
        print(f"📝 Liste complète (journal): {journal}")
        if meme_volume:
            print("   ⚠️  Journal sur le MÊME volume que la racine (aucun autre volume inscriptible trouvé).")
    else:
        print("📝 Journal non écrit (aucun emplacement hors racine) : liste affichée en entier ci-dessous.")

    if not modifs:
        return

    print("\nRenommages prévus :")
    print("-" * 70)
    integral = tout or journal is None or len(modifs) <= SEUIL_APERCU
    a_montrer = modifs if integral else modifs[:40]
    for m in a_montrer:
        print(f"  {m.rel}")
        print(f"      → {m.cible_nom}")
    if len(a_montrer) < len(modifs):
        reste = len(modifs) - len(a_montrer)
        print(f"  … +{reste} autre(s) non affichés ici.")
        print("  Liste intégrale dans le journal ci-dessus (ouvre-le pour tout vérifier).")
        print("  (Relance avec --tout pour tout afficher à l'écran.)")


def demander_confirmation(nb: int) -> bool:
    if not sys.stdin.isatty():
        print("\n⏸️  Entrée non interactive : aucune modification effectuée.")
        print("   (Pour appliquer sans invite, relance avec --oui.)")
        return False
    try:
        rep = input(f"\n➡️  Appliquer ces {nb} renommage(s) ? [o/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAnnulé.")
        return False
    return rep in ("o", "oui", "y", "yes")


# ----------------------------------------------------------------------------
# Point d'entrée
# ----------------------------------------------------------------------------

def main() -> None:
    dry_run = False
    tout = False
    auto_oui = False
    chemins: list[str] = []
    for arg in sys.argv[1:]:
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--tout":
            tout = True
        elif arg in ("--oui", "--yes"):
            auto_oui = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            chemins.append(arg)

    if len(chemins) != 1:
        print("Usage : python3 corriger_extensions.py <dossier> [--dry-run] [--tout] [--oui]")
        sys.exit(1)

    racine = Path(chemins[0]).expanduser().resolve()
    if not racine.is_dir():
        print(f"❌ Dossier introuvable ou invalide : {racine}")
        sys.exit(1)
    if est_racine_interdite(racine):
        print(f"⛔ Refus : « {racine} » est un emplacement protégé (système, paquet macOS ou corbeille).")
        print("   Vise un dossier de données (ex. ~/Pictures, ~/Movies, /Volumes/TonArchive).")
        sys.exit(1)

    # 1) Scan (lecture des noms uniquement)
    print(f"🔎 Analyse des noms de fichiers sous : {racine}")
    print("   (lecture seule, le contenu des fichiers n'est jamais ouvert)")
    modifs, deja_ok, erreurs_acces, orphelins = scanner(racine)

    # 2) Aperçu + journal de la liste prévue (écrit AVANT toute modification, --dry-run compris)
    journal, meme_volume = choisir_journal(racine)
    if journal:
        try:
            ecrire_journal_prevu(journal, racine, modifs, deja_ok, erreurs_acces, orphelins)
        except OSError as e:
            print(f"⚠️  Journal non écrit ({e}) ; liste affichée en entier ci-dessous.")
            journal = None
    afficher_apercu(racine, modifs, deja_ok, erreurs_acces, orphelins, journal, meme_volume, tout)

    if not modifs:
        print("\n✅ Aucune extension à corriger. Rien à faire.")
        return

    if dry_run:
        print("\n🧪 --dry-run : liste affichée, aucune modification effectuée.")
        return

    # 3) Confirmation
    ok = True if auto_oui else demander_confirmation(len(modifs))
    if not ok:
        print("✋ Aucune modification effectuée.")
        return

    # 4) Application (uniquement sur la liste figée)
    try:
        renommes, ignores, erreurs, repli = appliquer(modifs)
    except Interrompu as e:
        if journal:
            try:
                ajouter_resultats(journal, *e.resultats, interruption=(e.traites, len(modifs)))
            except OSError:
                pass
        print(f"\n⛔ Interrompu après {e.traites} fichier(s) traité(s) sur {len(modifs)} "
              f"({e.resultats[0]} renommé(s)) ; le fichier en cours peut avoir été renommé ou non, "
              "les suivants n'ont pas été touchés.")
        if journal:
            print(f"📝 Journal complet : {journal}")
        sys.exit(130)
    if journal:
        try:
            ajouter_resultats(journal, renommes, ignores, erreurs, repli)
        except OSError:
            pass

    print()
    print(f"✅ Terminé. {renommes} fichier(s) renommé(s).")
    if repli:
        print(AVERTISSEMENT_NON_ATOMIQUE)
    if ignores:
        print(f"⏭️  {len(ignores)} ignoré(s) par prudence (état changé depuis le scan ; détails dans le journal).")
    if erreurs:
        print(f"❌ {len(erreurs)} erreur(s) (détails dans le journal).")
    if journal:
        print(f"📝 Journal complet : {journal}")


if __name__ == "__main__":
    main()

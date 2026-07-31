#!/usr/bin/env python3
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
       inode) et que la cible n'existe pas : sinon il s'abstient. Aucun fichier
       existant n'est jamais écrasé. Affiche enfin le nombre exact de renommages.

FILETS DE SÉCURITÉ
    - Lecture seule des noms ; le contenu n'est jamais ouvert.
    - Refus de tourner sur « / » ou un dossier système (/System, /Library, /usr…).
    - Ne descend pas dans les dossiers-paquets macOS (.app, .photoslibrary,
      .pages…), ni dans « Library », ni dans les corbeilles.
    - Ignore les liens symboliques (fichiers comme dossiers).
    - Ne renomme jamais un dossier, seulement des fichiers.
    - Fusion d'extensions UNIQUEMENT si elles sont identiques (photo.jpg.jpg →
      photo.jpg). Deux extensions différentes (photo.jpg.png) sont laissées
      intactes : on ne devine pas laquelle garder.
    - Ne met en minuscules que les extensions connues (Notes.IMPORTANT n'est pas
      touché).
    - Conflit de nom → suffixe _2, _3… ; jamais d'écrasement.
    - Renommage de casse (PHOTO.JPG → photo.jpg) en deux temps, avec retour
      arrière automatique si la seconde étape échoue.
    - La liste figée + le journal sont produits AVANT toute écriture : ce que tu
      vois est exactement ce qui sera fait.
    - Le journal est écrit hors du disque scanné (dans le dossier courant), pour
      ne rien ajouter sur le volume cible.

USAGE
    python3 corriger_extensions.py "/Volumes/MonArchive"
    python3 corriger_extensions.py "/Volumes/MonArchive" --dry-run   # liste seule, n'applique rien
    python3 corriger_extensions.py "/Volumes/MonArchive" --tout      # affiche TOUTE la liste à l'écran
    python3 corriger_extensions.py "/Volumes/MonArchive" --oui       # non interactif : applique sans demander

Version : 4.0.0 — 03/06/2026
État : Définitif
Licence : MIT
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from collections import namedtuple


# ----------------------------------------------------------------------------
# Réglages
# ----------------------------------------------------------------------------

# True : .jpeg → .jpg. (jpg et jpeg = exactement le même format ; ce renommage
# ne change que l'étiquette du nom, jamais le contenu.) Mettre False pour garder .jpeg.
NORMALISER_JPEG = True

# Extensions reconnues. On ne « fusionne » des extensions empilées que si elles
# sont toutes ici ET identiques. On ne met en minuscules QUE ces extensions.
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
# liste complète reste dans le journal). --tout force l'affichage intégral.
SEUIL_APERCU = 200


# Une ligne de renommage prévue. Figée au scan, exécutée telle quelle.
#   rel       : chemin relatif (pour l'affichage)
#   src       : chemin absolu du fichier source
#   cible     : chemin absolu du nom cible
#   cible_nom : nom de fichier cible (sans le dossier)
#   case_safe : True si c'est un simple changement de casse (renommage en 2 temps)
#   dev, ino  : identité physique du fichier au moment du scan (anti-confusion)
Modif = namedtuple("Modif", "rel src cible cible_nom case_safe dev ino")


# ----------------------------------------------------------------------------
# Calcul du nom propre (aucune lecture de contenu)
# ----------------------------------------------------------------------------

def nouveau_nom(nom: str) -> str:
    """Nom corrigé pour un fichier, ou le nom inchangé s'il est déjà propre.

    - extensions empilées toutes identiques (casse/synonyme près) → fusion ;
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
        if len(formes) == 1:        # vraie duplication d'UNE même extension → fusion
            return f"{parties[0]}.{derniere_norm}"

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

    `reserves` contient des chemins en minuscules (comparaison insensible à la
    casse, comme APFS par défaut) pour éviter toute collision dans un même lot.
    """
    def occupe(p: Path) -> bool:
        return p.exists() or str(p).lower() in reserves

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
    s = str(racine)
    if s == "/":
        return True
    return any(s == p or s.startswith(p + "/") for p in RACINES_INTERDITES)


def scanner(racine: Path):
    """Parcourt l'arborescence et renvoie (modifs, nb_deja_ok, erreurs_acces).

    N'ouvre aucun fichier. Utilise os.scandir (rapide sur gros volumes : le type
    de chaque entrée est connu sans appel système supplémentaire).
    """
    modifs: list[Modif] = []
    deja_ok = 0
    erreurs_acces: list[str] = []

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
            if nom.startswith(".") or nom.startswith("rename_log_") \
               or nom.startswith("__rename_tmp_"):
                continue

            nouveau = nouveau_nom(nom)
            if nouveau == nom:
                deja_ok += 1
                continue

            src = Path(e.path)
            cible = src.with_name(nouveau)
            case_safe = False

            if str(cible).lower() in reserves:
                cible = _nom_libre(cible, reserves)         # conflit dans le lot
            elif cible.exists():
                if nom.lower() == nouveau.lower() and meme_fichier(src, cible):
                    case_safe = True                        # simple changement de casse
                else:
                    cible = _nom_libre(cible, reserves)     # conflit avec un autre fichier
            reserves.add(str(cible).lower())

            try:
                st = e.stat(follow_symlinks=False)
            except OSError as ex:
                erreurs_acces.append(str(ex))
                continue

            try:
                rel = str(src.relative_to(racine))
            except ValueError:
                rel = str(src)

            modifs.append(Modif(rel, str(src), str(cible), cible.name,
                                case_safe, st.st_dev, st.st_ino))

        pile.extend(sorted(sous_dossiers, reverse=True))

    modifs.sort(key=lambda m: m.rel)
    return modifs, deja_ok, erreurs_acces


# ----------------------------------------------------------------------------
# Étape 4 — APPLICATION (uniquement sur la liste figée)
# ----------------------------------------------------------------------------

def appliquer(modifs: list[Modif]):
    """Exécute les renommages de la liste. Renvoie (nb_renommes, ignores, erreurs)."""
    renommes = 0
    ignores: list[tuple[str, str]] = []
    erreurs: list[tuple[str, str]] = []

    for m in modifs:
        src = Path(m.src)
        cible = Path(m.cible)

        # --- Re-vérifications de sécurité (l'état a-t-il changé depuis le scan ?) ---
        try:
            if not src.exists() or src.is_symlink():
                ignores.append((m.rel, "source disparue ou devenue un lien"))
                continue
            st = src.stat()
            if (st.st_dev, st.st_ino) != (m.dev, m.ino):
                ignores.append((m.rel, "source remplacée depuis le scan"))
                continue
        except OSError as e:
            erreurs.append((m.rel, str(e)))
            continue

        # --- Renommage ---
        try:
            if m.case_safe:
                # Changement de casse sur disque insensible à la casse : passage
                # par un nom temporaire, avec retour arrière si la 2e étape échoue.
                temp = src.with_name(f"__rename_tmp_{m.cible_nom}")
                if temp.exists():
                    temp = _nom_libre(temp, set())
                src.rename(temp)
                try:
                    temp.rename(cible)
                except OSError:
                    temp.rename(src)        # rollback
                    raise
            else:
                # Ne JAMAIS écraser : si la cible est apparue depuis le scan, on s'abstient.
                if cible.exists() and not meme_fichier(src, cible):
                    ignores.append((m.rel, "cible occupée depuis le scan"))
                    continue
                src.rename(cible)
            renommes += 1
        except OSError as e:
            erreurs.append((m.rel, str(e)))

    return renommes, ignores, erreurs


# ----------------------------------------------------------------------------
# Affichage + journal
# ----------------------------------------------------------------------------

def choisir_journal() -> Path | None:
    """Crée le journal dans le dossier courant (à défaut, le home). None si impossible."""
    nom = f"rename_log_{datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
    for base in (Path.cwd(), Path.home()):
        cand = base / nom
        try:
            cand.open("w", encoding="utf-8").close()
            return cand
        except OSError:
            continue
    return None


def ecrire_journal_prevu(journal: Path, racine: Path, modifs, deja_ok, erreurs_acces) -> None:
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
        if erreurs_acces:
            f.write(f"\nDOSSIERS INACCESSIBLES (ignorés) — {len(erreurs_acces)}\n")
            f.write("-" * 78 + "\n")
            for msg in erreurs_acces:
                f.write(f"{msg}\n")


def ajouter_resultats(journal: Path, renommes, ignores, erreurs) -> None:
    with journal.open("a", encoding="utf-8") as f:
        f.write("\n\n" + "=" * 78 + "\n")
        f.write(f"RÉSULTATS — {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write("=" * 78 + "\n")
        f.write(f"Renommés avec succès : {renommes}\n")
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


def afficher_apercu(racine, modifs, deja_ok, erreurs_acces, journal, tout) -> None:
    print()
    print(f"📁 Racine                  : {racine}")
    print(f"🔧 À corriger              : {len(modifs)}")
    print(f"✅ Déjà corrects           : {deja_ok}")
    if erreurs_acces:
        print(f"🚫 Dossiers inaccessibles  : {len(erreurs_acces)} (ignorés)")
    if journal:
        print(f"📝 Liste complète (journal): {journal}")

    if not modifs:
        return

    print("\nRenommages prévus :")
    print("-" * 70)
    a_montrer = modifs if (tout or len(modifs) <= SEUIL_APERCU) else modifs[:40]
    for m in a_montrer:
        print(f"  {m.rel}")
        print(f"      → {m.cible_nom}")
    if len(a_montrer) < len(modifs):
        reste = len(modifs) - len(a_montrer)
        print(f"  … +{reste} autre(s) non affichés ici.")
        print(f"  Liste intégrale dans le journal ci-dessus (ouvre-le pour tout vérifier).")
        print(f"  (Relance avec --tout pour tout afficher à l'écran.)")


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
        print(f"⛔ Refus : « {racine} » est un emplacement système protégé.")
        print("   Vise un dossier de données (ex. ~/Pictures, ~/Movies, /Volumes/TonArchive).")
        sys.exit(1)

    # 1) Scan (lecture des noms uniquement)
    print(f"🔎 Analyse des noms de fichiers sous : {racine}")
    print("   (lecture seule, le contenu des fichiers n'est jamais ouvert)")
    modifs, deja_ok, erreurs_acces = scanner(racine)

    # 2) Aperçu + journal de la liste prévue
    journal = choisir_journal()
    if journal:
        try:
            ecrire_journal_prevu(journal, racine, modifs, deja_ok, erreurs_acces)
        except OSError as e:
            print(f"⚠️  Journal non écrit ({e}) ; le résumé à l'écran reste valable.")
            journal = None
    afficher_apercu(racine, modifs, deja_ok, erreurs_acces, journal, tout)

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
    renommes, ignores, erreurs = appliquer(modifs)
    if journal:
        try:
            ajouter_resultats(journal, renommes, ignores, erreurs)
        except OSError:
            pass

    print()
    print(f"✅ Terminé. {renommes} fichier(s) renommé(s).")
    if ignores:
        print(f"⏭️  {len(ignores)} ignoré(s) par prudence (état changé depuis le scan ; détails dans le journal).")
    if erreurs:
        print(f"❌ {len(erreurs)} erreur(s) (détails dans le journal).")
    if journal:
        print(f"📝 Journal complet : {journal}")


if __name__ == "__main__":
    main()

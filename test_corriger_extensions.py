"""Tests du contrat gelé de corriger_extensions (SPEC.md).

Chaque test cite la preuve du SPEC qu'il couvre. Plateforme de test : Linux, FS
sensible à la casse. Ce qui n'est pas vérifiable ici (st_birthtime, tags Finder,
chemin complet sur FS insensible à la casse) est déclaré tel quel dans le SPEC,
jamais simulé.
"""

import ctypes
import errno
import hashlib
import os
import signal
import sys
from pathlib import Path

import pytest

import corriger_extensions as corr

# Suite prévue pour Linux (FS sensible à la casse, /dev/shm, os.setxattr, dossier
# temporaire hors des zones système). Sur Mac : procédure manuelle du README.
pytestmark = pytest.mark.skipif(
    sys.platform == "darwin", reason="suite Linux ; sur Mac, suivre la vérification manuelle du README")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def touch(p: Path, data: bytes = b"data") -> Path:
    p.write_bytes(data)
    return p


def scan_apply(racine: Path):
    modifs, deja_ok, err_acces, orphelins = corr.scanner(racine)
    renommes, ignores, erreurs, repli = corr.appliquer(modifs)
    return {
        "modifs": modifs, "deja_ok": deja_ok, "orphelins": orphelins,
        "renommes": renommes, "ignores": ignores, "erreurs": erreurs, "repli": repli,
    }


def noms(racine: Path):
    return sorted(os.listdir(racine))


def forge(path: Path, cible_nom: str, case_safe: bool, racine: Path) -> corr.Modif:
    st = os.stat(path)
    cible = str(path.with_name(cible_nom))
    return corr.Modif(str(path.relative_to(racine)), str(path), cible, cible_nom,
                      case_safe, st.st_dev, st.st_ino)


# ---------------------------------------------------------------------------
# §2 — nouveau_nom : fusion, casse, limites (tests purs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entree,attendu", [
    ("photo.jpg.jpg", "photo.jpg"),           # fusion identiques
    ("clip.mp4.mp4.mp4", "clip.mp4"),         # N occurrences → 1
    ("photo.jpeg.jpg", "photo.jpg"),          # synonyme jpeg→jpg fusionné
    ("a.JPG.jpg", "a.jpg"),                   # casse fusionnée
    ("a.JPG", "a.jpg"),                       # minuscule d'extension connue
    ("PHOTO.JPG", "PHOTO.jpg"),               # casse, stem inchangé
    ("photo.jpg.png", "photo.jpg.png"),       # extensions différentes → intact
    ("Notes.IMPORTANT", "Notes.IMPORTANT"),   # extension inconnue → intact
    ("IMG.2024.JPG.JPG", "IMG.2024.jpg"),     # doublon en fin de nom fusionné (PO 1a)
    ("sansext", "sansext"),                   # pas d'extension
    (".cache", ".cache"),                     # nom caché → intact
    ("a.b.c.JPG.JPG", "a.b.c.jpg"),           # parties précédentes gardées (PO 1a)
])
def test_nouveau_nom(entree, attendu):
    assert corr.nouveau_nom(entree) == attendu


# ---------------------------------------------------------------------------
# §2 — fusion des doublons identiques, toute extension (réponse PO 2026-11-05)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entree,attendu", [
    ("b.ZIP.ZIP", "b.zip"),
    ("f.csv.csv", "f.csv"),
    ("x.FOO.FOO", "x.foo"),                         # extension inconnue fusionnée
    ("Notes.IMPORTANT.IMPORTANT", "Notes.important"),
    ("a.Foo.FOO.foo", "a.foo"),                     # identiques à la casse près
    ("son.M4A.M4A", "son.m4a"),                     # lettres et chiffres : fusionné
    ("x.v2.V2", "x.v2"),
    ("version.1.1", "version.1.1"),                 # chiffres seuls : jamais fusionné
    ("rapport.2024.2024", "rapport.2024.2024"),
    ("archive.001.001", "archive.001.001"),
    ("a..", "a.."),                                 # parties vides
    ("x.final version.final version", "x.final version.final version"),
    ("x.été.été", "x.été.été"),                     # non ASCII
    ("x.a-b.a-b", "x.a-b.a-b"),                     # ponctuation
    ("IMG.2024.JPG.JPG", "IMG.2024.jpg"),           # doublon en fin de nom (PO 1a)
    ("a.tar.gz.gz", "a.tar.gz"),
    ("x.FOO", "x.FOO"),                             # casse seule hors liste : intact
    ("Notes.IMPORTANT", "Notes.IMPORTANT"),
    (".cache.cache", ".cache.cache"),               # nom caché
])
def test_fusion_toute_extension(entree, attendu):
    assert corr.nouveau_nom(entree) == attendu


NOUVELLES_EXTS = [
    "zip", "rar", "7z", "tar", "gz", "dmg", "iso",
    "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "pages", "numbers", "key", "epub",
    "html", "htm", "csv", "json", "xml", "md",
    "svg", "psd", "avif",
]


def test_liste_elargie_compte():
    assert len(NOUVELLES_EXTS) == 27 and len(set(NOUVELLES_EXTS)) == 27
    assert not set(NOUVELLES_EXTS) & ANCIENNES_EXTS
    assert corr.KNOWN_EXTS == ANCIENNES_EXTS | set(NOUVELLES_EXTS)


ANCIENNES_EXTS = {
    "jpg", "jpeg", "png", "gif", "heic", "heif", "tiff", "tif",
    "bmp", "webp", "raw", "cr2", "nef", "arw", "dng", "orf", "rw2", "srw",
    "mp4", "mov", "avi", "mkv", "m4v", "wmv", "mpg", "mpeg",
    "3gp", "webm", "flv", "m2ts",
    "mp3", "wav", "flac", "aac", "m4a", "ogg",
    "pdf", "doc", "docx", "txt", "rtf",
    "aae",
}


@pytest.mark.parametrize("ext", NOUVELLES_EXTS)
def test_liste_elargie_casse(ext):
    assert corr.nouveau_nom(f"x.{ext.upper()}") == f"x.{ext}"


def test_liste_elargie_casse_derniere_seule():
    assert corr.nouveau_nom("c.XLSX") == "c.xlsx"
    assert corr.nouveau_nom("x.TAR.GZ") == "x.TAR.gz"


def test_fusion_toute_extension_bout_en_bout(tmp_path):
    touch(tmp_path / "x.FOO.FOO", b"un")
    touch(tmp_path / "y.FOO")
    touch(tmp_path / "version.1.1")
    (tmp_path / "album.FOO.FOO").mkdir()
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1
    assert noms(tmp_path) == sorted(["x.foo", "y.FOO", "version.1.1", "album.FOO.FOO"])
    assert (tmp_path / "x.foo").read_bytes() == b"un"
    assert (tmp_path / "album.FOO.FOO").is_dir()
    assert scan_apply(tmp_path)["renommes"] == 0          # idempotence


def test_fusion_toute_extension_conflit_suffixe(tmp_path):
    touch(tmp_path / "x.foo.foo", b"un")
    touch(tmp_path / "x.foo", b"deux")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1
    assert (tmp_path / "x.foo").read_bytes() == b"deux"   # jamais écrasé
    assert (tmp_path / "x_2.foo").read_bytes() == b"un"
    assert len(noms(tmp_path)) == 2


# ---------------------------------------------------------------------------
# §2 — fusion + casse de bout en bout
# ---------------------------------------------------------------------------

def test_fusion_et_casse_end_to_end(tmp_path):
    touch(tmp_path / "photo.JPG.JPG")
    touch(tmp_path / "clip.MP4.MP4.MP4")
    touch(tmp_path / "keep.jpg.png")
    touch(tmp_path / "Notes.IMPORTANT")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 2
    assert noms(tmp_path) == sorted(["photo.jpg", "clip.mp4", "keep.jpg.png", "Notes.IMPORTANT"])


# ---------------------------------------------------------------------------
# §2 — intégrité : hash, mtime_ns, inode, xattr user.* inchangés
# ---------------------------------------------------------------------------

def test_integrite_donnees_et_metadonnees(tmp_path):
    src = touch(tmp_path / "img.JPG", b"\x89PNG\x00exif-payload")
    os.utime(src, ns=(111_000_000_000, 222_000_000_000))
    h_avant = hashlib.sha256(src.read_bytes()).hexdigest()
    ino_avant = os.stat(src).st_ino
    mtime_avant = os.stat(src).st_mtime_ns
    xattr_ok = True
    try:
        os.setxattr(src, b"user.comment", b"finder-tag")
    except OSError:
        xattr_ok = False  # FS de test sans xattr user.* : déclaré non vérifiable ici

    scan_apply(tmp_path)

    cible = tmp_path / "img.jpg"
    assert cible.exists() and not (tmp_path / "img.JPG").exists()
    st = os.stat(cible)
    assert hashlib.sha256(cible.read_bytes()).hexdigest() == h_avant
    assert st.st_ino == ino_avant
    assert st.st_mtime_ns == mtime_avant
    if xattr_ok:
        assert os.getxattr(cible, b"user.comment") == b"finder-tag"


# ---------------------------------------------------------------------------
# §2/§4 — pipeline : appliquée ⊆ figée ; identité par (dev, ino)
# ---------------------------------------------------------------------------

def test_inclusion_appliquee_sous_ensemble_figee(tmp_path):
    touch(tmp_path / "a.JPG")
    touch(tmp_path / "b.PNG")
    modifs, *_ = corr.scanner(tmp_path)
    rels_figes = {m.rel for m in modifs}
    # On fausse l'identité (ino) d'une entrée figée : elle doit s'abstenir, et
    # l'appliqué reste un SOUS-ENSEMBLE strict du figé (jamais d'action hors liste).
    modifs = [m if m.rel != "a.JPG"
              else m._replace(ino=m.ino + 999)
              for m in modifs]
    renommes, ignores, erreurs, _ = corr.appliquer(modifs)
    rels_appliques = {m.rel for m in modifs} - {rel for rel, _ in ignores}
    assert rels_appliques <= rels_figes and rels_appliques < rels_figes
    assert "a.JPG" in {rel for rel, _ in ignores}   # identité changée → abstention
    assert renommes == 1                            # seul b.PNG passe


def test_identite_changee_abstention(tmp_path):
    f = touch(tmp_path / "x.JPG")
    modif = forge(f, "x.jpg", case_safe=False, racine=tmp_path)
    bad = corr.Modif(modif.rel, modif.src, modif.cible, modif.cible_nom,
                     False, modif.dev, modif.ino + 999)   # ino faussé
    renommes, ignores, erreurs, _ = corr.appliquer([bad])
    assert renommes == 0 and ignores and (tmp_path / "x.JPG").exists()


# ---------------------------------------------------------------------------
# §2 — pipeline : dry-run n'applique rien (via main)
# ---------------------------------------------------------------------------

def test_dry_run_naplique_rien(tmp_path, monkeypatch, capsys):
    touch(tmp_path / "a.JPG.JPG")
    monkeypatch.setattr(corr, "choisir_journal", lambda racine: (None, False))
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path), "--dry-run"])
    corr.main()
    assert noms(tmp_path) == ["a.JPG.JPG"]           # rien renommé
    assert "aucune modification" in capsys.readouterr().out.lower()


class _StdinTTY:
    def isatty(self):
        return True


@pytest.mark.parametrize("reponse,renomme", [
    ("", False), ("x", False), ("n", False), ("non", False), ("o", True), ("oui", True),
])
def test_confirmation_defaut_non(tmp_path, monkeypatch, reponse, renomme):
    touch(tmp_path / "a.JPG.JPG")
    monkeypatch.setattr(corr, "choisir_journal", lambda racine: (None, False))
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path)])
    monkeypatch.setattr("sys.stdin", _StdinTTY())
    monkeypatch.setattr("builtins.input", lambda invite="": reponse)
    corr.main()
    assert noms(tmp_path) == (["a.jpg"] if renomme else ["a.JPG.JPG"])


def test_contenu_jamais_ouvert(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    racine.mkdir()
    for nom in ["a.JPG.JPG", "b.ZIP.ZIP", "c.XLSX", "d.jpg", "x.FOO.FOO"]:
        touch(racine / nom)
    journal = tmp_path / "rename_log_test.txt"
    ouverts = []
    vrai_open, vrai_os_open = open, os.open

    def espion_open(f, *a, **k):
        ouverts.append(os.path.abspath(os.fsdecode(f)) if not isinstance(f, int) else f)
        return vrai_open(f, *a, **k)

    def espion_os_open(f, *a, **k):
        ouverts.append(os.path.abspath(os.fsdecode(f)))
        return vrai_os_open(f, *a, **k)

    monkeypatch.setattr("builtins.open", espion_open)
    monkeypatch.setattr("io.open", espion_open)
    monkeypatch.setattr("os.open", espion_os_open)
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (journal, False))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--oui"])
    corr.main()
    assert noms(racine) == sorted(["a.jpg", "b.zip", "c.xlsx", "d.jpg", "x.foo"])
    assert str(journal) in ouverts                       # l'espion voit bien les ouvertures
    sous_racine = [o for o in ouverts if isinstance(o, str) and o.startswith(str(racine) + os.sep)]
    assert sous_racine == []


# ---------------------------------------------------------------------------
# §2/§3 — conflit avec un autre fichier → suffixe, jamais d'écrasement
# ---------------------------------------------------------------------------

def test_conflit_autre_fichier_suffixe(tmp_path):
    touch(tmp_path / "a.JPG", b"un")
    touch(tmp_path / "a.jpg", b"deux")            # cible déjà prise par un AUTRE fichier
    r = scan_apply(tmp_path)
    assert (tmp_path / "a.jpg").read_bytes() == b"deux"    # non écrasé
    assert (tmp_path / "a_2.jpg").read_bytes() == b"un"
    assert r["renommes"] == 1


# ---------------------------------------------------------------------------
# §3 — anti-écrasement atomique : cible apparue entre scan et application
# ---------------------------------------------------------------------------

def test_atomic_cible_apparue_apres_scan(tmp_path):
    touch(tmp_path / "a.JPG", b"source")
    modifs, *_ = corr.scanner(tmp_path)
    touch(tmp_path / "a.jpg", b"apparu")          # apparaît APRÈS le scan
    renommes, ignores, erreurs, _ = corr.appliquer(modifs)
    assert renommes == 0
    assert (tmp_path / "a.jpg").read_bytes() == b"apparu"   # préexistant intact
    assert (tmp_path / "a.JPG").read_bytes() == b"source"
    assert ignores


# ---------------------------------------------------------------------------
# §3/§4 — liens symboliques occupant le nom cible → abstention, rien détruit
# ---------------------------------------------------------------------------

def test_symlink_vivant_sur_cible_abstention(tmp_path):
    touch(tmp_path / "A.JPG", b"reel")
    (tmp_path / "A.jpg").symlink_to(tmp_path / "A.JPG")
    avant = len(os.listdir(tmp_path))
    r = scan_apply(tmp_path)
    assert r["renommes"] == 0
    assert len(os.listdir(tmp_path)) == avant
    assert (tmp_path / "A.JPG").exists() and (tmp_path / "A.jpg").is_symlink()


def test_symlink_casse_sur_cible_abstention(tmp_path):
    touch(tmp_path / "x.JPG", b"reel")
    (tmp_path / "x.jpg").symlink_to(tmp_path / "nowhere-absent")
    avant = len(os.listdir(tmp_path))
    r = scan_apply(tmp_path)
    assert r["renommes"] == 0
    assert len(os.listdir(tmp_path)) == avant
    assert (tmp_path / "x.JPG").exists() and os.path.islink(tmp_path / "x.jpg")


# ---------------------------------------------------------------------------
# §4/§5 — liens durs de même inode → abstention, aucun __rename_tmp_*
# ---------------------------------------------------------------------------

def test_liens_durs_abstention(tmp_path):
    touch(tmp_path / "a.jpg", b"contenu")
    os.link(tmp_path / "a.jpg", tmp_path / "a.JPG")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 0
    assert (tmp_path / "a.jpg").exists() and (tmp_path / "a.JPG").exists()
    assert not [n for n in os.listdir(tmp_path) if n.startswith(corr.PREFIXE_TMP)]


# ---------------------------------------------------------------------------
# §5 — rollback : 2e étape en OSError → état restauré, aucun temp
# ---------------------------------------------------------------------------

def test_rollback_oserror(tmp_path, monkeypatch):
    f = touch(tmp_path / "a.JPG", b"DATA")
    modif = forge(f, "a.jpg", case_safe=True, racine=tmp_path)
    reel = corr._rename_no_overwrite
    calls = {"n": 0}

    def faux(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(errno.EACCES, "boom")
        return reel(src, dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", faux)
    renommes, ignores, erreurs, _ = corr.appliquer([modif])
    assert renommes == 0 and erreurs
    assert (tmp_path / "a.JPG").read_bytes() == b"DATA"
    assert not [n for n in os.listdir(tmp_path) if n.startswith(corr.PREFIXE_TMP)]


# ---------------------------------------------------------------------------
# §5 — rollback élargi : interruption (BaseException) → restauré + remonte
# ---------------------------------------------------------------------------

def test_rollback_keyboardinterrupt(tmp_path, monkeypatch):
    f = touch(tmp_path / "a.JPG", b"DATA")
    modif = forge(f, "a.jpg", case_safe=True, racine=tmp_path)
    reel = corr._rename_no_overwrite
    calls = {"n": 0}

    def faux(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return reel(src, dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", faux)
    with pytest.raises(KeyboardInterrupt):
        corr.appliquer([modif])
    assert (tmp_path / "a.JPG").read_bytes() == b"DATA"
    assert not (tmp_path / "a.jpg").exists()
    assert not [n for n in os.listdir(tmp_path) if n.startswith(corr.PREFIXE_TMP)]


# ---------------------------------------------------------------------------
# §5 — orphelin d'un run interrompu : signalé, jamais renommé
# ---------------------------------------------------------------------------

def test_orphelin_signale(tmp_path):
    touch(tmp_path / f"{corr.PREFIXE_TMP}a.jpg", b"orphelin")
    touch(tmp_path / "b.JPG")
    modifs, deja_ok, err, orphelins = corr.scanner(tmp_path)
    assert any("a.jpg" in o for o in orphelins)
    assert {m.rel for m in modifs} == {"b.JPG"}          # l'orphelin n'est pas une cible
    corr.appliquer(modifs)
    assert (tmp_path / f"{corr.PREFIXE_TMP}a.jpg").exists()   # jamais touché


# ---------------------------------------------------------------------------
# §3/§4/§5 — repli non atomique : renommages faits + avertissement journalisé
# ---------------------------------------------------------------------------

def test_repli_non_atomique_avertissement(tmp_path, monkeypatch):
    monkeypatch.setenv("CORREXT_FORCE_NON_ATOMIC", "1")
    touch(tmp_path / "a.JPG.JPG")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1 and r["repli"] is True
    assert (tmp_path / "a.jpg").exists()
    journal = tmp_path.parent / "log.txt"
    corr.ecrire_journal_prevu(journal, tmp_path, r["modifs"], 0, [], [])
    corr.ajouter_resultats(journal, r["renommes"], r["ignores"], r["erreurs"], r["repli"])
    assert "atomique" in journal.read_text()


# ---------------------------------------------------------------------------
# §5 — idempotence, absence de perte, dossiers non renommés, noms exotiques
# ---------------------------------------------------------------------------

def test_idempotence(tmp_path):
    touch(tmp_path / "a.JPG.JPG")
    scan_apply(tmp_path)
    r2 = scan_apply(tmp_path)
    assert r2["renommes"] == 0


def test_aucune_perte_de_fichier(tmp_path):
    for i in range(20):
        touch(tmp_path / f"f{i}.JPG")
        touch(tmp_path / f"g{i}.jpg.jpg")
    avant = len(os.listdir(tmp_path))
    scan_apply(tmp_path)
    assert len(os.listdir(tmp_path)) >= avant


def test_dossier_jamais_renomme(tmp_path):
    (tmp_path / "album.JPG").mkdir()
    touch(tmp_path / "photo.JPG")
    scan_apply(tmp_path)
    assert (tmp_path / "album.JPG").is_dir()          # dossier intact
    assert (tmp_path / "photo.jpg").exists()


def test_noms_exotiques_sans_crash(tmp_path):
    for nom in ["éclair.JPG.JPG", "deux mots.PNG", "a.b.c.JPG.JPG",
                "sansext", "court.z", "long." + "x" * 40]:
        touch(tmp_path / nom)
    scan_apply(tmp_path)                                # ne doit pas lever
    assert (tmp_path / "éclair.jpg").exists()
    assert (tmp_path / "deux mots.png").exists()


# ---------------------------------------------------------------------------
# §3 — refus des racines protégées (système, paquet macOS, Library)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chemin", [
    "/", "/System", "/usr/local",
    "/Volumes/A/Photos.photoslibrary", "/Volumes/A/X.app", "/Volumes/A/Y.pages",
    "/Users/moi/Library", "/data/.Trash",
])
def test_racine_interdite(chemin):
    assert corr.est_racine_interdite(Path(chemin)) is True


@pytest.mark.parametrize("chemin", [
    "/Volumes/Archive", "/Users/moi/Pictures", "/data/photos",
    "/Users/moi/Library/Mobile Documents/com~apple~CloudDocs",   # sous Library : accepté (question au PO)
])
def test_racine_autorisee(chemin):
    assert corr.est_racine_interdite(Path(chemin)) is False


# ---------------------------------------------------------------------------
# §3/§4 — journal hors volume, jamais sous la racine, même liste que l'aperçu
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.isdir("/dev/shm"), reason="exige /dev/shm (volume distinct)")
def test_journal_hors_volume(tmp_path):
    racine = Path("/dev/shm") / f"corrext_test_{os.getpid()}"
    racine.mkdir(parents=True, exist_ok=True)
    try:
        for i in range(5):
            touch(racine / f"f{i}.JPG.JPG")
        modifs, deja_ok, err, orph = corr.scanner(racine)
        journal, meme_volume = corr.choisir_journal(racine)
        assert journal is not None
        corr.ecrire_journal_prevu(journal, racine, modifs, deja_ok, err, orph)
        try:
            assert journal.stat().st_dev != racine.stat().st_dev   # autre volume
            assert meme_volume is False
            assert racine not in journal.parents                    # jamais sous la racine
            contenu = journal.read_text()
            assert "À CORRIGER — 5 fichier(s)" in contenu
            assert len(modifs) == 5
        finally:
            journal.unlink(missing_ok=True)
    finally:
        for p in racine.iterdir():
            p.unlink()
        racine.rmdir()


# ---------------------------------------------------------------------------
# §5 — sans journal possible, l'affichage est intégral (jamais tronqué)
# ---------------------------------------------------------------------------

def test_affichage_integral_sans_journal(capsys):
    modifs = [corr.Modif(f"f{i}.JPG", f"/x/f{i}.JPG", f"/x/f{i}.jpg", f"f{i}.jpg",
                         False, 1, i) for i in range(300)]
    corr.afficher_apercu(Path("/x"), modifs, 0, [], [], journal=None,
                         meme_volume=False, tout=False)
    out = capsys.readouterr().out
    assert out.count("→ ") == 300                       # les 300 lignes, aucune troncature
    assert "non affichés" not in out
    assert "journal ci-dessus" not in out


# ---------------------------------------------------------------------------
# §3 — macOS : renamex_np reçoit RENAME_EXCL (0x4), jamais RENAME_SWAP (0x2)
# Valeurs : xnu bsd/sys/stdio.h (RENAME_SWAP 0x00000002, RENAME_EXCL 0x00000004).
# ---------------------------------------------------------------------------

class _FauxLibSystem:
    RENAME_EXCL = 0x00000004

    def __init__(self):
        self.drapeaux = []

    def renamex_np(self, src, dst, drapeaux):
        self.drapeaux.append(drapeaux)
        if drapeaux != self.RENAME_EXCL:
            ctypes.set_errno(errno.ENOENT)              # RENAME_SWAP exige une cible existante
            return -1
        if os.path.lexists(os.fsdecode(dst)):
            ctypes.set_errno(errno.EEXIST)
            return -1
        os.rename(os.fsdecode(src), os.fsdecode(dst))
        return 0


def test_macos_renamex_np_rename_excl(tmp_path, monkeypatch):
    libc = _FauxLibSystem()
    monkeypatch.setattr(corr, "_LIBC", libc)
    monkeypatch.setattr(corr.sys, "platform", "darwin")
    touch(tmp_path / "a.JPG.JPG", b"un")
    touch(tmp_path / "b.ZIP.ZIP", b"deux")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 2 and r["erreurs"] == [] and r["repli"] is False
    assert noms(tmp_path) == ["a.jpg", "b.zip"]
    assert libc.drapeaux == [0x4, 0x4]


def test_macos_cible_apparue_jamais_echangee(tmp_path, monkeypatch):
    monkeypatch.setattr(corr, "_LIBC", _FauxLibSystem())
    monkeypatch.setattr(corr.sys, "platform", "darwin")
    touch(tmp_path / "a.JPG.JPG", b"source")
    modifs = corr.scanner(tmp_path)[0]
    touch(tmp_path / "a.jpg", b"preexistant")
    renommes, ignores, erreurs, _ = corr.appliquer(modifs)
    assert renommes == 0 and len(ignores) == 1
    assert (tmp_path / "a.jpg").read_bytes() == b"preexistant"
    assert (tmp_path / "a.JPG.JPG").read_bytes() == b"source"


# ---------------------------------------------------------------------------
# §3 — pas de descente dans les paquets macOS, Library, corbeilles
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dossier", [
    "X.app", "P.photoslibrary", "Y.pages", "Library", ".Trash", ".Trashes", "Z.APP",
    "iPhoto Library.photolibrary", "old.migratedphotolibrary", "$RECYCLE.BIN", "$Recycle.Bin",
])
def test_pas_de_descente_dans_zones_protegees(tmp_path, dossier):
    (tmp_path / dossier).mkdir()
    touch(tmp_path / dossier / "a.JPG.JPG")
    touch(tmp_path / "b.JPG.JPG")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1
    assert noms(tmp_path / dossier) == ["a.JPG.JPG"]
    assert (tmp_path / "b.jpg").exists()


# ---------------------------------------------------------------------------
# §3 — journal jamais sous la racine scannée (cwd et home sous la racine)
# ---------------------------------------------------------------------------

def test_journal_jamais_sous_racine_cwd_dedans(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    (racine / "sous").mkdir(parents=True)
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    monkeypatch.chdir(racine / "sous")
    monkeypatch.setenv("HOME", str(racine))
    monkeypatch.setattr(corr.tempfile, "tempdir", str(ailleurs))
    journal, _ = corr.choisir_journal(racine.resolve())
    assert journal is not None and journal.parent == ailleurs.resolve()
    assert os.listdir(racine) == ["sous"] and os.listdir(racine / "sous") == []


def test_journal_absent_si_tout_sous_racine(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    (racine / "sous").mkdir(parents=True)
    monkeypatch.chdir(racine / "sous")
    monkeypatch.setenv("HOME", str(racine))
    monkeypatch.setattr(corr.tempfile, "tempdir", str(racine / "sous"))
    assert corr.choisir_journal(racine.resolve()) == (None, False)
    assert os.listdir(racine) == ["sous"] and os.listdir(racine / "sous") == []


# ---------------------------------------------------------------------------
# §3 — repli non atomique : une cible apparue après le scan n'est jamais écrasée
# ---------------------------------------------------------------------------

def test_repli_cible_apparue_jamais_ecrasee(tmp_path, monkeypatch):
    monkeypatch.setenv("CORREXT_FORCE_NON_ATOMIC", "1")
    touch(tmp_path / "a.JPG.JPG", b"source")
    modifs = corr.scanner(tmp_path)[0]
    touch(tmp_path / "a.jpg", b"preexistant")
    renommes, ignores, _, _ = corr.appliquer(modifs)
    assert renommes == 0 and len(ignores) == 1
    assert (tmp_path / "a.jpg").read_bytes() == b"preexistant"
    assert (tmp_path / "a.JPG.JPG").read_bytes() == b"source"


# ---------------------------------------------------------------------------
# §2/§3 — deux fichiers du même lot visent le même nom → suffixe, aucune perte
# ---------------------------------------------------------------------------

def test_conflit_dans_le_lot(tmp_path):
    touch(tmp_path / "a.JPG.JPG", b"un")
    touch(tmp_path / "a.jpg.jpg", b"deux")
    touch(tmp_path / "x.FOO.FOO", b"trois")
    touch(tmp_path / "x.foo.foo", b"quatre")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 4
    assert noms(tmp_path) == ["a.jpg", "a_2.jpg", "x.foo", "x_2.foo"]
    contenus = sorted((tmp_path / n).read_bytes() for n in noms(tmp_path))
    assert contenus == sorted([b"un", b"deux", b"trois", b"quatre"])


# ---------------------------------------------------------------------------
# §3 — renommage de casse : un nom temporaire déjà pris n'est jamais écrasé
# ---------------------------------------------------------------------------

def test_temp_deja_pris_jamais_ecrase(tmp_path):
    src = touch(tmp_path / "a.JPG", b"photo")
    touch(tmp_path / f"{corr.PREFIXE_TMP}a.jpg", b"orphelin")
    m = forge(src, "a.jpg", True, tmp_path)
    renommes, _, erreurs, _ = corr.appliquer([m])
    assert renommes == 1 and erreurs == []
    assert (tmp_path / "a.jpg").read_bytes() == b"photo"
    assert (tmp_path / f"{corr.PREFIXE_TMP}a.jpg").read_bytes() == b"orphelin"
    assert len(noms(tmp_path)) == 2


# ---------------------------------------------------------------------------
# §2 pipeline — Ctrl-C pendant l'application : journal complété, sortie propre
# ---------------------------------------------------------------------------

def test_interruption_application_journal(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    racine.mkdir()
    for i in range(5):
        touch(racine / f"f{i}.JPG")
    journal = tmp_path / "rename_log_test.txt"
    vrai = corr._rename_no_overwrite
    appels = []

    def coupe_au_troisieme(src, dst):
        appels.append(src)
        if len(appels) == 3:
            raise KeyboardInterrupt
        return vrai(src, dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", coupe_au_troisieme)
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (journal, False))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--oui"])
    with pytest.raises(SystemExit) as fin:
        corr.main()
    assert fin.value.code == 130
    assert noms(racine) == ["f0.jpg", "f1.jpg", "f2.JPG", "f3.JPG", "f4.JPG"]
    texte = journal.read_text(encoding="utf-8")
    assert "INTERROMPU" in texte and "2 fichier(s) traité(s) sur 5" in texte
    assert "Renommés avec succès : 2" in texte
    assert "Interrompu" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# §3 — refus net au niveau programme : code de sortie non nul, aucune action
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sous_chemin", [
    "X.app", "P.photoslibrary/originals", "Library", ".Trash/vieux", "$RECYCLE.BIN/S-1-5",
    "iPhoto Library.photolibrary/Masters",
])
def test_main_refuse_racine_protegee(tmp_path, monkeypatch, sous_chemin):
    racine = tmp_path / sous_chemin
    racine.mkdir(parents=True)
    touch(racine / "a.JPG.JPG")
    monkeypatch.setattr(corr, "choisir_journal", lambda r: pytest.fail("aucun journal attendu"))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--oui"])
    with pytest.raises(SystemExit) as fin:
        corr.main()
    assert fin.value.code != 0
    assert noms(racine) == ["a.JPG.JPG"]


def test_main_refuse_racine_inexistante(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path / "absent"), "--oui"])
    with pytest.raises(SystemExit) as fin:
        corr.main()
    assert fin.value.code != 0
    assert not (tmp_path / "absent").exists()


# ---------------------------------------------------------------------------
# §3 — journal écrit AVANT toute modification, --dry-run compris, même liste que l'aperçu
# ---------------------------------------------------------------------------

def _lignes_apercu(sortie: str):
    lignes = sortie.split("Renommages prévus :", 1)[1].splitlines()
    return [l.strip() for l in lignes if l.startswith("  ") and l.strip()]


def test_journal_dry_run_meme_liste_que_apercu(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    racine.mkdir()
    for nom in ["a.JPG.JPG", "b.ZIP.ZIP", "c.XLSX", "d.jpg", "x.FOO.FOO"]:
        touch(racine / nom)
    journal = tmp_path / "rename_log_test.txt"
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (journal, False))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--dry-run"])
    corr.main()
    apercu = _lignes_apercu(capsys.readouterr().out)
    texte = journal.read_text(encoding="utf-8")
    section = texte.split("À CORRIGER", 1)[1].split("DÉJÀ CORRECTS", 1)[0]
    entrees = [l.strip() for l in section.splitlines()[2:] if l.strip()]
    assert entrees == apercu
    assert apercu == ["a.JPG.JPG", "→ a.jpg", "b.ZIP.ZIP", "→ b.zip", "c.XLSX", "→ c.xlsx",
                      "x.FOO.FOO", "→ x.foo"]
    assert noms(racine) == sorted(["a.JPG.JPG", "b.ZIP.ZIP", "c.XLSX", "d.jpg", "x.FOO.FOO"])


def test_journal_ecrit_avant_premier_renommage(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    racine.mkdir()
    touch(racine / "a.JPG.JPG")
    touch(racine / "b.ZIP.ZIP")
    journal = tmp_path / "rename_log_test.txt"
    vrai = corr._rename_no_overwrite
    vus = []

    def espion(src, dst):
        vus.append(journal.read_text(encoding="utf-8") if journal.exists() else None)
        return vrai(src, dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", espion)
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (journal, False))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--oui"])
    corr.main()
    assert len(vus) == 2
    assert vus[0] is not None and "a.JPG.JPG" in vus[0] and "b.ZIP.ZIP" in vus[0]
    assert "RÉSULTATS" not in vus[0]


# ---------------------------------------------------------------------------
# §5 — orphelin d'un run interrompu signalé à l'écran ET dans le journal
# ---------------------------------------------------------------------------

def test_orphelin_signale_ecran_et_journal(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    racine.mkdir()
    orphelin = f"{corr.PREFIXE_TMP}a.jpg"
    touch(racine / orphelin, b"orphelin")
    touch(racine / "b.JPG")
    journal = tmp_path / "rename_log_test.txt"
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (journal, False))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--oui"])
    corr.main()
    assert orphelin in capsys.readouterr().out
    assert orphelin in journal.read_text(encoding="utf-8").split("ORPHELINS", 1)[1]
    assert (racine / orphelin).read_bytes() == b"orphelin"


# ---------------------------------------------------------------------------
# §2 pipeline — entrée non interactive sans --oui : aucune écriture
# ---------------------------------------------------------------------------

class _StdinPasTTY:
    def isatty(self):
        return False


def test_non_interactif_sans_oui_naplique_rien(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")
    monkeypatch.setattr(corr, "choisir_journal", lambda racine: (None, False))
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path)])
    monkeypatch.setattr("sys.stdin", _StdinPasTTY())
    monkeypatch.setattr("builtins.input", lambda invite="": pytest.fail("aucune invite attendue"))
    corr.main()
    assert noms(tmp_path) == ["a.JPG.JPG"]


# ---------------------------------------------------------------------------
# §3 — choisir le journal ne tronque ni ne supprime jamais un fichier existant
# ---------------------------------------------------------------------------

def test_choisir_journal_ne_detruit_pas_un_homonyme(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    racine.mkdir()
    ici = tmp_path / "ici"
    ici.mkdir()
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()

    class _Fige(corr.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 2, 3, 4, 5)

    monkeypatch.setattr(corr, "datetime", _Fige)
    homonyme = ici / "rename_log_2026-01-02_03-04-05.txt"
    homonyme.write_text("journal précédent")
    monkeypatch.chdir(ici)
    monkeypatch.setenv("HOME", str(ailleurs))
    monkeypatch.setattr(corr.tempfile, "tempdir", str(ailleurs))
    journal, _ = corr.choisir_journal(racine.resolve())
    assert homonyme.read_text() == "journal précédent"
    assert journal is not None and journal != homonyme.resolve()


# ---------------------------------------------------------------------------
# §3 — racine protégée reconnue quelle que soit la casse tapée (APFS insensible)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chemin", [
    "/library", "/system", "/applications", "/USR/local", "/Private/var",
    "/Users/x/library", "/Users/x/.trash/vieux", "/Volumes/A/Photos.PHOTOSLIBRARY/originals",
    "/Volumes/A/$recycle.bin",
])
def test_racine_interdite_sans_casse(chemin):
    assert corr.est_racine_interdite(Path(chemin)) is True


# ---------------------------------------------------------------------------
# §3 — journal jamais sous la racine, même désignée par un autre chemin
# (casse différente sur APFS ; ici, un lien symbolique vers la racine)
# ---------------------------------------------------------------------------

def test_journal_jamais_sous_racine_autre_chemin(tmp_path, monkeypatch):
    racine = tmp_path / "Archive"
    (racine / "sous").mkdir(parents=True)
    alias = tmp_path / "archive-alias"
    alias.symlink_to(racine)
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    monkeypatch.chdir(racine / "sous")
    monkeypatch.setenv("HOME", str(ailleurs))
    monkeypatch.setattr(corr.tempfile, "tempdir", str(ailleurs))
    journal, _ = corr.choisir_journal(alias)
    assert journal is not None and journal.parent == ailleurs.resolve()
    assert os.listdir(racine / "sous") == []


# ---------------------------------------------------------------------------
# §2 — renommage de casse d'un nom long (243 à 255 octets) : le nom temporaire
# ne doit pas dépasser la limite du système de fichiers
# ---------------------------------------------------------------------------

def test_casse_nom_long(tmp_path):
    nom = "é" * 120 + ".JPG"                              # 244 octets
    src = touch(tmp_path / nom, b"photo")
    m = forge(src, "é" * 120 + ".jpg", True, tmp_path)
    renommes, _, erreurs, _ = corr.appliquer([m])
    assert erreurs == [] and renommes == 1
    assert noms(tmp_path) == ["é" * 120 + ".jpg"]
    assert (tmp_path / ("é" * 120 + ".jpg")).read_bytes() == b"photo"


# ---------------------------------------------------------------------------
# §3 — un vrai signal d'arrêt reçu entre les deux étapes d'un renommage de casse
# est différé : le fichier finit son renommage, aucun __rename_tmp_* ne survit
# ---------------------------------------------------------------------------

def test_sigint_entre_les_etapes_aucun_orphelin(tmp_path, monkeypatch):
    a = touch(tmp_path / "a.JPG", b"un")
    b = touch(tmp_path / "b.JPG", b"deux")
    modifs = [forge(a, "a.jpg", True, tmp_path), forge(b, "b.jpg", True, tmp_path)]
    vrai = corr._rename_no_overwrite
    appels = []

    def signal_apres_etape_1(src, dst):
        r = vrai(src, dst)
        appels.append(dst)
        if len(appels) == 1:
            os.kill(os.getpid(), signal.SIGINT)
        return r

    monkeypatch.setattr(corr, "_rename_no_overwrite", signal_apres_etape_1)
    with pytest.raises(corr.Interrompu) as interruption:
        corr.appliquer(modifs)
    assert noms(tmp_path) == ["a.jpg", "b.JPG"]
    assert (tmp_path / "a.jpg").read_bytes() == b"un"
    assert interruption.value.traites == 1 and interruption.value.resultats[0] == 1


def test_sigterm_entre_les_etapes_aucun_orphelin(tmp_path):
    a = touch(tmp_path / "a.JPG", b"un")
    touch(tmp_path / "b.JPG", b"deux")
    script = f"""
import os, signal, sys
sys.path.insert(0, {str(Path(corr.__file__).parent)!r})
import corriger_extensions as corr
from pathlib import Path
racine = Path({str(tmp_path)!r})
modifs = []
for nom in ("a.JPG", "b.JPG"):
    st = os.stat(racine / nom)
    modifs.append(corr.Modif(nom, str(racine / nom), str(racine / nom.lower()), nom.lower(),
                             True, st.st_dev, st.st_ino))
vrai = corr._rename_no_overwrite
appels = []
def coupe(src, dst):
    r = vrai(src, dst)
    appels.append(dst)
    if len(appels) == 1:
        os.kill(os.getpid(), signal.SIGTERM)
    return r
corr._rename_no_overwrite = coupe
corr.appliquer(modifs)
"""
    import subprocess
    r = subprocess.run([sys.executable, "-c", script], capture_output=True)
    assert r.returncode == -signal.SIGTERM
    assert noms(tmp_path) == ["a.jpg", "b.JPG"]
    assert a.with_name("a.jpg").read_bytes() == b"un"


# ---------------------------------------------------------------------------
# Dossiers illisibles : jamais de « Rien à faire » qui laisserait croire que tout a été examiné
# ---------------------------------------------------------------------------

def _scanner_avec_dossier_illisible(vrai):
    def scanner(racine):
        modifs, deja_ok, erreurs_acces, orphelins = vrai(racine)
        return modifs, deja_ok, erreurs_acces + ["[Errno 13] Permission denied: 'verrouille'"], orphelins
    return scanner


@pytest.mark.parametrize("fichiers,attendu_renommes", [([], 0), (["a.JPG.JPG"], 1)])
def test_dossiers_illisibles_annonces(tmp_path, monkeypatch, capsys, fichiers, attendu_renommes):
    for nom in fichiers:
        touch(tmp_path / nom)
    monkeypatch.setattr(corr, "scanner", _scanner_avec_dossier_illisible(corr.scanner))
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (None, False))
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path), "--oui"])
    corr.main()
    sortie = capsys.readouterr().out
    assert "Rien à faire" not in sortie
    fin = sortie.rsplit("Renommages prévus", 1)[-1]
    assert "1 dossier(s) n'ont pas pu être lus" in fin
    assert noms(tmp_path) == (["a.jpg"] if attendu_renommes else [])


# ---------------------------------------------------------------------------
# Nom mal encodé (octets non UTF-8) : affiché et journalisé échappé, renommé, aucun plantage
# ---------------------------------------------------------------------------

def test_nom_non_utf8(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    racine.mkdir()
    fd = os.open(os.fsencode(racine) + b"/caf\xe9.JPG.JPG", os.O_CREAT | os.O_WRONLY, 0o644)
    os.write(fd, b"photo")
    os.close(fd)
    touch(racine / "b.ZIP.ZIP")
    journal = tmp_path / "rename_log_test.txt"
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (journal, False))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--oui"])
    corr.main()
    assert sorted(os.listdir(os.fsencode(racine))) == [b"b.zip", b"caf\xe9.jpg"]
    assert "caf\\udce9.JPG.JPG" in capsys.readouterr().out
    assert "caf\\udce9.JPG.JPG" in journal.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# §2 — fusion du doublon en fin de nom (réponse PO 1a) et .jpeg gardé en .jpg (2b)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entree,attendu", [
    ("IMG.2024.JPG.JPG", "IMG.2024.jpg"),
    ("Vacances.2024.JPG.JPG", "Vacances.2024.jpg"),
    ("Scan 12.5.PDF.PDF", "Scan 12.5.pdf"),
    ("M. Dupont.JPG.JPG", "M. Dupont.jpg"),
    ("a.b.c.JPG.JPG", "a.b.c.jpg"),
    ("a.tar.gz.gz", "a.tar.gz"),
    ("IMG.2024.JPG.jpg", "IMG.2024.jpg"),            # sortie de la v4.1.0 reprise
    ("photo.png.jpeg.jpg", "photo.png.jpg"),
    ("a.JPG.x.JPG.JPG", "a.JPG.x.jpg"),
    ("rapport.v2.FOO.FOO", "rapport.v2.foo"),
    ("photo.jpg.png", "photo.jpg.png"),
    ("x.v2.1.1", "x.v2.1.1"),                        # suite finale de chiffres
    ("x.2024.2024.JPG", "x.2024.2024.jpg"),
    ("x.a b.a b", "x.a b.a b"),
    ("x.y.été.été", "x.y.été.été"),
])
def test_fusion_doublon_fin_de_nom(entree, attendu):
    assert corr.nouveau_nom(entree) == attendu
    assert corr.nouveau_nom(attendu) == attendu       # idempotent


@pytest.mark.parametrize("entree,attendu", [("photo.jpeg", "photo.jpg"), ("X.JPEG", "X.jpg")])
def test_jpeg_seul_devient_jpg(entree, attendu):
    assert corr.nouveau_nom(entree) == attendu


def test_jpeg_vers_jpg_jamais_ecrase(tmp_path):
    touch(tmp_path / "photo.jpeg", b"jpeg")
    touch(tmp_path / "photo.jpg", b"jpg")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1
    assert (tmp_path / "photo.jpg").read_bytes() == b"jpg"
    assert (tmp_path / "photo_2.jpg").read_bytes() == b"jpeg"


def test_doublon_fin_de_nom_bout_en_bout(tmp_path):
    (tmp_path / "2024").mkdir()
    touch(tmp_path / "2024" / "IMG.2024.JPG.JPG", b"un")
    touch(tmp_path / "Scan 12.5.PDF.PDF", b"deux")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 2
    assert noms(tmp_path / "2024") == ["IMG.2024.jpg"]
    assert (tmp_path / "Scan 12.5.pdf").read_bytes() == b"deux"
    assert scan_apply(tmp_path)["renommes"] == 0

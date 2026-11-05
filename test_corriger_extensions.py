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
    assert renommes == 0 and ignores == [("x.JPG", "source remplacée depuis le scan")]
    assert (tmp_path / "x.JPG").exists()
    autre_disque = corr.Modif(modif.rel, modif.src, modif.cible, modif.cible_nom,
                              False, modif.dev + 1, modif.ino)   # même inode, autre disque
    renommes, ignores, _, _ = corr.appliquer([autre_disque])
    assert renommes == 0 and ignores == [("x.JPG", "source remplacée depuis le scan")]


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
    "/Volumes/A/$recycle.bin", "/Volumes/A/.Trashes/501", "/Volumes/A/.TRASH",
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
    def scanner(racine, laisses=None):
        modifs, deja_ok, erreurs_acces, orphelins = vrai(racine, laisses)
        return modifs, deja_ok, erreurs_acces + ["[Errno 13] Permission denied: 'verrouille'"], orphelins
    return scanner


@pytest.mark.parametrize("fichiers,attendu_renommes", [([], 0), (["a.JPG.JPG"], 1)])
def test_dossiers_illisibles_annonces(tmp_path, monkeypatch, capsys, fichiers, attendu_renommes):
    for nom in fichiers:
        touch(tmp_path / nom)
    monkeypatch.setattr(corr, "scanner", _scanner_avec_dossier_illisible(corr.scanner))
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (None, False))
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path), "--oui"])
    assert corr.main() == 1                               # dossier illisible : code de sortie 1
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


# ---------------------------------------------------------------------------
# §2 — date d'origine des dossiers touchés remise (réponse PO 3a)
# ---------------------------------------------------------------------------

def _dater(chemin, secondes):
    os.utime(chemin, ns=(secondes * 1_000_000_000, secondes * 1_000_000_000))


def test_date_des_dossiers_remise(tmp_path):
    (tmp_path / "album").mkdir()
    touch(tmp_path / "album" / "a.JPG.JPG")
    touch(tmp_path / "b.ZIP.ZIP")
    _dater(tmp_path / "album", 1_546_300_800)          # 2019-01-01
    _dater(tmp_path, 1_546_300_801)
    r = scan_apply(tmp_path)
    assert r["renommes"] == 2 and r["erreurs"] == []
    assert os.stat(tmp_path / "album").st_mtime_ns == 1_546_300_800 * 1_000_000_000
    assert os.stat(tmp_path).st_mtime_ns == 1_546_300_801 * 1_000_000_000


def test_date_des_dossiers_remise_apres_interruption(tmp_path, monkeypatch):
    for i in range(3):
        touch(tmp_path / f"f{i}.JPG")
    _dater(tmp_path, 1_546_300_800)
    modifs = corr.scanner(tmp_path)[0]
    vrai = corr._rename_no_overwrite
    appels = []

    def coupe(src, dst):
        appels.append(src)
        if len(appels) == 2:
            raise KeyboardInterrupt
        return vrai(src, dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", coupe)
    with pytest.raises(corr.Interrompu):
        corr.appliquer(modifs)
    assert noms(tmp_path) == ["f0.jpg", "f1.JPG", "f2.JPG"]
    assert os.stat(tmp_path).st_mtime_ns == 1_546_300_800 * 1_000_000_000


def test_date_non_remise_signalee(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")

    def refuse(*a, **k):
        raise PermissionError(errno.EPERM, "refusé")

    monkeypatch.setattr(corr.os, "utime", refuse)
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1
    assert len(r["erreurs"]) == 1 and "date du dossier non remise" in r["erreurs"][0][1]


# ---------------------------------------------------------------------------
# §2 — compagnons et liens signalés, jamais renommés (réponse PO 7a)
# ---------------------------------------------------------------------------

def _lancer_main(racine, journal, monkeypatch, *options):
    monkeypatch.setattr(corr, "choisir_journal", lambda r: (journal, False))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), *options])
    return corr.main()


def test_compagnons_et_liens_signales(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    racine.mkdir()
    touch(racine / "IMG.JPG.JPG", b"photo")
    touch(racine / "IMG.JPG.JPG.xmp", b"darktable")
    touch(racine / "IMG.JPG.xmp", b"lightroom")
    (racine / "raccourci").symlink_to(racine / "IMG.JPG.JPG")
    touch(racine / "b.JPG")
    touch(racine / "b.JPG.xmp", b"b")
    touch(racine / "b.xmp", b"radical inchange")
    journal = tmp_path / "rename_log_test.txt"
    assert _lancer_main(racine, journal, monkeypatch, "--oui") == 0
    sortie = capsys.readouterr().out
    texte = journal.read_text(encoding="utf-8")
    section = texte.split("COMPAGNONS ET LIENS", 1)[1].split("\n\n", 1)[0]
    for attendu in ["IMG.JPG.JPG.xmp → vise IMG.JPG.JPG", "IMG.JPG.xmp → vise IMG.JPG.JPG",
                    "raccourci → vise IMG.JPG.JPG", "b.JPG.xmp → vise b.JPG"]:
        assert attendu in section and attendu in sortie
    assert "b.xmp →" not in section                       # casse seule : le radical ne change pas
    assert ("IMG.JPG.xmp → vise IMG.JPG.JPG (compagnon Lightroom (même radical))\n"
            in section + "\n")
    assert sorted(n for n in os.listdir(racine)) == sorted(
        ["IMG.jpg", "IMG.JPG.JPG.xmp", "IMG.JPG.xmp", "raccourci", "b.jpg", "b.JPG.xmp", "b.xmp"])
    assert os.path.islink(racine / "raccourci")


# ---------------------------------------------------------------------------
# §2 — abandons comptés et listés (réponse PO 8a)
# ---------------------------------------------------------------------------

def _arbre_laisses(racine):
    racine.mkdir()
    ailleurs = racine.parent / "ailleurs"
    ailleurs.mkdir()
    touch(ailleurs / "o.JPG.JPG")
    (racine / "lien-dossier").symlink_to(ailleurs)
    (racine / "L.JPG.JPG").symlink_to(ailleurs / "o.JPG.JPG")
    for d in ["Library", ".cache", "X.app", "$RECYCLE.BIN"]:
        (racine / d).mkdir()
        touch(racine / d / "dedans.JPG.JPG")
    touch(racine / "rename_log_ancien.txt")
    touch(racine / "x.JPG")
    (racine / "x.jpg").symlink_to(racine / "nulle-part")
    touch(racine / "ok.ZIP.ZIP")
    return {
        "lien-dossier": corr.RAISON_LIEN, "L.JPG.JPG": corr.RAISON_LIEN,
        "x.jpg": corr.RAISON_LIEN, "Library": "dossier Library ou corbeille",
        "$RECYCLE.BIN": "dossier Library ou corbeille", "X.app": "paquet macOS",
        ".cache": "dossier caché", "rename_log_ancien.txt": corr.RAISON_JOURNAL,
        "x.JPG": corr.RAISON_CIBLE_LIEN,
    }


def test_laisses_de_cote_comptes_et_listes(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    attendus = _arbre_laisses(racine)
    journal = tmp_path / "rename_log_test.txt"
    assert _lancer_main(racine, journal, monkeypatch, "--oui") == 0
    sortie = capsys.readouterr().out
    section = journal.read_text(encoding="utf-8").split("LAISSÉS DE CÔTÉ", 1)[1].split("\n\n", 1)[0]
    assert f"— {len(attendus)}" in section.splitlines()[0]
    for rel, raison in attendus.items():
        assert f"{rel} ({raison})" in section
        assert f"· {rel} ({raison})" in sortie
    assert "Laissés de côté (" in sortie and f": {len(attendus)}" in sortie
    for d in ["Library", ".cache", "X.app", "$RECYCLE.BIN"]:
        assert noms(racine / d) == ["dedans.JPG.JPG"]
    assert noms(tmp_path / "ailleurs") == ["o.JPG.JPG"]
    assert (racine / "x.JPG").exists() and (racine / "ok.zip").exists()


@pytest.mark.parametrize("avec_journal,nombre,listes", [
    (True, corr.SEUIL_LISTES + 1, False), (False, corr.SEUIL_LISTES + 1, True),
    (True, corr.SEUIL_LISTES, True),
])
def test_laisses_de_cote_longue_liste(tmp_path, monkeypatch, capsys, avec_journal, nombre, listes):
    racine = tmp_path / "racine"
    racine.mkdir()
    for i in range(nombre):
        (racine / f".cache{i}").mkdir()
    touch(racine / "a.JPG.JPG")
    journal = tmp_path / "rename_log_test.txt" if avec_journal else None
    _lancer_main(racine, journal, monkeypatch, "--dry-run")
    sortie = capsys.readouterr().out
    lignes = [l for l in sortie.splitlines() if l.strip().startswith("· .cache")]
    assert len(lignes) == (nombre if listes else 0)
    if not listes:
        assert "\n      (liste complète dans le journal)\n" in sortie
        assert journal.read_text(encoding="utf-8").count("(dossier caché)") == nombre


# ---------------------------------------------------------------------------
# §3 — code de sortie (réponse PO 10a)
# ---------------------------------------------------------------------------

def test_code_sortie_zero(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")
    assert _lancer_main(tmp_path, None, monkeypatch, "--oui") == 0
    assert _lancer_main(tmp_path, None, monkeypatch, "--oui") == 0     # rien à faire


def test_code_sortie_ignores_seuls_zero(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")
    monkeypatch.setattr(corr, "appliquer", lambda modifs: (0, [("a.JPG.JPG", "cible occupée")], [], False))
    assert _lancer_main(tmp_path, None, monkeypatch, "--oui") == 0


def test_code_sortie_erreur_de_renommage(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")
    touch(tmp_path / "b.ZIP.ZIP")

    def erreur_io(src, dst):
        raise OSError(errno.EIO, "erreur d'entrée-sortie", dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", erreur_io)
    assert _lancer_main(tmp_path, None, monkeypatch, "--oui") == 1
    assert noms(tmp_path) == ["a.JPG.JPG", "b.ZIP.ZIP"]


def test_code_sortie_usage(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog"])
    with pytest.raises(SystemExit) as fin:
        corr.main()
    assert fin.value.code == 1


# ---------------------------------------------------------------------------
# §3 — arrêt par SIGTERM ou SIGHUP noté au journal, code 128 + signal (réponse PO 10a)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nom_signal", ["SIGTERM", "SIGHUP"])
def test_arret_par_signal_note_au_journal(tmp_path, nom_signal):
    import subprocess
    racine = tmp_path / "racine"
    racine.mkdir()
    for i in range(4):
        touch(racine / f"f{i}.JPG.JPG")
    journal = tmp_path / "rename_log_test.txt"
    script = f"""
import os, signal, sys
sys.path.insert(0, {str(Path(corr.__file__).parent)!r})
import corriger_extensions as corr
from pathlib import Path
corr.choisir_journal = lambda r: (Path({str(journal)!r}), False)
vrai = corr._rename_no_overwrite
appels = []
def coupe(src, dst):
    r = vrai(src, dst)
    appels.append(dst)
    if len(appels) == 2:
        os.kill(os.getpid(), signal.{nom_signal})
    return r
corr._rename_no_overwrite = coupe
sys.argv = ["prog", {str(racine)!r}, "--oui"]
sys.exit(corr.main())
"""
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    signum = getattr(signal, nom_signal)
    assert r.returncode == 128 + signum
    texte = journal.read_text(encoding="utf-8")
    assert f"INTERROMPU ({nom_signal}) après 2 fichier(s) traité(s) sur 4" in texte
    assert "Renommés avec succès : 2" in texte
    assert noms(racine) == ["f0.jpg", "f1.jpg", "f2.JPG.JPG", "f3.JPG.JPG"]


# ---------------------------------------------------------------------------
# §3 — caractères de contrôle échappés à l'écran et au journal (réponse PO 10a)
# ---------------------------------------------------------------------------

def test_caracteres_de_controle_echappes(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    racine.mkdir()
    noms_bruts = ["a\nb.JPG.JPG", "esc\x1b[2K\rfaux.JPG.JPG", "inv‮gpj.ZIP.ZIP"]
    for nom in noms_bruts:
        touch(racine / nom)
    journal = tmp_path / "rename_log_test.txt"
    assert _lancer_main(racine, journal, monkeypatch, "--oui") == 0
    sortie = capsys.readouterr().out
    texte = journal.read_text(encoding="utf-8")
    for echappe in ["a\\nb.JPG.JPG", "esc\\x1b[2K\\rfaux.JPG.JPG", "inv\\u202egpj.ZIP.ZIP"]:
        assert echappe in sortie and echappe in texte
    for brut in ["\x1b", "\r", "‮", "a\nb"]:
        assert brut not in sortie and brut not in texte
    assert sorted(os.listdir(racine)) == sorted(["a\nb.jpg", "esc\x1b[2K\rfaux.jpg", "inv‮gpj.zip"])


# ---------------------------------------------------------------------------
# Sorties de référence : écran et journal exacts (ce que le PO lit avant de dire o/N)
# ---------------------------------------------------------------------------

class _DateFigee(corr.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 2, 3, 4, 5)


ECRAN_COMPLET = "🔎 Analyse des noms de fichiers sous : <RACINE>\n   (lecture seule, le contenu des fichiers n'est jamais ouvert)\n\n📁 Racine                  : <RACINE>\n🔧 À corriger              : 3\n✅ Déjà corrects           : 3\n🧹 Restes d'un run interrompu (__rename_tmp_*, jamais renommés) : 1\n      · __rename_tmp_x.jpg\n🙈 Laissés de côté (1 dossier Library ou corbeille, 1 dossier caché, 1 journal de l'outil (rename_log_*), 1 lien symbolique non suivi) : 4\n      · .cache (dossier caché)\n      · Library (dossier Library ou corbeille)\n      · lien (lien symbolique non suivi)\n      · rename_log_vieux.txt (journal de l'outil (rename_log_*))\n🔗 Compagnons et liens à vérifier (jamais renommés) : 2\n      · a.JPG.JPG.xmp → vise a.JPG.JPG (compagnon nommé d'après le nom complet)\n      · lien → vise a.JPG.JPG (lien symbolique)\n📝 Liste complète (journal): <JOURNAL>\n   ⚠️  Journal sur le MÊME volume que la racine (aucun autre volume inscriptible trouvé).\n\nRenommages prévus :\n----------------------------------------------------------------------\n  a.JPG.JPG\n      → a.jpg\n  album/IMG.2024.JPG.JPG\n      → IMG.2024.jpg\n  c.XLSX\n      → c.xlsx\n\n✅ Terminé. 3 fichier(s) renommé(s).\n📝 Journal complet : <JOURNAL>\n"

JOURNAL_COMPLET = "Journal de nettoyage d'extensions — 2026-01-02 03:04:05\nRacine : <RACINE>\nÉtat : LISTE PRÉVUE (rien n'a encore été renommé)\n==============================================================================\n\nÀ CORRIGER — 3 fichier(s)\n------------------------------------------------------------------------------\na.JPG.JPG\n  → a.jpg\n\nalbum/IMG.2024.JPG.JPG\n  → IMG.2024.jpg\n\nc.XLSX\n  → c.xlsx\n\n\nDÉJÀ CORRECTS — 3 fichier(s) (nom déjà propre)\n\nCOMPAGNONS ET LIENS À VÉRIFIER (jamais renommés) — 2\n------------------------------------------------------------------------------\na.JPG.JPG.xmp → vise a.JPG.JPG (compagnon nommé d'après le nom complet)\nlien → vise a.JPG.JPG (lien symbolique)\n\nLAISSÉS DE CÔTÉ (jamais renommés) — 4\n------------------------------------------------------------------------------\n.cache (dossier caché)\nLibrary (dossier Library ou corbeille)\nlien (lien symbolique non suivi)\nrename_log_vieux.txt (journal de l'outil (rename_log_*))\n\nORPHELINS D'UN RUN INTERROMPU (jamais renommés) — 1\n------------------------------------------------------------------------------\n__rename_tmp_x.jpg\n\n\n==============================================================================\nRÉSULTATS — 2026-01-02 03:04:05\n==============================================================================\nRenommés avec succès : 3\n\n"


def test_sortie_de_reference_complete(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(corr, "datetime", _DateFigee)
    r = tmp_path / "racine"
    (r / "album").mkdir(parents=True)
    for n in ["a.JPG.JPG", "a.JPG.JPG.xmp", "c.XLSX", "d.jpg", "Notes.IMPORTANT",
              "__rename_tmp_x.jpg", "rename_log_vieux.txt"]:
        touch(r / n, b"x")
    touch(r / "album" / "IMG.2024.JPG.JPG", b"x")
    (r / ".cache").mkdir()
    (r / "Library").mkdir()
    (r / "lien").symlink_to(r / "a.JPG.JPG")
    j = tmp_path / "rename_log_test.txt"
    monkeypatch.setattr(corr, "choisir_journal", lambda x: (j, True))
    monkeypatch.setattr("sys.argv", ["prog", str(r), "--oui"])
    assert corr.main() == 0
    ecran = capsys.readouterr().out.replace(str(r), "<RACINE>").replace(str(j), "<JOURNAL>")
    assert ecran == ECRAN_COMPLET
    assert j.read_text(encoding="utf-8").replace(str(r), "<RACINE>") + "\n" == JOURNAL_COMPLET


ECRAN_REPLI = "🔎 Analyse des noms de fichiers sous : <RACINE>\n   (lecture seule, le contenu des fichiers n'est jamais ouvert)\n\n📁 Racine                  : <RACINE>\n🔧 À corriger              : 3\n✅ Déjà corrects           : 0\n📝 Liste complète (journal): <JOURNAL>\n\nRenommages prévus :\n----------------------------------------------------------------------\n  a.JPG.JPG\n      → a.jpg\n  b.ZIP.ZIP\n      → b.zip\n  erreur.PDF.PDF\n      → erreur.pdf\n\n✅ Terminé. 1 fichier(s) renommé(s).\n⚠️  Système de fichiers sans renommage atomique (exFAT / partage réseau) : la garantie anti-écrasement a reposé sur un test d'existence, non atomique.\n⏭️  1 ignoré(s) par prudence (état changé depuis le scan ; détails dans le journal).\n❌ 1 erreur(s) (détails dans le journal).\n📝 Journal complet : <JOURNAL>\n"

RESULTATS_REPLI = " — 2026-01-02 03:04:05\n==============================================================================\nRenommés avec succès : 1\n\n⚠️  Système de fichiers sans renommage atomique (exFAT / partage réseau) : la garantie anti-écrasement a reposé sur un test d'existence, non atomique.\n\nIGNORÉS (état changé depuis le scan, par prudence) — 1\n------------------------------------------------------------------------------\nb.ZIP.ZIP : cible occupée depuis le scan\n\nERREURS — 1\n------------------------------------------------------------------------------\nerreur.PDF.PDF : [Errno 5] Input/output error: '<RACINE>/erreur.pdf'\n"


class _FauxLibcSansAtomique:
    """renameat2 refusé comme sur exFAT (ENOTSUP), sauf « erreur* » qui échoue (EIO)."""

    def renameat2(self, a, src, b, dst, drapeaux):
        ctypes.set_errno(errno.EIO if b"erreur" in dst else errno.ENOTSUP)
        return -1


def test_sortie_de_reference_repli_ignore_erreur(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(corr, "datetime", _DateFigee)
    monkeypatch.setattr(corr, "_LIBC", _FauxLibcSansAtomique())
    monkeypatch.setattr(corr.sys, "platform", "linux")
    r = tmp_path / "racine"
    r.mkdir()
    for n in ["a.JPG.JPG", "b.ZIP.ZIP", "erreur.PDF.PDF"]:
        touch(r / n, b"x")
    vrai = corr.appliquer

    def cible_apparue(modifs):
        touch(r / "b.zip", b"apparu")
        return vrai(modifs)

    monkeypatch.setattr(corr, "appliquer", cible_apparue)
    j = tmp_path / "rename_log_test.txt"
    monkeypatch.setattr(corr, "choisir_journal", lambda x: (j, False))
    monkeypatch.setattr("sys.argv", ["prog", str(r), "--oui"])
    assert corr.main() == 1
    ecran = capsys.readouterr().out.replace(str(r), "<RACINE>").replace(str(j), "<JOURNAL>")
    assert ecran == ECRAN_REPLI
    resultats = j.read_text(encoding="utf-8").split("RÉSULTATS", 1)[1].replace(str(r), "<RACINE>")
    assert resultats == RESULTATS_REPLI
    assert noms(r) == ["a.jpg", "b.ZIP.ZIP", "b.zip", "erreur.PDF.PDF"]
    assert (r / "b.zip").read_bytes() == b"apparu"



# ---------------------------------------------------------------------------
# Comblement de la passe de mutation (réponse PO 6a) : chaque test ferme un trou relevé
# ---------------------------------------------------------------------------

def test_suffixe_au_dela_de_2(tmp_path):
    touch(tmp_path / "a.JPG", b"source")
    touch(tmp_path / "a.jpg", b"un")
    touch(tmp_path / "a_2.jpg", b"deux")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1
    assert (tmp_path / "a_3.jpg").read_bytes() == b"source"
    assert len(noms(tmp_path)) == 3


def _beaucoup(racine, n):
    racine.mkdir()
    for i in range(n):
        touch(racine / f"f{i:03d}.JPG")


@pytest.mark.parametrize("n,options,attendu_lignes,tronque", [
    (corr.SEUIL_APERCU + 1, (), 40, True),
    (corr.SEUIL_APERCU, (), corr.SEUIL_APERCU, False),
    (corr.SEUIL_APERCU + 1, ("--tout",), corr.SEUIL_APERCU + 1, False),
])
def test_apercu_tronque_ou_integral(tmp_path, monkeypatch, capsys, n, options, attendu_lignes, tronque):
    racine = tmp_path / "racine"
    _beaucoup(racine, n)
    journal = tmp_path / "rename_log_test.txt"
    assert _lancer_main(racine, journal, monkeypatch, "--dry-run", *options) == 0
    sortie = capsys.readouterr().out
    assert len([l for l in sortie.splitlines() if l.startswith("      → f")]) == attendu_lignes
    if tronque:
        assert f"\n  … +{n - 40} autre(s) non affichés ici.\n" in sortie
        assert "\n  Liste intégrale dans le journal ci-dessus (ouvre-le pour tout vérifier).\n" in sortie
        assert "\n  (Relance avec --tout pour tout afficher à l'écran.)\n" in sortie
    else:
        assert "autre(s) non affichés" not in sortie


def test_journal_impossible_a_ecrire_liste_integrale(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    _beaucoup(racine, corr.SEUIL_APERCU + 1)

    def echoue(*a, **k):
        raise OSError(errno.ENOSPC, "plus de place")

    monkeypatch.setattr(corr, "ecrire_journal_prevu", echoue)
    assert _lancer_main(racine, tmp_path / "j.txt", monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert "⚠️  Journal non écrit ([Errno 28] plus de place) ; liste affichée en entier ci-dessous." in sortie
    assert "\n📝 Journal non écrit (aucun emplacement hors racine) : liste affichée en entier ci-dessous.\n" in sortie
    assert len([l for l in sortie.splitlines() if l.startswith("      → f")]) == corr.SEUIL_APERCU + 1


def test_messages_rien_a_faire_et_dry_run(tmp_path, monkeypatch, capsys):
    touch(tmp_path / "ok.jpg")
    assert _lancer_main(tmp_path, None, monkeypatch, "--oui") == 0
    assert "\n✅ Aucune extension à corriger. Rien à faire.\n" in capsys.readouterr().out
    touch(tmp_path / "a.JPG.JPG")
    assert _lancer_main(tmp_path, None, monkeypatch, "--dry-run") == 0
    assert "\n🧪 --dry-run : liste affichée, aucune modification effectuée.\n" in capsys.readouterr().out


def test_messages_refus_et_dossier_invalide(tmp_path, monkeypatch, capsys):
    paquet = tmp_path / "X.app"
    paquet.mkdir()
    monkeypatch.setattr("sys.argv", ["prog", str(paquet)])
    with pytest.raises(SystemExit) as fin:
        corr.main()
    assert fin.value.code == 1
    sortie = capsys.readouterr().out
    assert f"⛔ Refus : « {paquet} » est un emplacement protégé (système, paquet macOS ou corbeille).\n" in sortie
    assert "   Vise un dossier de données (ex. ~/Pictures, ~/Movies, /Volumes/TonArchive).\n" in sortie
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path / "absent")])
    with pytest.raises(SystemExit) as fin:
        corr.main()
    assert fin.value.code == 1
    assert f"❌ Dossier introuvable ou invalide : {tmp_path / 'absent'}\n" in capsys.readouterr().out


def test_message_usage(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog", "a", "b"])
    with pytest.raises(SystemExit):
        corr.main()
    assert "Usage : python3 corriger_extensions.py <dossier> [--dry-run] [--tout] [--oui]\n" in capsys.readouterr().out


@pytest.mark.parametrize("option", ["-h", "--help"])
def test_aide(monkeypatch, capsys, option):
    monkeypatch.setattr("sys.argv", ["prog", option])
    with pytest.raises(SystemExit) as fin:
        corr.main()
    assert fin.value.code == 0
    assert capsys.readouterr().out == corr.__doc__ + "\n"


def test_option_yes(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")
    monkeypatch.setattr("sys.stdin", _StdinPasTTY())
    assert _lancer_main(tmp_path, None, monkeypatch, "--yes") == 0
    assert noms(tmp_path) == ["a.jpg"]


@pytest.mark.parametrize("reponse", ["y", "yes", "YES", " O "])
def test_confirmation_autres_oui(monkeypatch, reponse):
    monkeypatch.setattr("sys.stdin", _StdinTTY())
    monkeypatch.setattr("builtins.input", lambda invite="": reponse)
    assert corr.demander_confirmation(3) is True


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_confirmation_ctrl_d_ou_ctrl_c(monkeypatch, capsys, exception):
    monkeypatch.setattr("sys.stdin", _StdinTTY())

    def leve(invite=""):
        raise exception

    monkeypatch.setattr("builtins.input", leve)
    assert corr.demander_confirmation(3) is False
    assert "\nAnnulé.\n" in capsys.readouterr().out


def test_confirmation_texte(monkeypatch, capsys):
    vus = []
    monkeypatch.setattr("sys.stdin", _StdinTTY())
    monkeypatch.setattr("builtins.input", lambda invite="": vus.append(invite) or "n")
    assert corr.demander_confirmation(7) is False
    assert vus == ["\n➡️  Appliquer ces 7 renommage(s) ? [o/N] "]
    monkeypatch.setattr("sys.stdin", _StdinPasTTY())
    assert corr.demander_confirmation(7) is False
    sortie = capsys.readouterr().out
    assert "\n⏸️  Entrée non interactive : aucune modification effectuée.\n" in sortie
    assert "   (Pour appliquer sans invite, relance avec --oui.)\n" in sortie


def test_main_confirmation_refusee_message(tmp_path, monkeypatch, capsys):
    touch(tmp_path / "a.JPG.JPG")
    monkeypatch.setattr("sys.stdin", _StdinTTY())
    monkeypatch.setattr("builtins.input", lambda invite="": "")
    assert _lancer_main(tmp_path, None, monkeypatch) == 0
    assert "✋ Aucune modification effectuée.\n" in capsys.readouterr().out


def test_message_interruption(tmp_path, monkeypatch, capsys):
    for i in range(5):
        touch(tmp_path / f"f{i}.JPG")
    vrai = corr._rename_no_overwrite
    appels = []

    def coupe(src, dst):
        appels.append(src)
        if len(appels) == 3:
            raise KeyboardInterrupt
        return vrai(src, dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", coupe)
    j = tmp_path.parent / f"j-{tmp_path.name}.txt"
    with pytest.raises(SystemExit) as fin:
        _lancer_main(tmp_path, j, monkeypatch, "--oui")
    assert fin.value.code == 130
    sortie = capsys.readouterr().out
    assert ("\n⛔ Interrompu (Ctrl-C) après 2 fichier(s) traité(s) sur 5 (2 renommé(s)) ; "
            "les suivants n'ont pas été touchés.\n") in sortie
    assert f"📝 Journal complet : {j}\n" in sortie
    assert ("\nINTERROMPU (Ctrl-C) après 2 fichier(s) traité(s) sur 5, dans l'ordre de la liste ci-dessus ; "
            "les suivants n'ont pas été touchés.\n") in j.read_text(encoding="utf-8")


def test_source_disparue_ignoree(tmp_path):
    touch(tmp_path / "a.JPG.JPG")
    modifs = corr.scanner(tmp_path)[0]
    (tmp_path / "a.JPG.JPG").unlink()
    renommes, ignores, erreurs, _ = corr.appliquer(modifs)
    assert (renommes, ignores, erreurs) == (0, [("a.JPG.JPG", "source disparue ou devenue un lien")], [])


def test_raisons_exactes_par_chemin(tmp_path, monkeypatch):
    a = touch(tmp_path / "a.JPG")
    b = touch(tmp_path / "b.JPG")
    c = touch(tmp_path / "c.JPG")
    d = touch(tmp_path / "d.ZIP.ZIP")
    modifs = [forge(a, "a.jpg", True, tmp_path), forge(b, "b.jpg", True, tmp_path),
              forge(c, "c.jpg", True, tmp_path), forge(d, "d.zip", False, tmp_path)]
    vrai = corr._rename_no_overwrite

    def selon_le_nom(src, dst):
        if dst.endswith("/a.jpg"):
            raise FileExistsError(errno.EEXIST, "occupé", dst)
        if dst.endswith("/b.jpg"):
            raise OSError(errno.EIO, "étape 2", dst)
        if dst.endswith(f"{corr.PREFIXE_TMP}c.jpg"):
            raise OSError(errno.EIO, "étape 1", dst)
        if dst.endswith("/d.zip"):
            raise OSError(errno.EIO, "direct", dst)
        return vrai(src, dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", selon_le_nom)
    renommes, ignores, erreurs, _ = corr.appliquer(modifs)
    assert renommes == 0
    assert ignores == [("a.JPG", "cible occupée (lien dur / apparue depuis le scan)")]
    assert erreurs == [
        ("b.JPG", f"[Errno 5] étape 2: '{tmp_path / 'b.jpg'}'"),
        ("c.JPG", f"[Errno 5] étape 1: '{tmp_path / (corr.PREFIXE_TMP + 'c.jpg')}'"),
        ("d.ZIP.ZIP", f"[Errno 5] direct: '{tmp_path / 'd.zip'}'"),
    ]
    assert noms(tmp_path) == ["a.JPG", "b.JPG", "c.JPG", "d.ZIP.ZIP"]


def test_cible_occupee_ignoree_chemin_direct(tmp_path):
    touch(tmp_path / "d.ZIP.ZIP", b"source")
    modifs = corr.scanner(tmp_path)[0]
    touch(tmp_path / "d.zip", b"apparu")
    renommes, ignores, erreurs, _ = corr.appliquer(modifs)
    assert (renommes, ignores, erreurs) == (0, [("d.ZIP.ZIP", "cible occupée depuis le scan")], [])


@pytest.mark.parametrize("case_safe", [True, False])
def test_repli_garde_en_memoire_sur_tout_le_lot(tmp_path, monkeypatch, case_safe):
    fichiers = [touch(tmp_path / f"{x}.JPG") for x in "ab"]
    modifs = [forge(f, f.name.replace(".JPG", ".jpg"), case_safe, tmp_path) for f in fichiers]
    vrai = corr._rename_no_overwrite
    appels = []

    def repli_au_premier_appel(src, dst):
        appels.append(src)
        vrai(src, dst)
        return len(appels) == 1

    monkeypatch.setattr(corr, "_rename_no_overwrite", repli_au_premier_appel)
    renommes, _, erreurs, repli = corr.appliquer(modifs)
    assert renommes == 2 and erreurs == [] and repli is True
    assert noms(tmp_path) == ["a.jpg", "b.jpg"]


def test_casse_nom_temporaire_dans_le_meme_dossier(tmp_path, monkeypatch):
    src = touch(tmp_path / "a.JPG")
    vus = []
    vrai = corr._rename_no_overwrite

    def espion(s, d):
        vus.append((s, d))
        return vrai(s, d)

    monkeypatch.setattr(corr, "_rename_no_overwrite", espion)
    corr.appliquer([forge(src, "a.jpg", True, tmp_path)])
    temp = str(tmp_path / f"{corr.PREFIXE_TMP}a.jpg")
    assert vus == [(str(src), temp), (temp, str(tmp_path / "a.jpg"))]


def test_vraie_detection_du_repli_errno(tmp_path, monkeypatch):
    for code in (errno.ENOTSUP, errno.EINVAL, errno.ENOSYS):
        class Refus:
            def renameat2(self, *a):
                ctypes.set_errno(code)
                return -1
        monkeypatch.setattr(corr, "_LIBC", Refus())
        monkeypatch.setattr(corr.sys, "platform", "linux")
        nom = f"f{code}.ZIP.ZIP"
        touch(tmp_path / nom)
        r = scan_apply(tmp_path)
        assert r["renommes"] == 1 and r["repli"] is True and r["erreurs"] == []
        assert (tmp_path / f"f{code}.zip").exists()


def test_choisir_journal_meme_volume_annonce(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    racine.mkdir()
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    monkeypatch.chdir(ailleurs)
    monkeypatch.setenv("HOME", str(ailleurs))
    monkeypatch.setattr(corr.tempfile, "tempdir", str(ailleurs))
    journal, meme_volume = corr.choisir_journal(racine.resolve())
    assert journal is not None and journal.parent == ailleurs.resolve() and meme_volume is True


def test_main_journal_reel_hors_racine(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    racine.mkdir()
    touch(racine / "a.JPG.JPG")
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    monkeypatch.chdir(ailleurs)
    monkeypatch.setenv("HOME", str(ailleurs))
    monkeypatch.setattr(corr.tempfile, "tempdir", str(ailleurs))
    monkeypatch.setattr("sys.argv", ["prog", str(racine), "--oui"])
    assert corr.main() == 0
    journaux = [n for n in os.listdir(ailleurs) if n.startswith("rename_log_")]
    assert len(journaux) == 1 and "a.JPG.JPG" in (ailleurs / journaux[0]).read_text(encoding="utf-8")
    assert noms(racine) == ["a.jpg"]


def test_date_non_remise_apres_interruption_signalee(tmp_path, monkeypatch):
    for i in range(2):
        touch(tmp_path / f"f{i}.JPG")
    modifs = corr.scanner(tmp_path)[0]
    vrai = corr._rename_no_overwrite
    appels = []

    def coupe(src, dst):
        appels.append(src)
        if len(appels) == 2:
            raise KeyboardInterrupt
        return vrai(src, dst)

    def refuse(*a, **k):
        raise PermissionError(errno.EPERM, "refusé")

    monkeypatch.setattr(corr, "_rename_no_overwrite", coupe)
    monkeypatch.setattr(corr.os, "utime", refuse)
    with pytest.raises(corr.Interrompu) as interruption:
        corr.appliquer(modifs)
    erreurs = interruption.value.resultats[2]
    assert len(erreurs) == 1 and "date du dossier non remise" in erreurs[0][1]


def test_deux_renommages_de_casse_comptes(tmp_path):
    modifs = [forge(touch(tmp_path / f"{x}.JPG"), f"{x}.jpg", True, tmp_path) for x in "ab"]
    renommes, _, erreurs, _ = corr.appliquer(modifs)
    assert renommes == 2 and erreurs == []



# ---------------------------------------------------------------------------
# Comblement, deuxième passe de mutation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("premier", [".DS_Store", "0-deja-correct.jpg", "0rename_log_vieux.txt"])
def test_un_fichier_ecarte_ne_stoppe_pas_le_dossier(tmp_path, premier):
    touch(tmp_path / premier.replace("0rename", "rename"))
    touch(tmp_path / "b.JPG.JPG")
    touch(tmp_path / "c.ZIP.ZIP")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 2
    assert {"b.jpg", "c.zip"} <= set(noms(tmp_path))


def test_fichiers_caches_ni_comptes_ni_touches(tmp_path):
    touch(tmp_path / ".DS_Store")
    touch(tmp_path / "._photo.JPG.JPG")
    modifs, deja_ok, _, _ = corr.scanner(tmp_path)
    assert modifs == [] and deja_ok == 0


def test_cible_prise_par_un_lien_ne_stoppe_pas_le_dossier(tmp_path):
    touch(tmp_path / "a.JPG")
    (tmp_path / "a.jpg").symlink_to(tmp_path / "nulle-part")
    touch(tmp_path / "b.JPG.JPG")
    assert scan_apply(tmp_path)["renommes"] == 1
    assert (tmp_path / "b.jpg").exists()


def test_dossier_illisible_ne_stoppe_pas_le_scan(tmp_path, monkeypatch, capsys):
    racine = tmp_path / "racine"
    for d in ["a-verrouille", "b-libre"]:
        (racine / d).mkdir(parents=True)
        touch(racine / d / "x.JPG.JPG")
    vrai = os.scandir

    def scandir(chemin):
        if str(chemin).endswith("a-verrouille"):
            raise PermissionError(errno.EACCES, "Permission denied", str(chemin))
        return vrai(chemin)

    monkeypatch.setattr(corr.os, "scandir", scandir)
    j = tmp_path / "rename_log_test.txt"
    assert _lancer_main(racine, j, monkeypatch, "--oui") == 1
    assert noms(racine / "b-libre") == ["x.jpg"]
    message = f"[Errno 13] Permission denied: '{racine / 'a-verrouille'}'"
    sortie = capsys.readouterr().out
    assert "\n🚫 Dossiers inaccessibles  : 1 (non examinés)\n" in sortie
    assert (f"\nDOSSIERS INACCESSIBLES (non examinés) — 1\n{'-' * 78}\n{message}\n"
            in j.read_text(encoding="utf-8"))


def test_detection_casse_sur_disque_insensible(tmp_path, monkeypatch):
    """Simule APFS : a.jpg « existe » et c'est le même fichier que a.JPG."""
    touch(tmp_path / "a.JPG")
    vrai = os.path.lexists
    monkeypatch.setattr(corr.os.path, "lexists",
                        lambda p: str(p) == str(tmp_path / "a.jpg") or vrai(p))
    monkeypatch.setattr(corr, "meme_fichier", lambda a, b: True)
    modifs = corr.scanner(tmp_path)[0]
    assert [(m.cible_nom, m.case_safe) for m in modifs] == [("a.jpg", True)]


def test_compagnon_qui_est_lui_meme_a_renommer_non_signale(tmp_path):
    for n in ["a.jpg.jpg", "a.jpg.jpg.jpg", "a.XMP.XMP", "a.XMP.xmp"]:
        touch(tmp_path / n)
    laisses = []
    modifs = corr.scanner(tmp_path, laisses)[0]
    assert len(modifs) == 4
    assert corr.compagnons(modifs, laisses) == []


def test_compagnons_dans_un_sous_dossier(tmp_path):
    (tmp_path / "album").mkdir()
    for n in ["IMG.JPG.JPG", "IMG.JPG.JPG.xmp", "IMG.JPG.xmp"]:
        touch(tmp_path / "album" / n)
    laisses = []
    modifs = corr.scanner(tmp_path, laisses)[0]
    assert corr.compagnons(modifs, laisses) == [
        ("album/IMG.JPG.JPG.xmp", "album/IMG.JPG.JPG", "compagnon nommé d'après le nom complet"),
        ("album/IMG.JPG.xmp", "album/IMG.JPG.JPG", "compagnon Lightroom (même radical)"),
    ]


def test_compte_des_laisses_par_raison(tmp_path, monkeypatch, capsys):
    for d in [".a", ".b", "Library"]:
        (tmp_path / d).mkdir()
    touch(tmp_path / "x.JPG.JPG")
    _lancer_main(tmp_path, None, monkeypatch, "--dry-run")
    assert "🙈 Laissés de côté (1 dossier Library ou corbeille, 2 dossier caché) : 3\n" in capsys.readouterr().out


@pytest.mark.parametrize("genre", ["laisses", "compagnons"])
def test_tout_et_journal_pour_les_listes(tmp_path, monkeypatch, capsys, genre):
    racine = tmp_path / "racine"
    racine.mkdir()
    n = corr.SEUIL_LISTES + 1
    for i in range(n):
        if genre == "laisses":
            (racine / f".d{i}").mkdir()
        else:
            touch(racine / f"f{i:02d}.JPG.JPG")
            touch(racine / f"f{i:02d}.JPG.JPG.xmp")
    j = tmp_path / "rename_log_test.txt"

    def lignes_listees(sortie):
        if genre == "laisses":
            return sum(1 for l in sortie.splitlines() if l.strip().startswith("· .d"))
        return sum(1 for l in sortie.splitlines() if "→ vise" in l)

    _lancer_main(racine, j, monkeypatch, "--dry-run")
    assert lignes_listees(capsys.readouterr().out) == 0
    _lancer_main(racine, j, monkeypatch, "--dry-run", "--tout")
    assert lignes_listees(capsys.readouterr().out) == n


def test_nom_non_utf8_dans_les_resultats(tmp_path, monkeypatch):
    racine = tmp_path / "racine"
    racine.mkdir()
    fd = os.open(os.fsencode(racine) + b"/caf\xe9.JPG.JPG", os.O_CREAT | os.O_WRONLY, 0o644)
    os.close(fd)

    def erreur_io(src, dst):
        raise OSError(errno.EIO, "erreur", dst)

    monkeypatch.setattr(corr, "_rename_no_overwrite", erreur_io)
    j = tmp_path / "rename_log_test.txt"
    assert _lancer_main(racine, j, monkeypatch, "--oui") == 1
    resultats = j.read_text(encoding="utf-8").split("RÉSULTATS", 1)[1]
    assert "caf\\udce9.JPG.JPG : [Errno 5] erreur" in resultats


def test_main_invite_avec_le_nombre(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")
    touch(tmp_path / "b.ZIP.ZIP")
    vus = []
    monkeypatch.setattr("sys.stdin", _StdinTTY())
    monkeypatch.setattr("builtins.input", lambda invite="": vus.append(invite) or "n")
    _lancer_main(tmp_path, None, monkeypatch)
    assert vus == ["\n➡️  Appliquer ces 2 renommage(s) ? [o/N] "]


def test_temp_deja_pris_reste_dans_le_dossier(tmp_path, monkeypatch):
    src = touch(tmp_path / "a.JPG", b"photo")
    touch(tmp_path / f"{corr.PREFIXE_TMP}a.jpg", b"orphelin")
    vus = []
    vrai = corr._rename_no_overwrite

    def espion(s, d):
        vus.append(d)
        return vrai(s, d)

    monkeypatch.setattr(corr, "_rename_no_overwrite", espion)
    corr.appliquer([forge(src, "a.jpg", True, tmp_path)])
    assert vus[0] == str(tmp_path / f"{corr.PREFIXE_TMP}a_2.jpg")


def test_compagnon_lightroom_radical_a_points(tmp_path):
    for n in ["x.2024.JPG", "x.2024.xmp", "y.2024.JPG.JPG", "y.2024.JPG.xmp"]:
        touch(tmp_path / n)
    laisses = []
    modifs = corr.scanner(tmp_path, laisses)[0]
    assert corr.compagnons(modifs, laisses) == [
        ("y.2024.JPG.xmp", "y.2024.JPG.JPG", "compagnon Lightroom (même radical)")]


# ---------------------------------------------------------------------------
# Chemins d'erreur rares (course, disque débranché), éprouvés par injection
# ---------------------------------------------------------------------------

class _EntreeQuiEchoue:
    def __init__(self, vraie, methode):
        self._vraie, self._methode = vraie, methode
        self.name, self.path = vraie.name, vraie.path

    def __getattr__(self, nom):
        if nom == self._methode:
            def echoue(*a, **k):
                raise PermissionError(errno.EACCES, "refusé", self.path)
            return echoue
        return getattr(self._vraie, nom)


def _scandir_qui_echoue(monkeypatch, nom_vise, methode):
    vrai = os.scandir

    class Contexte:
        def __init__(self, chemin):
            with vrai(chemin) as it:
                self.entrees = [_EntreeQuiEchoue(e, methode) if e.name == nom_vise else e for e in it]

        def __enter__(self):
            return iter(self.entrees)

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(corr.os, "scandir", Contexte)


@pytest.mark.parametrize("methode", ["stat", "is_dir", "is_symlink"])
def test_entree_illisible_ne_stoppe_pas_le_dossier(tmp_path, monkeypatch, methode):
    for n in ["a.JPG.JPG", "b.ZIP.ZIP", "c.XLSX"]:
        touch(tmp_path / n)
    _scandir_qui_echoue(monkeypatch, "a.JPG.JPG", methode)
    modifs, _, erreurs_acces, _ = corr.scanner(tmp_path)
    assert [m.rel for m in modifs] == ["b.ZIP.ZIP", "c.XLSX"]
    assert erreurs_acces == [f"[Errno 13] refusé: '{tmp_path / 'a.JPG.JPG'}'"]


def test_compagnons_dossier_disparu(tmp_path, monkeypatch):
    touch(tmp_path / "a.JPG.JPG")
    modifs = corr.scanner(tmp_path)[0]

    def disparu(chemin):
        raise FileNotFoundError(errno.ENOENT, "disparu", chemin)

    monkeypatch.setattr(corr.os, "listdir", disparu)
    assert corr.compagnons(modifs, []) == []


def test_source_illisible_au_moment_d_appliquer(tmp_path, monkeypatch):
    src = touch(tmp_path / "a.JPG.JPG")
    modifs = corr.scanner(tmp_path)[0]
    vrai = Path.stat

    def stat(self, *a, **k):
        if self == src:
            raise PermissionError(errno.EACCES, "refusé", str(self))
        return vrai(self, *a, **k)

    monkeypatch.setattr(Path, "stat", stat)
    renommes, ignores, erreurs, _ = corr.appliquer(modifs)
    assert (renommes, ignores) == (0, [])
    assert erreurs == [("a.JPG.JPG", f"[Errno 13] refusé: '{src}'")]


def test_meme_fichier_cible_absente():
    assert corr.meme_fichier(Path("/"), Path("/nulle-part-absent")) is False


def test_est_sous_racine_ou_parent_illisibles(tmp_path, monkeypatch):
    assert corr._est_sous(tmp_path, tmp_path / "absente") is False
    racine = tmp_path / "racine"
    (racine / "x" / "y").mkdir(parents=True)
    vrai = Path.stat

    def stat(self, *a, **k):
        if self == racine / "x" / "y":
            raise PermissionError(errno.EACCES, "refusé")
        return vrai(self, *a, **k)

    monkeypatch.setattr(Path, "stat", stat)
    assert corr._est_sous(racine / "x" / "y", racine) is True


@pytest.mark.parametrize("panne", ["resolve", "stat"])
def test_choisir_journal_candidat_en_panne_passe_au_suivant(tmp_path, monkeypatch, panne):
    racine = tmp_path / "racine"
    racine.mkdir()
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    for d in (cwd, home):
        d.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(corr.tempfile, "tempdir", str(home))
    vrai = getattr(Path, panne)
    en_echec = {str(cwd), str(cwd.resolve())}

    def en_panne(self, *a, **k):
        if str(self) in en_echec:
            raise PermissionError(errno.EACCES, "refusé")
        return vrai(self, *a, **k)

    monkeypatch.setattr(Path, panne, en_panne)
    journal, _ = corr.choisir_journal(racine.resolve())
    assert journal is not None and journal.parent == home.resolve()


def test_retour_arriere_impossible_consigne(tmp_path, monkeypatch):
    src = touch(tmp_path / "a.JPG", b"photo")
    vrai_rename = os.rename

    def etape_2_puis_debranche(s, d):
        if d.endswith("/a.jpg"):
            raise OSError(errno.EIO, "disque débranché", d)
        return vrai_rename(s, d)

    monkeypatch.setattr(corr, "_rename_no_overwrite", lambda s, d: etape_2_puis_debranche(s, d) or False)

    def rename_refuse(s, d):
        raise OSError(errno.ENODEV, "plus de disque", s)

    monkeypatch.setattr(corr.os, "rename", rename_refuse)
    renommes, ignores, erreurs, _ = corr.appliquer([forge(src, "a.jpg", True, tmp_path)])
    temp = f"{corr.PREFIXE_TMP}a.jpg"
    assert renommes == 0 and ignores == []
    assert erreurs[0] == ("a.JPG", f"[Errno 5] disque débranché: '{tmp_path / 'a.jpg'}'")
    assert erreurs[1][0] == "a.JPG" and erreurs[1][1].startswith(
        f"retour arrière impossible, fichier resté sous {temp} : [Errno 19] plus de disque")
    assert (tmp_path / temp).read_bytes() == b"photo"


def test_lot_insensible_a_la_casse_suffixe(tmp_path):
    touch(tmp_path / "X.jpg.jpg", b"un")
    touch(tmp_path / "x.JPG", b"deux")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 2 and r["ignores"] == []
    assert noms(tmp_path) == ["X.jpg", "x_2.jpg"]


def test_doublon_vers_un_lien_dur_suffixe(tmp_path):
    touch(tmp_path / "x.jpg", b"contenu")
    os.link(tmp_path / "x.jpg", tmp_path / "x.JPG.JPG")
    r = scan_apply(tmp_path)
    assert r["renommes"] == 1
    assert noms(tmp_path) == ["x.jpg", "x_2.jpg"]


def test_date_d_acces_du_dossier_remise_aussi(tmp_path):
    touch(tmp_path / "a.JPG.JPG")
    modifs = corr.scanner(tmp_path)[0]
    os.utime(tmp_path, ns=(1_000_000_000_000_000_000, 1_546_300_800_000_000_000))
    corr.appliquer(modifs)
    st = os.stat(tmp_path)
    assert (st.st_atime_ns, st.st_mtime_ns) == (1_000_000_000_000_000_000, 1_546_300_800_000_000_000)


@pytest.mark.parametrize("marque", [" ", " ", "‎", "‏", "؜"])
def test_autres_marques_de_sens_echappees(marque):
    assert corr._lisible(f"a{marque}b") == f"a\\u{ord(marque):04x}b"

"""Tests du contrat gelé de corriger_extensions (SPEC.md).

Chaque test cite la preuve du SPEC qu'il couvre. Plateforme de test : Linux, FS
sensible à la casse. Ce qui n'est pas vérifiable ici (st_birthtime, tags Finder,
chemin complet sur FS insensible à la casse) est déclaré tel quel dans le SPEC,
jamais simulé.
"""

import errno
import hashlib
import os
from pathlib import Path

import pytest

import corriger_extensions as corr


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
    ("IMG.2024.JPG.JPG", "IMG.2024.JPG.jpg"), # limite gravée : 2024 non connu, doublon survit
    ("sansext", "sansext"),                   # pas d'extension
    (".cache", ".cache"),                     # nom caché → intact
    ("a.b.c.JPG.JPG", "a.b.c.JPG.jpg"),       # b,c non connus → seule la casse finale
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
    ("IMG.2024.JPG.JPG", "IMG.2024.JPG.jpg"),       # pile non entièrement identique
    ("a.tar.gz.gz", "a.tar.gz.gz"),
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


@pytest.mark.parametrize("chemin", ["/Volumes/Archive", "/Users/moi/Pictures", "/data/photos"])
def test_racine_autorisee(chemin):
    assert corr.est_racine_interdite(Path(chemin)) is False


# ---------------------------------------------------------------------------
# §3/§4 — journal hors volume, jamais sous la racine, même liste que l'aperçu
# ---------------------------------------------------------------------------

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

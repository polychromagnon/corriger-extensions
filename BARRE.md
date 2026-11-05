# BARRE — corriger-extensions

> **Le principe.** Ce fichier est le tien : c'est le seul que tu dois ouvrir. Tout ce qui attend un geste de ta part est ici, et rien d'autre. L'équipage (`/dev` : spec, ship, send) le lit avant chaque run, le tient à jour, et n'efface jamais une ligne que tu as écrite.
>
> **Le partage des rôles.** `SPEC.md` est le contrat technique, tenu pour l'équipage : tu peux le lire, tu n'as jamais à y intervenir. Ici, chaque section dit qui écrit et ce que ta réponse déclenche.

---

## 1. Gravé dans le marbre — tes volontés

> Tes décisions durables, une par ligne, numérotées à la suite. L'équipage les applique à chaque cycle sans les rediscuter. Un **NON** écrit ici est définitif : l'objet refusé ne te sera jamais reproposé (ses voisins restent permis). Pour changer d'avis, édite ou retire la ligne : le prochain run s'aligne. Une nouvelle volonté s'ajoute en fin de liste, sans renuméroter.

1. L'outil sert pour tous les types de fichiers : un doublon d'extension identique est fusionné et mis en minuscules quelle que soit l'extension (`b.ZIP.ZIP` devient `b.zip`), sauf s'il n'est fait que de chiffres (`version.1.1` reste intact) ; la casse seule n'est corrigée que pour les extensions connues, liste élargie aux formats courants (`c.XLSX` devient `c.xlsx`, `Notes.IMPORTANT` reste intact). (réponse du 2026-11-05, choix c)
2. Un doublon d'extension en fin de nom est fusionné aussi : `IMG.2024.JPG.JPG` devient `IMG.2024.jpg`. (réponse du 2026-11-05, 1a)
3. Un `.jpeg` seul continue de devenir `.jpg` (`photo.jpeg` devient `photo.jpg`). (réponse du 2026-11-05, 2b)
4. Après les renommages, chaque dossier touché retrouve sa date de modification d'origine. (réponse du 2026-11-05, 3a)


## 2. Politiques en ton absence (`/dev auto`)

> Tes réponses données d'avance aux questions qui surgiraient pendant un run sans toi. Pour tout ce qui n'a pas de ligne ici, l'équipage prend le défaut le plus sûr et le consigne en section 4.

- features : SANS (MVP strict)
- parallele : OFF
- doute de périmètre : option minimale et réversible
- enjeu : … (+, ++ ou +++ ; prime sur le ++ par défaut ; vide, ++ s'applique quand tu lances toi-même en session, et une chasse sans toi n'attaque rien, sauf niveau fixé par le métier qui la lance ; ++++ ne se lit jamais ici)

## 3. ⚠ À TRANCHER — l'équipage attend ta décision

> Une décision par ligne : qui la pose, la question, la proposition de l'équipage, puis la flèche où tu réponds (un mot suffit : oui, non, un chiffre, un choix). Le prochain run lit ta réponse, l'applique, retire la ligne, et grave en section 1 ce qui mérite de durer. **Section vide : rien ne t'attend.** Tant qu'une ligne reste sans réponse, le SPEC n'est pas figé et rien ne part en production.



- [trust, 2026-11-05] Fichiers cachés (`.photo.JPG.JPG`, `._IMG.JPG`) et entrées spéciales (tubes, sockets) : l'outil ne les touche pas et ne les compte nulle part, alors que ta réponse 8a dit que ce qui est laissé de côté est compté et listé. Les lister ferait apparaître chaque `.DS_Store` et chaque `._` d'un disque exFAT. Proposition : les compter sans les lister (un seul nombre à l'aperçu et au journal). →
- [trust, 2026-11-05] Extensions connues : la casse seule ne corrige pas des formats courants hors liste, par exemple `x.CR3` (Canon), `x.RAF` (Fujifilm), `x.MTS` (caméscopes), `x.WMA`, `x.OPUS`, `x.3G2`, `x.ODG` ; seul un doublon (`x.CR3.CR3`) est corrigé ; une seconde attaque en relève d'autres : `ai`, `eps`, `aif`, `aiff`, `srt`, `tgz`, `bz2`, `xz`, `mid`, `pef`, `jpe`. Proposition : ajouter ces 18 extensions. →
- [trust, 2026-11-05] Bornes de la fusion : un doublon n'est fusionné que s'il est fait de lettres et chiffres ASCII (`x.été.été` et `x.final version.final version` restent tels quels), plus étroit que ta règle n°1 « quelle que soit l'extension ». Proposition : garder ces bornes (une partie avec accent ou espace est plus souvent un vrai nom qu'une extension cassée). →
- [trust, 2026-11-05] Ctrl-C à la question o/N : l'outil répond « Annulé. » et sort avec le code 0, alors que le SPEC dit « 130 après un Ctrl-C » (pensé pour l'application). Proposition : 130 aussi à la question, pour qu'un script sache que tu as interrompu. →

- [trust, 2026-11-05] Paquets macOS : la liste des dossiers-paquets jamais parcourus (`.app`, `.photoslibrary`, `.pages`…) est finie ; absents par exemple `.logicx` (Logic Pro), `.lrdata` (aperçus Lightroom), `.cocatalog` (Capture One), `.vmwarevm`, `.pvm` (machines virtuelles), `.dvdmedia`. Un fichier à extension cassée à l'intérieur de l'un d'eux serait renommé, ce qui peut abîmer le paquet. Proposition : ajouter ces 6 paquets. →
- [trust, 2026-11-05] Dates sur disque FAT32 et peut-être exFAT : sous macOS Sonoma, un renommage sur FAT32 garde la date sur le moment, puis macOS la remet à l'heure courante environ 5 secondes plus tard (fil Apple Developer Forums 759757, lu le 2026-11-05 ; un ingénieur Apple parle de régression, bug FB14464931) ; exFAT n'y est pas testé. L'outil ne peut pas l'empêcher, et cela vaut aussi pour la date des dossiers qu'il remet. Proposition : après ton essai exFAT du README (qui attend maintenant 15 secondes avant de relire les dates), si la date change, afficher un avertissement à l'aperçu sur ces disques avant la question o/N. →
## 4. Décidé sans toi — à revoir

> Une ligne par décision prise en ton absence : le choix, l'alternative écartée, la raison. Trois gestes possibles : tu la laisses (elle reste un défaut tacite), tu la graves en section 1 (elle devient loi), ou tu écris **NON** en fin de ligne (le prochain run la défait et repose la question en section 3).

- La liste d'extensions connues reste écrite dans le script, non réglable (élargie par ta réponse du 2026-11-05). Écarté : la rendre réglable. Raison : politique « sans nouvelle fonction » ; l'idée est au backlog. (SPEC, décision de gel n°1)
- `son.M4A.M4A` devient `son.m4a` : seule une partie faite uniquement de chiffres échappe à la fusion. Écarté : exclure toute extension contenant un chiffre. Raison : neuf extensions de photo, vidéo et audio (mp4, m4a, mp3, 3gp, 7z, cr2, m2ts, m4v, rw2) cesseraient d'être corrigées. Tranché à ta demande le 2026-11-05.
- La partie répétée doit être faite de lettres ASCII et de chiffres, avec au moins une lettre : `x.final version.final version` ou `x.été.été` ne sont pas fusionnés. Écarté : toute chaîne répétée. Raison : une chaîne avec espace ou accent est plus souvent un vrai nom qu'une extension cassée ; option minimale et réversible.
- Défaut grave trouvé et corrigé : sur Mac, l'outil passait le code `0x2` à l'appel système de renommage, qui veut dire « échanger les deux fichiers » et non « refuser si la cible existe » (`0x4`, vérifié dans le code source d'Apple). La v4.1.0 ne renommait donc sans doute rien sur ton Mac (déduit du code d'Apple, pas essayé sur un Mac). Écarté : rien, c'est un défaut. Raison : promesse « jamais d'écrasement ».
- Un dossier situé dans un paquet macOS ou une corbeille est refusé comme dossier de départ ; les photothèques iPhoto (`.photolibrary`) et la corbeille Windows (`$RECYCLE.BIN`) ne sont jamais parcourues ; un dossier système tapé dans une autre casse (`~/library`) est refusé. Écarté : s'en tenir au seul nom du dossier de départ. Raison : le SPEC promet de ne jamais toucher l'intérieur d'un paquet ni d'une corbeille.
- Ctrl-C, fermeture du Terminal ou arrêt système : l'arrêt attend la fin du fichier en cours. Écarté : laisser l'arrêt couper au milieu. Raison : 12 essais sur 40 laissaient un nom temporaire `__rename_tmp_*`.
- La suite de tests automatiques est déclarée « Linux », sautée sur Mac, et une vérification manuelle pour le Mac est écrite dans le README. Écarté : la rendre portable sans pouvoir l'essayer sur un Mac. Raison : une suite non essayée serait un faux vert.
- `a.JPG.jpg` devient `a.jpg`. Écarté : le laisser tel quel. Raison : c'était déjà le comportement. (n°2)
- Preuve « ce que tu vois est ce qui sera fait » : l'outil ne fait jamais rien hors de la liste montrée, mais peut en faire moins (abstention sur un cas douteux). Écarté : exiger qu'il fasse toute la liste. Raison : une abstention légitime rendrait cette preuve fausse. (n°4)
- *(Remplacée par ta réponse 1a du 2026-11-05, marbre n°2 : le doublon en fin de nom est fusionné.)* `IMG.2024.JPG.JPG` n'est corrigé que sur la casse (`IMG.2024.JPG.jpg`) : le doublon reste. Écarté : élargir la fusion. Raison : cela changerait le comportement sur des fichiers réels. (n°5)
- Date de création Finder et tags : non vérifiés (impossible sous Linux), déclarés à vérifier sur ton Mac. Écarté : les simuler, ou attendre le Mac. Raison : simuler serait un faux vert. (n°6)
- Six défauts de sûreté corrigés dans le code, plutôt que d'affaiblir les promesses pour coller au code. Raison : affaiblir une preuve est interdit. (n°7)
- Version 4.1.0. Écarté : rester en 4.0.0. Raison : le comportement change sur des cas limites. (n°8)
- Un lien symbolique (pas un alias Finder) porte déjà le nom visé, même cassé : l'outil ne renomme pas. Écarté : garder l'ancien test. Raison : deux cas reproduits effaçaient une entrée. (n°9)
- Journal : sur un autre disque si possible, sinon sur le même disque mais hors du dossier traité, avec un avertissement. Écarté : pas de journal du tout sur un Mac à un seul disque. Raison : le journal est le filet. (n°10)
- Retour arrière d'un renommage de casse raté : prouvé par un test simulé, pas sur un vrai disque insensible à la casse comme celui de ton Mac. Raison : la VM n'a pas ce type de disque. (n°11)
- Noms temporaires `__rename_tmp_*` : jamais laissés après un arrêt normal ou un Ctrl-C ; après une coupure de courant, signalés au lancement suivant. Écarté : promettre « jamais, quoi qu'il arrive ». Raison : aucun code ne survit à une coupure de courant. (n°12)
- Disques sans renommage sûr (exFAT, partages réseau) : l'outil renomme quand même, avec un avertissement que la protection anti-écrasement y est moins forte. Écarté : refuser d'y travailler. Raison : l'outil serait inutilisable sur tes disques externes. (n°13)
- Aucun journal n'a pu être écrit : la liste complète s'affiche d'office à l'écran. Écarté : bloquer, ou en dispenser le mode sans confirmation (`--oui`). Raison : tu dois voir tout ce qui sera fait. (n°14)
- Suffixe anti-collision placé avant toute l'extension, parties connues comprises : `a.tar.gz.gz` devient `a_2.tar.gz` si `a.tar.gz` existe (avant : `a.tar_2.gz`, que l'Utilitaire d'archives ne reconnaît plus). Écarté : garder le suffixe avant la seule dernière extension. Raison : le SPEC ne fixe pas la place, et une archive doit rester reconnue.
- Version 5.0.0 au lieu de 4.2.0 (jamais publiée). Écarté : 4.2.0. Raison : des noms que la v4.1.0 laissait tels quels sont maintenant corrigés et le code de sortie change, ce qui est un changement majeur selon la règle des numéros de version.
- Détails de mise en œuvre de tes réponses du 2026-11-05, chacun marqué dans le SPEC : la fusion de fin de nom garde les bornes de la règle (c) (chiffres seuls exclus, lettres et chiffres ASCII) ; un échec de remise de la date d'un dossier est signalé, pas bloquant ; les compagnons signalés sont `<nom complet>.<ext>`, `<radical>.xmp` de Lightroom et les liens symboliques de l'arborescence, pas les alias Finder ; code de sortie 0 malgré des abstentions de prudence, 1 pour une erreur ou un dossier illisible, 128 + numéro pour un arrêt par signal ; la liste des abandons s'affiche si elle tient en 40 lignes, sinon dans le journal ; l'outil de mutation tourne dans un environnement de la session, pas dans le harnais du kit.

## 5. État du chantier

> Écrit par le dernier run, verdict en première ligne. Le détail des preuves vit dans `dossier/proof.md` ; ici, seulement ce qui t'oriente.

**Verdict : SPEC prêt**

- Intention non validée par un humain : essaie le produit pour vérifier qu'il fait ce que tu voulais.
- Fait : tes dix réponses du 2026-11-05 appliquées au SPEC ; trois gravées en section 1.
- Reste : ship (coder tes réponses, mutation, preuves, attaques au niveau +++), puis send.
- Bloqué : rien.
- En attente de ton feu vert : le test des tags Finder sur exFAT, que tu as choisi de faire à la toute fin : sur ton Mac, dans un terminal, sur le disque exFAT, `cd /Volumes/TON_DISQUE && touch t.JPG.JPG && xattr -w user.test 1 t.JPG.JPG && python3 -c "import os; os.rename('t.JPG.JPG', 't.jpg')" && ls -a | grep 't\.' && xattr -l t.jpg` ; attendu : `._t.jpg` présent, aucun `._t.JPG.JPG`, et `user.test: 1`. Lance aussi la vérification Mac du README sur ce disque (un témoignage non vérifié dit que macOS y remet la date de modification à « maintenant »).

# BARRE — corriger-extensions

> **Le principe.** Ce fichier est le tien : c'est le seul que tu dois ouvrir. Tout ce qui attend un geste de ta part est ici, et rien d'autre. L'équipage (`/dev` : spec, ship, send) le lit avant chaque run, le tient à jour, et n'efface jamais une ligne que tu as écrite.
>
> **Le partage des rôles.** `SPEC.md` est le contrat technique, tenu pour l'équipage : tu peux le lire, tu n'as jamais à y intervenir. Ici, chaque section dit qui écrit et ce que ta réponse déclenche.

---

## 1. Gravé dans le marbre — tes volontés

> Tes décisions durables, une par ligne, numérotées à la suite. L'équipage les applique à chaque cycle sans les rediscuter. Un **NON** écrit ici est définitif : l'objet refusé ne te sera jamais reproposé (ses voisins restent permis). Pour changer d'avis, édite ou retire la ligne : le prochain run s'aligne. Une nouvelle volonté s'ajoute en fin de liste, sans renuméroter.

1. L'outil sert pour tous les types de fichiers : un doublon d'extension identique est fusionné et mis en minuscules quelle que soit l'extension (`b.ZIP.ZIP` devient `b.zip`), sauf s'il n'est fait que de chiffres (`version.1.1` reste intact) ; la casse seule n'est corrigée que pour les extensions connues, liste élargie aux formats courants (`c.XLSX` devient `c.xlsx`, `Notes.IMPORTANT` reste intact). (réponse du 2026-11-05, choix c)


## 2. Politiques en ton absence (`/dev auto`)

> Tes réponses données d'avance aux questions qui surgiraient pendant un run sans toi. Pour tout ce qui n'a pas de ligne ici, l'équipage prend le défaut le plus sûr et le consigne en section 4.

- features : SANS (MVP strict)
- parallele : OFF
- doute de périmètre : option minimale et réversible
- enjeu : … (+, ++ ou +++ ; prime sur le ++ par défaut ; vide, ++ s'applique quand tu lances toi-même en session, et une chasse sans toi n'attaque rien, sauf niveau fixé par le métier qui la lance ; ++++ ne se lit jamais ici)

## 3. ⚠ À TRANCHER — l'équipage attend ta décision

> Une décision par ligne : qui la pose, la question, la proposition de l'équipage, puis la flèche où tu réponds (un mot suffit : oui, non, un chiffre, un choix). Le prochain run lit ta réponse, l'applique, retire la ligne, et grave en section 1 ce qui mérite de durer. **Section vide : rien ne t'attend.** Tant qu'une ligne reste sans réponse, le SPEC n'est pas figé et rien ne part en production.

- [trust, 2026-11-05] Doublon en fin de nom : `IMG.2024.JPG.JPG`, `Vacances.2024.JPG.JPG` ou `Scan 12.5.PDF.PDF` gardent leur doublon (seule la casse finale change : `IMG.2024.JPG.jpg`), alors que ta règle n°1 dit qu'un doublon d'extension identique est fusionné. Fusionner aussi le doublon en fin de nom (`IMG.2024.jpg`), toujours sans fusionner les chiffres seuls (`version.1.1`) ? Proposition : oui. →
- [trust, 2026-11-05] Un `.jpeg` sain est renommé en `.jpg` (`photo.jpeg` devient `photo.jpg`), comportement hérité de la v4.0.0, alors que l'outil ne doit corriger que les doublons et les majuscules. Garder ce renommage ? Proposition : non, ne plus toucher un `.jpeg` seul (`X.JPEG` deviendrait `X.jpeg`) ; la fusion `photo.jpeg.jpg` en `photo.jpg` reste. →
- [trust, 2026-11-05] Renommer un fichier change la date de modification du dossier qui le contient (inévitable au niveau du disque) : un tri des dossiers par date dans le Finder en sera changé. Remettre la date d'origine des dossiers touchés après les renommages ? Proposition : oui. →
- [trust, 2026-11-05] Un dossier situé sous `Library` (par exemple iCloud Drive, `~/Library/Mobile Documents/com~apple~CloudDocs`) est accepté comme dossier à traiter ; un dossier situé dans un paquet ou une corbeille est désormais refusé. Refuser aussi tout dossier sous `Library` ? Proposition : non, iCloud Drive y vit. →
- [trust, 2026-11-05] Sur un disque exFAT, macOS range les tags Finder d'un fichier `x` dans un fichier caché `._x`, que l'outil ne touche jamais. Je n'ai pas pu vérifier sous Linux si macOS renomme le `._` avec son fichier ; sinon les tags d'un fichier corrigé seraient perdus. Test sur ton Mac, dans un terminal, sur le disque exFAT : `cd /Volumes/TON_DISQUE && touch t.JPG.JPG && xattr -w user.test 1 t.JPG.JPG && python3 -c "import os; os.rename('t.JPG.JPG', 't.jpg')" && ls -a | grep 't\.' && xattr -l t.jpg` ; attendu si tout va bien : `._t.jpg` présent, aucun `._t.JPG.JPG`, et `user.test: 1`. Proposition : tu lances ce test et tu colles la sortie ici. →

- [trust, 2026-11-05] Trois attaques de suite ont trouvé, en modifiant volontairement le code, des promesses du SPEC qu'aucun test ne protège vraiment (corrigées à chaque fois, mais il en reste : l'avertissement de repli exFAT à l'écran et son report au journal via le programme complet, la liste affichée en entier quand le journal ne peut pas s'écrire, l'identité du fichier par disque et numéro, le message « ignoré(s) »). La règle d'arrêt veut que cette cause, revenue trois fois, ne se répare plus au coup par coup. Proposition : au prochain cycle, installer un outil de mutation (mutmut) dans le harnais et combler tous les survivants en une passe. →
- [trust, 2026-11-05] Fichiers compagnons nommés d'après le fichier complet (`IMG.JPG.JPG.xmp` de darktable ou digiKam, `IMG.JPG.xmp` de Lightroom) : quand `IMG.JPG.JPG` devient `IMG.jpg`, son compagnon n'est ni renommé ni signalé, et le logiciel qui l'a écrit ne le retrouvera plus. Proposition : les signaler à l'aperçu et au journal, sans les renommer. →

## 4. Décidé sans toi — à revoir

> Une ligne par décision prise en ton absence : le choix, l'alternative écartée, la raison. Trois gestes possibles : tu la laisses (elle reste un défaut tacite), tu la graves en section 1 (elle devient loi), ou tu écris **NON** en fin de ligne (le prochain run la défait et repose la question en section 3).

- La liste d'extensions connues reste écrite dans le script, non réglable (élargie par ta réponse du 2026-11-05). Écarté : la rendre réglable. Raison : politique « sans nouvelle fonction » ; l'idée est au backlog. (SPEC, décision de gel n°1)
- `son.M4A.M4A` devient `son.m4a` : seule une partie faite uniquement de chiffres échappe à la fusion. Écarté : exclure toute extension contenant un chiffre. Raison : neuf extensions de photo, vidéo et audio (mp4, m4a, mp3, 3gp, 7z, cr2, m2ts, m4v, rw2) cesseraient d'être corrigées. Tranché à ta demande le 2026-11-05.
- La fusion « toute extension » ne joue que si toutes les parties après le premier point sont identiques : `IMG.2024.JPG.JPG` et `a.tar.gz.gz` gardent leur doublon (seule la casse finale change). Écarté : fusionner aussi un doublon en fin de nom. Raison : option minimale ; élargir changerait des noms comme `rapport.v2.v2` sans que tu l'aies vu. (SPEC, gel n°5)
- La partie répétée doit être faite de lettres ASCII et de chiffres, avec au moins une lettre : `x.final version.final version` ou `x.été.été` ne sont pas fusionnés. Écarté : toute chaîne répétée. Raison : une chaîne avec espace ou accent est plus souvent un vrai nom qu'une extension cassée ; option minimale et réversible.
- Version 4.2.0. Écarté : 4.1.1 ou 5.0.0. Raison : nouveauté compatible (semver mineur), aucun comportement existant ne change.
- `a.JPG.jpg` devient `a.jpg`. Écarté : le laisser tel quel. Raison : c'était déjà le comportement. (n°2)
- Preuve « ce que tu vois est ce qui sera fait » : l'outil ne fait jamais rien hors de la liste montrée, mais peut en faire moins (abstention sur un cas douteux). Écarté : exiger qu'il fasse toute la liste. Raison : une abstention légitime rendrait cette preuve fausse. (n°4)
- `IMG.2024.JPG.JPG` n'est corrigé que sur la casse (`IMG.2024.JPG.jpg`) : le doublon reste. Écarté : élargir la fusion. Raison : cela changerait le comportement sur des fichiers réels. (n°5)
- Date de création Finder et tags : non vérifiés (impossible sous Linux), déclarés à vérifier sur ton Mac. Écarté : les simuler, ou attendre le Mac. Raison : simuler serait un faux vert. (n°6)
- Six défauts de sûreté corrigés dans le code, plutôt que d'affaiblir les promesses pour coller au code. Raison : affaiblir une preuve est interdit. (n°7)
- Version 4.1.0. Écarté : rester en 4.0.0. Raison : le comportement change sur des cas limites. (n°8)
- Un lien symbolique (pas un alias Finder) porte déjà le nom visé, même cassé : l'outil ne renomme pas. Écarté : garder l'ancien test. Raison : deux cas reproduits effaçaient une entrée. (n°9)
- Journal : sur un autre disque si possible, sinon sur le même disque mais hors du dossier traité, avec un avertissement. Écarté : pas de journal du tout sur un Mac à un seul disque. Raison : le journal est le filet. (n°10)
- Retour arrière d'un renommage de casse raté : prouvé par un test simulé, pas sur un vrai disque insensible à la casse comme celui de ton Mac. Raison : la VM n'a pas ce type de disque. (n°11)
- Noms temporaires `__rename_tmp_*` : jamais laissés après un arrêt normal ou un Ctrl-C ; après une coupure de courant, signalés au lancement suivant. Écarté : promettre « jamais, quoi qu'il arrive ». Raison : aucun code ne survit à une coupure de courant. (n°12)
- Disques sans renommage sûr (exFAT, partages réseau) : l'outil renomme quand même, avec un avertissement que la protection anti-écrasement y est moins forte. Écarté : refuser d'y travailler. Raison : l'outil serait inutilisable sur tes disques externes. (n°13)
- Aucun journal n'a pu être écrit : la liste complète s'affiche d'office à l'écran. Écarté : bloquer, ou en dispenser le mode sans confirmation (`--oui`). Raison : tu dois voir tout ce qui sera fait. (n°14)

## 5. État du chantier

> Écrit par le dernier run, verdict en première ligne. Le détail des preuves vit dans `dossier/proof.md` ; ici, seulement ce qui t'oriente.

**Verdict : SPEC prêt**

- Intention non validée par un humain : essaie le produit sur un dossier-jouet pour vérifier qu'il fait ce que tu voulais.
- Fait : ta réponse (choix c) appliquée au SPEC le 2026-11-05 et gravée en section 1.
- Reste : ship (code, tests, preuves, attaque du code au niveau +++), puis send.
- Bloqué : rien.
- En attente de ton feu vert : rien.

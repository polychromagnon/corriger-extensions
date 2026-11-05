# BARRE — corriger-extensions

> **Le principe.** Ce fichier est le tien : c'est le seul que tu dois ouvrir. Tout ce qui attend un geste de ta part est ici, et rien d'autre. L'équipage (`/dev` : spec, ship, send) le lit avant chaque run, le tient à jour, et n'efface jamais une ligne que tu as écrite.
>
> **Le partage des rôles.** `SPEC.md` est le contrat technique, tenu pour l'équipage : tu peux le lire, tu n'as jamais à y intervenir. Ici, chaque section dit qui écrit et ce que ta réponse déclenche.

---

## 1. Gravé dans le marbre — tes volontés

> Tes décisions durables, une par ligne, numérotées à la suite. L'équipage les applique à chaque cycle sans les rediscuter. Un **NON** écrit ici est définitif : l'objet refusé ne te sera jamais reproposé (ses voisins restent permis). Pour changer d'avis, édite ou retire la ligne : le prochain run s'aligne. Une nouvelle volonté s'ajoute en fin de liste, sans renuméroter.


## 2. Politiques en ton absence (`/dev auto`)

> Tes réponses données d'avance aux questions qui surgiraient pendant un run sans toi. Pour tout ce qui n'a pas de ligne ici, l'équipage prend le défaut le plus sûr et le consigne en section 4.

- features : SANS (MVP strict)
- parallele : OFF
- doute de périmètre : option minimale et réversible
- enjeu : … (+, ++ ou +++ ; prime sur le ++ par défaut ; vide, ++ s'applique quand tu lances toi-même en session, et une chasse sans toi n'attaque rien, sauf niveau fixé par le métier qui la lance ; ++++ ne se lit jamais ici)

## 3. ⚠ À TRANCHER — l'équipage attend ta décision

> Une décision par ligne : qui la pose, la question, la proposition de l'équipage, puis la flèche où tu réponds (un mot suffit : oui, non, un chiffre, un choix). Le prochain run lit ta réponse, l'applique, retire la ligne, et grave en section 1 ce qui mérite de durer. **Section vide : rien ne t'attend.** Tant qu'une ligne reste sans réponse, le SPEC n'est pas figé et rien ne part en production.


- [Claude, 2026-11-05] La liste d'extensions connues (38 : photos, vidéos, audio, pdf, doc, docx, txt, rtf, aae) laisse tels quels tous les autres types : `b.ZIP.ZIP`, `c.XLSX`, `f.csv.csv` ne sont pas corrigés. Or tu as dit le 2026-11-05 que l'outil sert pour tous les fichiers. Proposition : élargir la liste aux formats courants (archives, bureautique, web, données). →

## 4. Décidé sans toi — à revoir

> Une ligne par décision prise en ton absence : le choix, l'alternative écartée, la raison. Trois gestes possibles : tu la laisses (elle reste un défaut tacite), tu la graves en section 1 (elle devient loi), ou tu écris **NON** en fin de ligne (le prochain run la défait et repose la question en section 3).

- Aucune nouvelle fonction ce cycle, dont la liste d'extensions connues, qui reste figée dans le script. Écarté : la rendre réglable. Raison : politique « sans nouvelle fonction » ; l'idée est au backlog. Décision prise avant que tu élargisses l'outil à tous les fichiers : voir la question en section 3. (SPEC, décisions de gel n°1 et 3)
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

- Fait : SPEC.md gelé, code v4.1.0 et tests au 2026-08-29 ; barre créée le 2026-11-05.
- Reste : ship (rejouer et compléter les preuves du SPEC, attaque du code).
- Bloqué : rien.
- En attente de ton feu vert : rien.

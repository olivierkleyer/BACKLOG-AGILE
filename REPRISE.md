# Reprise du projet Backlog Agile (note pour une nouvelle session)

## L'appli
Simulateur pedagogique de Scrum pour les cours d'Oli (ORSYS, EPITA). Flask + SQLAlchemy + SQLite, deploye sur Render (offre gratuite) depuis ce depot (branche `main`, deploiement automatique a chaque push).
- `app.py` : modeles, regles, routes. `exemple.py` : cas ROBO AGRI. `templates/` : pages Jinja.
- Comptes : `po` (Product Owner = formateur) et `dev1` a `dev10` (equipe). Mots de passe : variables Render `PO_PASSWORD`, `EQUIPE_PASSWORD`, `SECRET_KEY`.
- **Chaque deploiement (et chaque mise en veille Render) vide les donnees.** Parade : menu Sauvegarde (PO) -> fichier JSON a telecharger / restaurer.

## Regles de travail avec Oli
1. Oli teste et envoie ses remarques numerotees ; reponses en francais, concises, avis franc.
2. Developper et tester **en local**, montrer des captures.
3. **Pousser sur GitHub uniquement apres son « go »** (un push = redeploiement = donnees videes).
4. A chaque push : mettre a jour le **mode operatoire** (document Claude Docs « Backlog Agile – Mode operatoire »).
5. Commits signes `Olivier Kleyer <olivierkleyer@gmail.com>`.

## Parcours guide (fil conducteur « Mise en route », 9 etapes)
1 Regler le calendrier -> 2 Creer les releases -> 3 Creer les features -> 4 Ecrire les stories -> 5 Estimer et rendre pretes -> 6 Sprint planning -> 7 Jouer le sprint (Kanban) -> 8 Revue de sprint -> 9 Retrospective.
Menu : 1 Releases & sprints, 2 Product backlog, 3 Sprint planning, 4 Kanban (+ Vue globale), 5 Revue, 6 Retrospective ; admin : Produit DoR & DoD, Utilisateurs, Sauvegarde.

Principes UX decides avec Oli : accueil sur l'etape en cours ; affichage progressif (blocs des etapes passees replies en une ligne) ; remontee auto au bandeau quand une etape passe au vert ; etape en cours affichee en haut de l'ecran ; boutons avec verbes d'action (« + » reserve a « en ajouter une autre ») ; un seul bouton Enregistrer par page ; DoR et DoD **non bloquantes** par defaut (option formateur dans Produit, DoR & DoD) ; toute story peut se rattacher a toute autre ; RACI = lignes Acteur + Role (un seul A, au moins un R).

## Tests
`tests/e2e_parcours.py` joue tout le parcours (voir l'en-tete du fichier). A relancer apres chaque serie de modifications : 0 bug attendu.

## Pistes restantes (par priorite)
1. Planning poker (vote d'estimation secret puis revelation).
2. Perturbations declenchees par le formateur (bug urgent, absence = capacite reduite, changement de priorite).
3. Multi-equipes + vue formateur + base persistante payante : prerequis pour proposer l'outil a ORSYS / le commercialiser (a reprendre plus tard avec une etude de la concurrence).

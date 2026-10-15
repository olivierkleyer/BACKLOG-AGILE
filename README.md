# Backlog Agile — guide de déploiement

Application web issue du modèle Excel `backlog_exemple.xlsx` : product backlog
(Feature → Story → Tâche), fiche story, Kanban par sprint et planification des sprints.

## Structure

```
backlog_app/
├── app.py              ← application Flask
├── exemple.py          ← données de l'exemple ROBO AGRI
├── requirements.txt
├── Procfile
└── templates/
    ├── base.html, login.html
    ├── backlog.html     ← product backlog (onglet BACKLOG de l'Excel)
    ├── story.html       ← fiche story (onglet STORY de l'Excel), une par story
    ├── kanban.html      ← Kanban du sprint (glisser-déposer + boutons ‹ ›)
    ├── sprints.html     ← objectifs, capacité, charge, vélocité, stories non planifiées
    ├── parametres.html  ← nom, vision, nb de sprints (1-20), durée (1-6 sem.), DoD commune
    └── admin_users.html
```

## Déploiement sur Render (comme TDB-PROGRAMM)

1. Pousser le dossier sur un dépôt GitHub.
2. Render → **New Web Service** → connecter le dépôt.
   - Build : `pip install -r requirements.txt`
   - Start : `gunicorn app:app`
3. Base de données : copier l'*Internal Database URL* d'une base **PostgreSQL** Render dans `DATABASE_URL`.
   Render n'autorise qu'une base gratuite par compte : pour réutiliser celle de TDB-PROGRAMM, ajouter `DB_SCHEMA=backlog`.
4. Variables d'environnement :

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | Base PostgreSQL (sinon SQLite local, perdu à chaque redéploiement) |
| `SECRET_KEY` | Chaîne longue et aléatoire |
| `PO_PASSWORD` | Mot de passe initial du compte `po` |
| `EQUIPE_PASSWORD` | Mot de passe initial commun de `dev1` à `dev10` |
| `DB_SCHEMA` | Facultatif. Nom d'un schéma PostgreSQL (ex : `backlog`) pour partager une base existante — par exemple celle de TDB-PROGRAMM — sans mélanger les tables |

Sans `PO_PASSWORD` / `EQUIPE_PASSWORD`, des mots de passe aléatoires sont générés et affichés dans les logs Render.

## Test en local

```bash
pip install -r requirements.txt
python app.py        # http://localhost:5000
```

## Rôles

| Compte | Peut faire |
|---|---|
| `po` (Product Owner) | Tout : créer / renommer / ordonner / supprimer features et stories, rédiger la story (en tant que / besoin / pour, critères), priorité, paramètres, DoD commune, objectifs et capacité des sprints, comptes |
| `dev1` … `dev10` (équipe) | Estimation, responsable, statut, sprint, cases de DoD, DoD spécifique, tâches, déplacement des cartes du Kanban |

## Règles de gestion

- Estimation des stories en **points**, des tâches en **heures**.
- DoD bloquante (réglable dans *Produit & DoD*) : une story ne passe en « Fait » que si tous ses critères sont cochés. Désactivée, l'appli se contente d'un avertissement.
- Burndown du sprint (page Kanban), en points ou en heures, sur des **jours simulés** : le PO avance le jour (J1, J2…) après chaque daily scrum, ce qui permet de jouer un sprint de 2 semaines en une heure.
- Exemple ROBO AGRI (*Utilisateurs → Charger l'exemple*) : remplace le backlog par un cas prêt à l'emploi (`exemple.py`).
- Réduire le nombre de sprints renvoie les stories des sprints supprimés dans le backlog non planifié.
- Vélocité moyenne = moyenne des points « Fait » des sprints dont la date de fin est passée.
- Le Kanban se rafraîchit seul toutes les 20 s quand un autre participant déplace une carte.

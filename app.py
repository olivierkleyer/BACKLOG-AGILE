from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, abort
from datetime import datetime, timedelta, date
from collections import defaultdict
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json, os, re, secrets
from sqlalchemy import text

app = Flask(__name__)

# Cle de session : a definir dans les variables d'environnement Render (SECRET_KEY).
_secret = os.environ.get('SECRET_KEY')
if not _secret:
    print('ATTENTION : SECRET_KEY non definie, cle aleatoire temporaire utilisee.', flush=True)
    _secret = secrets.token_hex(32)
app.secret_key = _secret

# Base de donnees : PostgreSQL si DATABASE_URL est definie (Render), sinon SQLite en local.
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///backlog.db')
for _prefix in ('postgres://', 'postgresql://'):
    if _db_url.startswith(_prefix):
        _db_url = 'postgresql+psycopg2://' + _db_url[len(_prefix):]
        break
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
# DB_SCHEMA (facultatif) : range les tables dans un schema PostgreSQL dedie.
# Permet de partager une base existante (ex : celle de TDB-PROGRAMM) sans melanger les tables.
DB_SCHEMA = re.sub(r'[^a-z0-9_]', '', os.environ.get('DB_SCHEMA', '').lower())
if DB_SCHEMA and _db_url.startswith('postgresql'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS']['connect_args'] = {'options': '-csearch_path={}'.format(DB_SCHEMA)}
else:
    DB_SCHEMA = ''
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
app.permanent_session_lifetime = timedelta(hours=2)

# ---------------------------------------------------------------- Referentiels
STATUTS = ['A faire', 'En cours', 'Fait']
PRIORITES = ['P1', 'P2', 'P3']
SPRINTS_MAX = 20
DUREE_MIN, DUREE_MAX = 1, 6
DOR_COMMUNE_DEFAUT = [
    'Rédigée au format « En tant que… j\'ai besoin de… pour… »',
    "Critères d'acceptation définis",
    "Estimée par l'équipe",
    'Assez petite pour tenir dans un sprint',
    'Dépendances identifiées',
]
DOD_COMMUNE_DEFAUT = [
    'Code relu par un pair',
    'Tests unitaires écrits et passants',
    "Critères d'acceptation validés par le PO",
    'Documentation mise à jour',
]

def borne(v, mini, maxi, defaut=None):
    try: v = int(v)
    except (TypeError, ValueError): return defaut if defaut is not None else mini
    return max(mini, min(maxi, v))

def nombre(v, defaut=0.0):
    try: return max(0.0, round(float(str(v).replace(',', '.')), 1))
    except (TypeError, ValueError): return defaut

def statut_ok(v):
    return v if v in STATUTS else 'A faire'

def lire_json(txt, defaut):
    try:
        v = json.loads(txt or '')
        return v if isinstance(v, type(defaut)) else defaut
    except (TypeError, ValueError):
        return defaut

def fmt(n):
    """Affiche 3 plutot que 3.0"""
    return int(n) if float(n).is_integer() else n
app.jinja_env.filters['fmt'] = fmt

# ---------------------------------------------------------------- Modele
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='equipe')   # 'po' ou 'equipe'
    nom_complet = db.Column(db.String(120), default='')
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class Projet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), default='Mon produit')
    vision = db.Column(db.Text, default='')
    nb_sprints = db.Column(db.Integer, default=6)
    duree_semaines = db.Column(db.Integer, default=2)
    date_debut = db.Column(db.String(10), default='')     # AAAA-MM-JJ
    dod_commune_json = db.Column(db.Text, default='[]')
    dod_bloquante = db.Column(db.Boolean, default=True)    # une story ne passe en Fait que si sa DoD est complete
    dor_commune_json = db.Column(db.Text, default='[]')
    dor_bloquante = db.Column(db.Boolean, default=True)    # une story n'entre dans un sprint que si elle est prete

    @property
    def dod_commune(self): return lire_json(self.dod_commune_json, [])
    @property
    def dor_commune(self): return lire_json(self.dor_commune_json, [])

class Sprint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, unique=True, nullable=False)
    objectif = db.Column(db.Text, default='')
    capacite = db.Column(db.Float, default=0)             # en points
    jour_courant = db.Column(db.Integer, default=1)       # jour simule du sprint (burndown)

class Release(db.Model):
    """Une release regroupe des sprints consecutifs : R1 = sprints 1 a n1, R2 = n1+1 a n1+n2..."""
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(80), nullable=False)
    nb_sprints = db.Column(db.Integer, default=1)
    objectif = db.Column(db.Text, default='')
    ordre = db.Column(db.Integer, default=0)
    features = db.relationship('Feature', backref='release', lazy=True)

class Feature(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    release_id = db.Column(db.Integer, db.ForeignKey('release.id'), nullable=True)
    ordre = db.Column(db.Integer, default=0)
    stories = db.relationship('Story', backref='feature', cascade='all, delete-orphan', lazy=True)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feature_id = db.Column(db.Integer, db.ForeignKey('feature.id'), nullable=False)
    titre = db.Column(db.String(200), nullable=False)
    en_tant_que = db.Column(db.Text, default='')
    besoin = db.Column(db.Text, default='')
    pour = db.Column(db.Text, default='')
    criteres = db.Column(db.Text, default='')              # criteres d'acceptation
    statut = db.Column(db.String(20), default='A faire')
    fait_jour = db.Column(db.Integer, nullable=True)       # jour du sprint ou la story est passee en Fait
    responsable = db.Column(db.String(40), default='')
    priorite = db.Column(db.String(5), default='P2')
    points = db.Column(db.Float, default=0)
    sprint = db.Column(db.Integer, default=0)              # 0 = non planifiee
    dod_json = db.Column(db.Text, default='[]')            # DoD specifique [{label, ok}]
    dod_commune_ok_json = db.Column(db.Text, default='[]') # libelles de la DoD commune coches
    dor_ok_json = db.Column(db.Text, default='[]')         # libelles de la DoR cochés
    ordre = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    taches = db.relationship('Tache', backref='story', cascade='all, delete-orphan', lazy=True,
                             order_by='Tache.id')

    @property
    def dod(self): return lire_json(self.dod_json, [])
    @property
    def dod_commune_ok(self): return lire_json(self.dod_commune_ok_json, [])

    def heures(self): return sum(t.heures or 0 for t in self.taches)
    def heures_restantes(self): return sum(t.heures or 0 for t in self.taches if t.statut != 'Fait')

    @property
    def dor_ok(self): return lire_json(self.dor_ok_json, [])

    def dor_etat(self, dor_commune):
        ok = set(self.dor_ok)
        return sum(1 for l in dor_commune if l in ok), len(dor_commune)

    def est_prete(self, dor_commune):
        f, t = self.dor_etat(dor_commune)
        return f == t

    def dod_etat(self, dod_commune):
        """(cases cochees, cases totales) sur DoD commune + DoD specifique"""
        ok_c = set(self.dod_commune_ok)
        total = len(dod_commune) + len(self.dod)
        fait = sum(1 for l in dod_commune if l in ok_c) + sum(1 for d in self.dod if d.get('ok'))
        return fait, total

    def numero(self):
        return 'US-{:03d}'.format(self.id)

class Tache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('story.id'), nullable=False)
    titre = db.Column(db.String(200), nullable=False)
    heures = db.Column(db.Float, default=0)
    statut = db.Column(db.String(20), default='A faire')
    fait_jour = db.Column(db.Integer, nullable=True)
    responsable = db.Column(db.String(40), default='')

# ---------------------------------------------------------------- Initialisation
def get_projet():
    p = Projet.query.first()
    if not p:
        p = Projet(dod_commune_json=json.dumps(DOD_COMMUNE_DEFAUT), dor_commune_json=json.dumps(DOR_COMMUNE_DEFAUT),
                   date_debut=date.today().isoformat())
        db.session.add(p); db.session.commit()
    return p

def synchroniser_sprints(n):
    existants = {s.numero for s in Sprint.query.all()}
    for i in range(1, n + 1):
        if i not in existants:
            db.session.add(Sprint(numero=i))
    db.session.commit()

def init_db():
    if DB_SCHEMA:
        with db.engine.begin() as cx:
            cx.execute(text('CREATE SCHEMA IF NOT EXISTS "{}"'.format(DB_SCHEMA)))
    db.create_all()
    p = get_projet()
    synchroniser_sprints(p.nb_sprints)
    if User.query.count() == 0:
        po_pw = os.environ.get('PO_PASSWORD') or secrets.token_urlsafe(9)
        eq_pw = os.environ.get('EQUIPE_PASSWORD') or secrets.token_urlsafe(9)
        if not os.environ.get('PO_PASSWORD') or not os.environ.get('EQUIPE_PASSWORD'):
            print('Comptes crees. po : {} | dev1 a dev10 : {}'.format(po_pw, eq_pw), flush=True)
        u = User(username='po', role='po', nom_complet='Product Owner')
        u.set_password(po_pw); db.session.add(u)
        for i in range(1, 11):
            u = User(username='dev{}'.format(i), role='equipe', nom_complet='Équipe - dev {}'.format(i))
            u.set_password(eq_pw); db.session.add(u)
        db.session.commit()

with app.app_context():
    init_db()

# ---------------------------------------------------------------- Securite
login_attempts = defaultdict(lambda: {'count': 0, 'locked_until': None})

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '0.0.0.0').split(',')[0].strip()

def connecte(f):
    @wraps(f)
    def w(*a, **k):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*a, **k)
    return w

def po_requis(f):
    @wraps(f)
    def w(*a, **k):
        if 'user_id' not in session: return redirect(url_for('login'))
        if session.get('role') != 'po':
            flash('Action réservée au Product Owner', 'error')
            return redirect(request.referrer or url_for('backlog'))
        return f(*a, **k)
    return w

def est_po(): return session.get('role') == 'po'

@app.context_processor
def contexte():
    if 'user_id' not in session: return {}
    p = get_projet()
    return {'projet': p, 'est_po': est_po(), 'STATUTS': STATUTS, 'PRIORITES': PRIORITES,
            'parcours': parcours(p)}

def parcours(p):
    """Fil conducteur : les 6 etapes du PO et de l'equipe, avec la prochaine action."""
    stories = Story.query.all()
    pretes = [s for s in stories if s.points and s.est_prete(p.dor_commune)]
    a_affiner = next((s for s in stories if not (s.points and s.est_prete(p.dor_commune))), None)
    etapes = [
        {'n': 1, 'nom': 'Releases', 'ok': Release.query.count() > 0, 'po': True,
         'action': 'Créez une release et indiquez son nombre de sprints.',
         'lien': url_for('sprints') + '#releases', 'bouton': 'Créer une release'},
        {'n': 2, 'nom': 'Features', 'ok': Feature.query.count() > 0, 'po': True,
         'action': 'Créez une feature et rattachez-la à une release.',
         'lien': url_for('backlog') + '#nouvelle-feature', 'bouton': 'Créer une feature'},
        {'n': 3, 'nom': 'User stories', 'ok': len(stories) > 0, 'po': True,
         'action': 'Ajoutez des user stories dans une feature (champ « Nouvelle user story » sous la feature).',
         'lien': url_for('backlog'), 'bouton': 'Ajouter des stories'},
        {'n': 4, 'nom': 'Estimer et rendre prêtes', 'ok': len(pretes) > 0, 'po': False,
         'action': "Ouvrez chaque story : estimez-la en points et cochez sa Definition of Ready.",
         'lien': url_for('story', sid=a_affiner.id) if a_affiner else url_for('backlog'), 'bouton': 'Affiner une story'},
        {'n': 5, 'nom': 'Planifier le sprint', 'ok': any(s.sprint for s in stories), 'po': False,
         'action': 'Affectez les stories prêtes à un sprint (liste « Affecter à… »).',
         'lien': url_for('sprints') + '#non-planifiees', 'bouton': 'Planifier'},
        {'n': 6, 'nom': 'Jouer le sprint', 'ok': any(s.statut != 'A faire' for s in stories if s.sprint), 'po': False,
         'action': 'Faites avancer les cartes sur le Kanban ; le PO avance le jour après chaque daily.',
         'lien': url_for('kanban'), 'bouton': 'Ouvrir le Kanban'},
    ]
    courante = next((e for e in etapes if not e['ok']), None)
    return {'etapes': etapes, 'courante': courante}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = get_client_ip(); d = login_attempts[ip]
        if d['locked_until'] and datetime.utcnow() < d['locked_until']:
            flash('Trop de tentatives. Réessayez dans quelques minutes.', 'error')
            return render_template('login.html')
        u = User.query.filter_by(username=request.form.get('username', '').strip().lower()).first()
        if u and u.check_password(request.form.get('password', '')):
            login_attempts[ip] = {'count': 0, 'locked_until': None}
            session.permanent = True
            session['user_id'] = u.id; session['role'] = u.role; session['username'] = u.username
            return redirect(url_for('backlog'))
        d['count'] += 1
        if d['count'] >= 5:
            d['locked_until'] = datetime.utcnow() + timedelta(minutes=15); d['count'] = 0
        flash('Identifiant ou mot de passe incorrect', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/')
@connecte
def index(): return redirect(url_for('backlog'))

# ---------------------------------------------------------------- Calculs
def dates_sprint(p, numero):
    try: d0 = date.fromisoformat(p.date_debut)
    except (TypeError, ValueError): return None, None
    debut = d0 + timedelta(weeks=p.duree_semaines * (numero - 1))
    fin = debut + timedelta(weeks=p.duree_semaines) - timedelta(days=1)
    return debut, fin

def resume_sprints(p):
    stories = Story.query.all()
    sprints = Sprint.query.filter(Sprint.numero <= p.nb_sprints).order_by(Sprint.numero).all()
    out = []
    for s in sprints:
        st = [x for x in stories if x.sprint == s.numero]
        engage = sum(x.points or 0 for x in st)
        fait = sum(x.points or 0 for x in st if x.statut == 'Fait')
        debut, fin = dates_sprint(p, s.numero)
        out.append({'sprint': s, 'nb': len(st), 'engage': engage, 'fait': fait,
                    'debut': debut, 'fin': fin,
                    'charge_pct': round(100 * engage / s.capacite) if s.capacite else None})
    return out

def calendrier_releases(p):
    """Pour chaque release : sprints couverts, dates, points. Les releases s'enchainent dans l'ordre."""
    out, cumul = [], 0
    for r in Release.query.order_by(Release.ordre, Release.id).all():
        s1, s2 = cumul + 1, cumul + r.nb_sprints
        cumul = s2
        debut, _ = dates_sprint(p, s1)
        _, fin = dates_sprint(p, s2)
        stories = [s for f in r.features for s in f.stories]
        pts = sum(s.points or 0 for s in stories)
        fait = sum(s.points or 0 for s in stories if s.statut == 'Fait')
        hors = [s for s in stories if s.sprint and not (s1 <= s.sprint <= s2)]
        out.append({'r': r, 'i': len(out), 's1': s1, 's2': s2, 'debut': debut, 'fin': fin,
                    'depasse': s2 > p.nb_sprints, 'points': pts, 'fait': fait,
                    'nb_stories': len(stories), 'hors': hors,
                    'pct': round(100 * fait / pts) if pts else 0})
    return out

def sprints_des_releases():
    return sum(r.nb_sprints or 0 for r in Release.query.all())

def caler_calendrier(p):
    """Le calendrier couvre toujours toutes les releases : il s'allonge si besoin.
    Renvoie un message d'erreur si les releases depassent le maximum (rien n'est alors enregistre)."""
    total = sprints_des_releases()
    if total > SPRINTS_MAX:
        db.session.rollback()
        return 'Les releases demanderaient {} sprints : le maximum est {}. Modification annulée.'.format(total, SPRINTS_MAX)
    if total > p.nb_sprints:
        p.nb_sprints = total
        db.session.commit()
        synchroniser_sprints(total)
        _, fin = dates_sprint(p, total)
        flash('Le calendrier passe à {} sprints pour couvrir les releases{}.'.format(
            total, ' (fin le {})'.format(fin.strftime('%d/%m/%Y')) if fin else ''), 'success')
    db.session.commit()
    return None

def release_du_sprint(cal, n):
    return next((c for c in cal if c['s1'] <= n <= c['s2']), None)

def jours_sprint(p):
    return p.duree_semaines * 5   # jours ouvres

def jour_du_sprint(n):
    sp = Sprint.query.filter_by(numero=n).first() if n else None
    return sp.jour_courant if sp else None

def changer_statut_story(s, nouveau, p):
    """Applique la regle de la DoD bloquante. Renvoie un message d'erreur ou None."""
    nouveau = statut_ok(nouveau)
    if nouveau == 'Fait' and s.statut != 'Fait' and p.dod_bloquante:
        fait, total = s.dod_etat(p.dod_commune)
        if fait < total:
            return 'Impossible de passer « {} » en Fait : Définition du Fini incomplète ({}/{}).'.format(s.titre, fait, total)
    if nouveau == 'Fait' and s.statut != 'Fait':
        s.fait_jour = jour_du_sprint(s.sprint)
        for t in s.taches:            # une story finie solde ses taches restantes
            if t.statut != 'Fait':
                t.statut = 'Fait'; t.fait_jour = s.fait_jour
    elif nouveau != 'Fait':
        s.fait_jour = None
    s.statut = nouveau
    return None

def affecter_sprint(s, n, p):
    """Affecte une story a un sprint (0 = backlog) en appliquant la DoR bloquante. Renvoie une erreur ou None."""
    if n and n != s.sprint and p.dor_bloquante and not s.est_prete(p.dor_commune):
        f, t = s.dor_etat(p.dor_commune)
        return "« {} » n'est pas prête (Definition of Ready {}/{}) : elle ne peut pas entrer dans un sprint.".format(s.titre, f, t)
    if s.statut == 'Fait' and n != s.sprint:
        s.fait_jour = jour_du_sprint(n)
    s.sprint = n
    return None

def changer_statut_tache(t, nouveau):
    nouveau = statut_ok(nouveau)
    if nouveau == 'Fait' and t.statut != 'Fait':
        t.fait_jour = jour_du_sprint(t.story.sprint)
    elif nouveau != 'Fait':
        t.fait_jour = None
    t.statut = nouveau

def burndown(p, n):
    """Reste a faire en fin de chaque jour simule du sprint, en points (stories) et en heures (taches)."""
    sp = Sprint.query.filter_by(numero=n).first()
    d = jours_sprint(p)
    jour = min(max(sp.jour_courant or 1, 1), d) if sp else 1
    stories = Story.query.filter_by(sprint=n).all()
    taches = [t for s in stories for t in s.taches]
    def serie(items, poids):
        total = sum(poids(x) for x in items)
        reel = []
        for j in range(0, jour + 1):
            fait = sum(poids(x) for x in items if x.statut == 'Fait' and j > 0 and (x.fait_jour or 1) <= j)
            reel.append(round(total - fait, 1))
        return {'total': round(total, 1), 'reel': reel}
    return {'jours': d, 'jour': jour,
            'points': serie(stories, lambda x: x.points or 0),
            'heures': serie(taches, lambda x: x.heures or 0)}

def responsables_connus():
    noms = set()
    for s in Story.query.all():
        if s.responsable: noms.add(s.responsable)
        for t in s.taches:
            if t.responsable: noms.add(t.responsable)
    return sorted(noms)

# ---------------------------------------------------------------- Backlog
@app.route('/backlog')
@connecte
def backlog():
    p = get_projet()
    features = Feature.query.order_by(Feature.ordre, Feature.id).all()
    filtre_sprint = request.args.get('sprint', '')
    filtre_statut = request.args.get('statut', '')
    filtre_release = request.args.get('release', '')
    if filtre_release == '0':
        features = [f for f in features if not f.release_id]
    elif filtre_release:
        features = [f for f in features if str(f.release_id) == filtre_release]
    cal = {c['r'].id: c for c in calendrier_releases(p)}
    prio_rang = {k: i for i, k in enumerate(PRIORITES)}
    blocs = []
    for f in features:
        st = sorted(f.stories, key=lambda s: (prio_rang.get(s.priorite, 9), s.ordre, s.id))
        if filtre_sprint != '':
            st = [s for s in st if str(s.sprint) == filtre_sprint]
        if filtre_statut:
            st = [s for s in st if s.statut == filtre_statut]
        blocs.append({'f': f, 'stories': st, 'cal': cal.get(f.release_id),
                      'points': sum(s.points or 0 for s in f.stories),
                      'fait': sum(s.points or 0 for s in f.stories if s.statut == 'Fait')})
    toutes = Story.query.all()
    stats = {'stories': len(toutes),
             'points': sum(s.points or 0 for s in toutes),
             'fait': sum(s.points or 0 for s in toutes if s.statut == 'Fait'),
             'non_planifiees': sum(1 for s in toutes if not s.sprint),
             'non_estimees': sum(1 for s in toutes if not s.points)}
    return render_template('backlog.html', blocs=blocs, stats=stats, dod_commune=p.dod_commune, dor_commune=p.dor_commune,
                           filtre_sprint=filtre_sprint, filtre_statut=filtre_statut, filtre_release=filtre_release,
                           releases=Release.query.order_by(Release.ordre, Release.id).all(),
                           responsables=responsables_connus())

def release_valide(v):
    try: v = int(v)
    except (TypeError, ValueError): return None
    return v if db.session.get(Release, v) else None

@app.route('/feature/ajouter', methods=['POST'])
@po_requis
def feature_ajouter():
    nom = request.form.get('nom', '').strip()
    if nom:
        ordre = (db.session.query(db.func.max(Feature.ordre)).scalar() or 0) + 1
        db.session.add(Feature(nom=nom[:200], release_id=release_valide(request.form.get('release_id')), ordre=ordre))
        db.session.commit()
    return redirect(url_for('backlog'))

@app.route('/feature/<int:fid>/modifier', methods=['POST'])
@po_requis
def feature_modifier(fid):
    f = db.get_or_404(Feature, fid)
    nom = request.form.get('nom', '').strip()
    if nom: f.nom = nom[:200]
    f.release_id = release_valide(request.form.get('release_id'))
    db.session.commit()
    return redirect(url_for('backlog'))

@app.route('/feature/<int:fid>/deplacer/<sens>', methods=['POST'])
@po_requis
def feature_deplacer(fid, sens):
    fs = Feature.query.order_by(Feature.ordre, Feature.id).all()
    i = next((k for k, f in enumerate(fs) if f.id == fid), None)
    j = i - 1 if sens == 'haut' else i + 1
    if i is not None and 0 <= j < len(fs):
        fs[i], fs[j] = fs[j], fs[i]
        for k, f in enumerate(fs): f.ordre = k
        db.session.commit()
    return redirect(url_for('backlog'))

@app.route('/feature/<int:fid>/supprimer', methods=['POST'])
@po_requis
def feature_supprimer(fid):
    f = db.get_or_404(Feature, fid)
    db.session.delete(f); db.session.commit()
    flash('Feature « {} » supprimée avec ses stories'.format(f.nom), 'success')
    return redirect(url_for('backlog'))

@app.route('/story/ajouter', methods=['POST'])
@po_requis
def story_ajouter():
    f = db.get_or_404(Feature, request.form.get('feature_id', type=int))
    titre = request.form.get('titre', '').strip()
    if not titre:
        return redirect(url_for('backlog'))
    s = Story(feature_id=f.id, titre=titre[:200],
              priorite=request.form.get('priorite') if request.form.get('priorite') in PRIORITES else 'P2')
    db.session.add(s); db.session.commit()
    return redirect(url_for('story', sid=s.id))

# ---------------------------------------------------------------- Fiche story
@app.route('/story/<int:sid>', methods=['GET', 'POST'])
@connecte
def story(sid):
    s = db.get_or_404(Story, sid)
    p = get_projet()
    if request.method == 'POST':
        fm = request.form
        if est_po():
            s.titre = (fm.get('titre', '').strip() or s.titre)[:200]
            s.en_tant_que = fm.get('en_tant_que', '').strip()
            s.besoin = fm.get('besoin', '').strip()
            s.pour = fm.get('pour', '').strip()
            s.criteres = fm.get('criteres', '').strip()
            if fm.get('priorite') in PRIORITES: s.priorite = fm.get('priorite')
            fid = fm.get('feature_id', type=int)
            if fid and db.session.get(Feature, fid): s.feature_id = fid
        s.responsable = fm.get('responsable', '').strip().upper()[:40]
        s.points = nombre(fm.get('points'))
        s.dor_ok_json = json.dumps([l for i, l in enumerate(p.dor_commune) if fm.get('dorc_{}'.format(i))])
        erreur_dor = affecter_sprint(s, borne(fm.get('sprint'), 0, p.nb_sprints, 0), p)
        # DoD commune : cases cochees
        s.dod_commune_ok_json = json.dumps([l for i, l in enumerate(p.dod_commune) if fm.get('dodc_{}'.format(i))])
        # DoD specifique : libelles + cases
        dod = []
        for i, label in enumerate(fm.getlist('dod_label')):
            label = label.strip()
            if label:
                dod.append({'label': label[:200], 'ok': bool(fm.get('dod_ok_{}'.format(i)))})
        nouveau = fm.get('dod_nouveau', '').strip()
        if nouveau: dod.append({'label': nouveau[:200], 'ok': False})
        s.dod_json = json.dumps(dod)
        erreur = changer_statut_story(s, fm.get('statut'), p)
        s.updated_at = datetime.utcnow()
        db.session.commit()
        fait, total = s.dod_etat(p.dod_commune)
        if erreur or erreur_dor:
            flash(' '.join(e for e in (erreur_dor, erreur) if e) + ' Les autres modifications sont enregistrées.', 'error')
        elif s.statut == 'Fait' and fait < total:
            flash('Story enregistrée en « Fait » alors que la Définition du Fini n\'est pas complète ({}/{})'.format(fait, total), 'error')
        else:
            flash('Story enregistrée', 'success')
        return redirect(url_for('story', sid=s.id))
    # navigation precedente / suivante dans l'ordre du backlog
    prio_rang = {k: i for i, k in enumerate(PRIORITES)}
    ordre = []
    for f in Feature.query.order_by(Feature.ordre, Feature.id).all():
        ordre += [x.id for x in sorted(f.stories, key=lambda x: (prio_rang.get(x.priorite, 9), x.ordre, x.id))]
    i = ordre.index(s.id)
    prec = ordre[i - 1] if i > 0 else None
    suiv = ordre[i + 1] if i < len(ordre) - 1 else None
    cal = next((c for c in calendrier_releases(p) if c['r'].id == s.feature.release_id), None)
    return render_template('story.html', s=s, dod_commune=p.dod_commune, prec=prec, suiv=suiv, cal=cal,
                           features=Feature.query.order_by(Feature.ordre, Feature.id).all(),
                           responsables=responsables_connus(), dod=s.dod_etat(p.dod_commune),
                           dor_commune=p.dor_commune, dor=s.dor_etat(p.dor_commune))

@app.route('/story/<int:sid>/supprimer', methods=['POST'])
@po_requis
def story_supprimer(sid):
    s = db.get_or_404(Story, sid)
    db.session.delete(s); db.session.commit()
    flash('Story « {} » supprimée'.format(s.titre), 'success')
    return redirect(url_for('backlog'))

@app.route('/story/<int:sid>/tache', methods=['POST'])
@connecte
def tache_ajouter(sid):
    s = db.get_or_404(Story, sid)
    titre = request.form.get('titre', '').strip()
    if titre:
        db.session.add(Tache(story_id=s.id, titre=titre[:200], heures=nombre(request.form.get('heures')),
                             responsable=request.form.get('responsable', '').strip().upper()[:40]))
        db.session.commit()
    return redirect(url_for('story', sid=s.id) + '#taches')

@app.route('/tache/<int:tid>/modifier', methods=['POST'])
@connecte
def tache_modifier(tid):
    t = db.get_or_404(Tache, tid)
    if request.form.get('supprimer'):
        sid = t.story_id; db.session.delete(t); db.session.commit()
        return redirect(url_for('story', sid=sid) + '#taches')
    t.titre = (request.form.get('titre', '').strip() or t.titre)[:200]
    t.heures = nombre(request.form.get('heures'))
    changer_statut_tache(t, request.form.get('statut'))
    t.responsable = request.form.get('responsable', '').strip().upper()[:40]
    db.session.commit()
    return redirect(url_for('story', sid=t.story_id) + '#taches')

# ---------------------------------------------------------------- Kanban
@app.route('/kanban')
@connecte
def kanban():
    p = get_projet()
    n = borne(request.args.get('sprint'), 1, p.nb_sprints, 1)
    sp = Sprint.query.filter_by(numero=n).first()
    stories = Story.query.filter_by(sprint=n).all()
    prio_rang = {k: i for i, k in enumerate(PRIORITES)}
    stories.sort(key=lambda s: (prio_rang.get(s.priorite, 9), s.ordre, s.id))
    colonnes = {st: [s for s in stories if s.statut == st] for st in STATUTS}
    engage = sum(s.points or 0 for s in stories)
    fait = sum(s.points or 0 for s in stories if s.statut == 'Fait')
    debut, fin = dates_sprint(p, n)
    return render_template('kanban.html', n=n, sp=sp, colonnes=colonnes, engage=engage, fait=fait,
                           bd=burndown(p, n), dod_bloquante=p.dod_bloquante,
                           debut=debut, fin=fin, dod_commune=p.dod_commune,
                           sprints=resume_sprints(p), rel=release_du_sprint(calendrier_releases(p), n),
                           non_planifiees=Story.query.filter_by(sprint=0).count())

@app.route('/api/story/<int:sid>/statut', methods=['POST'])
@connecte
def api_statut(sid):
    s = db.get_or_404(Story, sid)
    p = get_projet()
    d = request.get_json(silent=True) or {}
    erreur = changer_statut_story(s, d.get('statut'), p)
    if erreur:
        return jsonify({'ok': False, 'erreur': erreur}), 409
    s.updated_at = datetime.utcnow()
    db.session.commit()
    fait, total = s.dod_etat(p.dod_commune)
    return jsonify({'ok': True, 'statut': s.statut, 'dod_fait': fait, 'dod_total': total,
                    'burndown': burndown(p, s.sprint) if s.sprint else None})

@app.route('/api/kanban/<int:n>')
@connecte
def api_kanban(n):
    """Etat du sprint pour le rafraichissement automatique du tableau"""
    return jsonify({'statuts': {str(s.id): s.statut for s in Story.query.filter_by(sprint=n).all()},
                    'jour': jour_du_sprint(n)})

@app.route('/sprint/<int:n>/jour', methods=['POST'])
@po_requis
def sprint_jour(n):
    p = get_projet()
    sp = Sprint.query.filter_by(numero=n).first_or_404()
    sens = 1 if request.form.get('sens') == '+' else -1
    sp.jour_courant = min(max((sp.jour_courant or 1) + sens, 1), jours_sprint(p))
    db.session.commit()
    return redirect(url_for('kanban', sprint=n))

# ---------------------------------------------------------------- Sprints & parametres
@app.route('/sprints', methods=['GET', 'POST'])
@connecte
def sprints():
    p = get_projet()
    if request.method == 'POST':
        if not est_po():
            flash('Action réservée au Product Owner', 'error'); return redirect(url_for('sprints'))
        fm = request.form
        if fm.get('section') == 'calendrier':
            nb = borne(fm.get('nb_sprints'), 1, SPRINTS_MAX, p.nb_sprints)
            mini = sprints_des_releases()
            if nb < mini:
                flash('Le calendrier ne peut pas descendre sous {} sprints : les releases en couvrent {}. '
                      'Réduisez d\'abord une release (bloc Releases ci-dessous).'.format(mini, mini), 'error')
                nb = mini
            orphelines = Story.query.filter(Story.sprint > nb).count()
            if orphelines:
                Story.query.filter(Story.sprint > nb).update({'sprint': 0})
                flash('{} story(s) des sprints supprimés sont revenues dans le backlog non planifié'.format(orphelines), 'error')
            p.nb_sprints = nb
            p.duree_semaines = borne(fm.get('duree_semaines'), DUREE_MIN, DUREE_MAX, p.duree_semaines)
            try: p.date_debut = date.fromisoformat(fm.get('date_debut', '')).isoformat()
            except ValueError: pass
            db.session.commit()
            synchroniser_sprints(p.nb_sprints)
            flash('Calendrier enregistré', 'success')
            return redirect(url_for('sprints'))
        if fm.get('section') == 'releases':
            for r in Release.query.all():
                nom = fm.get('rel_nom_{}'.format(r.id), '').strip()
                if nom: r.nom = nom[:80]
                r.nb_sprints = borne(fm.get('rel_nb_{}'.format(r.id)), 1, SPRINTS_MAX, r.nb_sprints)
                r.objectif = fm.get('rel_obj_{}'.format(r.id), '').strip()
            erreur = caler_calendrier(p)
            flash(erreur or 'Releases enregistrées', 'error' if erreur else 'success')
            return redirect(url_for('sprints') + '#releases')
        for s in Sprint.query.filter(Sprint.numero <= p.nb_sprints).all():
            s.objectif = fm.get('objectif_{}'.format(s.numero), '').strip()
            s.capacite = nombre(fm.get('capacite_{}'.format(s.numero)))
        db.session.commit()
        flash('Sprints enregistrés', 'success')
        return redirect(url_for('sprints'))
    rs = resume_sprints(p)
    termines = [r for r in rs if r['fin'] and r['fin'] < date.today()]
    velocite = round(sum(r['fait'] for r in termines) / len(termines), 1) if termines else None
    prio_rang = {k: i for i, k in enumerate(PRIORITES)}
    np = sorted(Story.query.filter_by(sprint=0).all(), key=lambda s: (prio_rang.get(s.priorite, 9), s.feature.ordre, s.id))
    cal = calendrier_releases(p)
    for r in rs: r['release'] = release_du_sprint(cal, r['sprint'].numero)
    return render_template('sprints.html', sprints=rs, non_planifiees=np, velocite=velocite, dor_commune=p.dor_commune,
                           dor_bloquante=p.dor_bloquante,
                           nb_termines=len(termines), aujourdhui=date.today(), cal=cal,
                           sprints_releases=sum(c['r'].nb_sprints for c in cal),
                           SPRINTS_MAX=SPRINTS_MAX, DUREE_MIN=DUREE_MIN, DUREE_MAX=DUREE_MAX)

@app.route('/release/ajouter', methods=['POST'])
@po_requis
def release_ajouter():
    nom = request.form.get('nom', '').strip()
    if nom:
        ordre = (db.session.query(db.func.max(Release.ordre)).scalar() or 0) + 1
        db.session.add(Release(nom=nom[:80], nb_sprints=borne(request.form.get('nb_sprints'), 1, SPRINTS_MAX, 1),
                               objectif=request.form.get('objectif', '').strip(), ordre=ordre))
        erreur = caler_calendrier(get_projet())
        if erreur: flash(erreur, 'error')
    return redirect(url_for('sprints') + '#releases')

@app.route('/release/<int:rid>/deplacer/<sens>', methods=['POST'])
@po_requis
def release_deplacer(rid, sens):
    rs = Release.query.order_by(Release.ordre, Release.id).all()
    i = next((k for k, r in enumerate(rs) if r.id == rid), None)
    j = i - 1 if sens == 'haut' else i + 1
    if i is not None and 0 <= j < len(rs):
        rs[i], rs[j] = rs[j], rs[i]
        for k, r in enumerate(rs): r.ordre = k
        db.session.commit()
    return redirect(url_for('sprints') + '#releases')

@app.route('/release/<int:rid>/supprimer', methods=['POST'])
@po_requis
def release_supprimer(rid):
    r = db.get_or_404(Release, rid)
    for f in r.features: f.release_id = None
    db.session.delete(r); db.session.commit()
    flash('Release « {} » supprimée (ses features sont conservées, sans release)'.format(r.nom), 'success')
    return redirect(url_for('sprints') + '#releases')

@app.route('/story/<int:sid>/sprint', methods=['POST'])
@connecte
def story_sprint(sid):
    s = db.get_or_404(Story, sid)
    p = get_projet()
    erreur = affecter_sprint(s, borne(request.form.get('sprint'), 0, p.nb_sprints, 0), p)
    if erreur:
        flash(erreur + ' Complétez sa DoR sur la fiche story.', 'error')
    db.session.commit()
    return redirect(url_for('sprints') + '#non-planifiees')

@app.route('/parametres', methods=['GET', 'POST'])
@po_requis
def parametres():
    p = get_projet()
    if request.method == 'POST':
        fm = request.form
        p.nom = (fm.get('nom', '').strip() or p.nom)[:200]
        p.vision = fm.get('vision', '').strip()
        dod = [l.strip()[:200] for l in fm.get('dod_commune', '').splitlines() if l.strip()]
        p.dod_commune_json = json.dumps(dod)
        p.dod_bloquante = bool(fm.get('dod_bloquante'))
        p.dor_commune_json = json.dumps([l.strip()[:200] for l in fm.get('dor_commune', '').splitlines() if l.strip()])
        p.dor_bloquante = bool(fm.get('dor_bloquante'))
        db.session.commit()
        flash('Paramètres enregistrés', 'success')
        return redirect(url_for('parametres'))
    return render_template('parametres.html')

# ---------------------------------------------------------------- Administration
@app.route('/admin/users')
@po_requis
def admin_users():
    return render_template('admin_users.html', users=User.query.order_by(User.id).all())

@app.route('/admin/users/<int:uid>/password', methods=['POST'])
@po_requis
def change_password(uid):
    u = db.get_or_404(User, uid)
    pw = request.form.get('password', '')
    if len(pw) >= 4:
        u.set_password(pw); db.session.commit(); flash('Mot de passe de {} mis à jour'.format(u.username), 'success')
    else:
        flash('Mot de passe trop court (4 caractères minimum)', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/reset-passwords', methods=['POST'])
@po_requis
def reset_passwords():
    pw = request.form.get('new_password', '').strip()
    if len(pw) < 4:
        flash('Mot de passe trop court (4 caractères minimum)', 'error')
    else:
        for u in User.query.filter_by(role='equipe').all(): u.set_password(pw)
        db.session.commit(); flash("Mot de passe commun de l'équipe mis à jour", 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/reset', methods=['POST'])
@po_requis
def reset_all():
    if request.form.get('confirmation', '').strip().upper() != 'VIDER':
        flash('Tapez VIDER pour confirmer la réinitialisation', 'error')
        return redirect(url_for('admin_users'))
    Tache.query.delete(); Story.query.delete(); Feature.query.delete(); Release.query.delete()
    for s in Sprint.query.all(): s.objectif = ''; s.capacite = 0; s.jour_courant = 1
    db.session.commit()
    flash('Backlog vidé : releases, features, stories et tâches supprimées', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/exemple', methods=['POST'])
@po_requis
def charger_exemple():
    """Remplace le backlog par le cas ROBO AGRI (voir exemple.py)."""
    import exemple as ex
    if request.form.get('confirmation', '').strip().upper() != 'EXEMPLE':
        flash("Tapez EXEMPLE pour confirmer le chargement de l'exemple", 'error')
        return redirect(url_for('admin_users'))
    Tache.query.delete(); Story.query.delete(); Feature.query.delete(); Release.query.delete()
    p = get_projet()
    p.nom = ex.PRODUIT['nom']; p.vision = ex.PRODUIT['vision']
    p.nb_sprints = ex.PRODUIT['nb_sprints']; p.duree_semaines = ex.PRODUIT['duree_semaines']
    lundi = date.today() - timedelta(days=date.today().weekday())
    p.date_debut = lundi.isoformat()
    p.dod_commune_json = json.dumps(ex.DOD_COMMUNE)
    p.dor_commune_json = json.dumps(ex.DOR_COMMUNE)
    db.session.commit()
    synchroniser_sprints(p.nb_sprints)
    for sp in Sprint.query.all():
        cfg = ex.SPRINTS.get(sp.numero, {})
        sp.objectif = cfg.get('objectif', ''); sp.capacite = cfg.get('capacite', 0); sp.jour_courant = 1
    releases = []
    for i, r in enumerate(ex.RELEASES):
        rel = Release(nom=r['nom'], nb_sprints=r['nb_sprints'], objectif=r['objectif'], ordre=i)
        db.session.add(rel); releases.append(rel)
    db.session.flush()
    for i, f in enumerate(ex.FEATURES):
        feat = Feature(nom=f['nom'], release_id=releases[f['release']].id, ordre=i)
        db.session.add(feat); db.session.flush()
        for k, (titre, qui, besoin, pour, crit, prio, pts, spr, dod, taches) in enumerate(f['stories']):
            st = Story(feature_id=feat.id, titre=titre, en_tant_que=qui, besoin=besoin, pour=pour, criteres=crit,
                       priorite=prio, points=pts, sprint=spr, ordre=k,
                       dod_json=json.dumps([{'label': l, 'ok': False} for l in dod]),
                       dor_ok_json=json.dumps(ex.dor_cochee(crit, pts, spr)))
            db.session.add(st); db.session.flush()
            for t, h in taches:
                db.session.add(Tache(story_id=st.id, titre=t, heures=h))
    db.session.commit()
    flash('Exemple ROBO AGRI chargé : sprint 1 prêt à démarrer, le reste du backlog est à estimer et à planifier.', 'success')
    return redirect(url_for('backlog'))

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))

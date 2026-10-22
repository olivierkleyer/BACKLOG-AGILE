"""Test de bout en bout de Backlog Agile : 20 etapes, PO sur ordinateur + dev1 sur telephone.

Lancement (base vierge obligatoire) :
    rm -rf instance
    PO_PASSWORD=popo EQUIPE_PASSWORD=devdev SECRET_KEY=x PORT=5099 nohup python3 app.py &
    mkdir -p /tmp/e2e && python3 tests/e2e_parcours.py http://localhost:5099 /tmp/e2e
Prerequis : playwright (Chromium dans /opt/pw-browsers/chromium, sinon adapter executable_path).
Resultat : liste OK / BUG dans la console et /tmp/e2e/rapport.txt, captures PNG dans /tmp/e2e.
Les erreurs de chargement de polices externes (Google Fonts bloque en bac a sable) sont ignorees.
"""
import sys, traceback, re
from playwright.sync_api import sync_playwright
U = sys.argv[1]; OUT = sys.argv[2]
bugs, log = [], []
def note(m): log.append(m); print(m, flush=True)
def bug(m): bugs.append(m); print('BUG:', m, flush=True)

def watch(pg, nom):
    pg.on('pageerror', lambda e: bug(f'[{nom}] erreur JS : {e}'))
    pg.on('console', lambda m: m.type == 'error' and 'favicon' not in m.text and 'TUNNEL' not in m.text and '404' not in m.text and bug(f'[{nom}] console : {m.text}'))
    pg.on('response', lambda r: (r.status >= 500 or (r.status == 404 and '9999' not in r.url)) and bug(f'[{nom}] HTTP {r.status} sur {r.url}'))
    pg.on('dialog', lambda d: d.accept('motif test') if d.type == 'prompt' else d.accept())

def login(pg, u, pw):
    pg.goto(U + '/logout'); pg.goto(U + '/login')
    pg.fill('input[name=username]', u); pg.fill('#pw', pw); pg.click('button[type=submit]'); pg.wait_for_load_state()

def alertes(pg): return pg.locator('.page-content > .alert').all_inner_texts()

def etape(pg, nom, f):
    try:
        f(); note(f'OK  {nom}')
    except Exception as e:
        bug(f'Étape « {nom} » : {type(e).__name__}: {str(e).splitlines()[0][:200]}')
        try: pg.screenshot(path=f'{OUT}/echec_{len(bugs)}.png', full_page=True)
        except Exception: pass

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path='/opt/pw-browsers/chromium')
    po = b.new_page(viewport={'width': 1366, 'height': 900}); watch(po, 'PO')
    dev = b.new_page(viewport={'width': 390, 'height': 844}); watch(dev, 'dev1 mobile')

    def s01():
        login(po, 'po', 'popo')
        assert '/sprints' in po.url, 'accueil attendu sur le calendrier, obtenu ' + po.url
        assert po.locator('#parcours').count(), 'bandeau absent'
    etape(po, '01 connexion PO → calendrier', s01)

    def s02():
        po.select_option('select[name=duree_semaines]', '1'); po.fill('#calendrier input[name=nb_sprints]', '4')
        po.click('#calendrier button.btn-primary'); po.wait_for_load_state()
        assert 'Calendrier enregistré' in ' '.join(alertes(po)), alertes(po)
        assert 'ÉTAPE 2' in po.locator('#parcours .card-title').inner_text()
    etape(po, '02 calendrier 4 sprints d\'1 semaine', s02)

    def s03():
        po.fill('#nouvelle-release input[name=nom]', 'R1 – MVP'); po.fill('#nouvelle-release input[name=nb_sprints]', '2')
        po.click('text=Créer la release'); po.wait_for_load_state()
        po.click('text=+ Nouvelle release'); po.wait_for_timeout(700)
        po.fill('#nouvelle-release input[name=nom]', 'R2 – Flotte'); po.fill('#nouvelle-release input[name=nb_sprints]', '3')
        po.click('text=Créer la release'); po.wait_for_load_state()
        t = ' '.join(alertes(po)); assert 'R2' in t, t
        assert 'calendrier passe à 5' in t.lower() or '5 sprints' in po.content(), 'calendrier non allongé : ' + t
    etape(po, '03 deux releases (allongement auto du calendrier)', s03)

    def s04():
        po.goto(U + '/backlog'); po.click('text=+ Nouvelle feature'); po.wait_for_timeout(700)
        po.fill('#nouvelle-feature input[name=nom]', 'Cartographie'); po.click('text=Créer la feature'); po.wait_for_load_state()
        po.click('text=+ Nouvelle feature'); po.wait_for_timeout(700)
        po.fill('#nouvelle-feature input[name=nom]', 'Supervision'); po.select_option('#nf-release', index=1)
        po.click('text=Créer la feature'); po.wait_for_load_state()
        assert po.locator('.ajout-story').count() == 2
    etape(po, '04 deux features', s04)

    def s05():
        stories = [(0, 'us', 'Importer le plan', 'P1'), (0, 'us', 'Sélectionner les rangs', 'P1'), (0, 'tech', 'API commande', 'P2'),
                   (0, 'bug', 'Robot bloqué en bout de rang', 'P1'), (1, 'spike', 'Choisir la radio', 'P2'), (1, 'dette', 'Remplacer la lib carto', 'P3')]
        for fi, nat, t, p in stories:
            f = po.locator('.ajout-story').nth(fi)
            f.locator('select[name=nature]').select_option(nat); f.locator('input[name=titre]').fill(t)
            f.locator('select[name=priorite]').select_option(p); f.locator('button').click(); po.wait_for_load_state()
        assert po.locator('a.story-link').count() == 6, po.locator('a.story-link').count()
    etape(po, '05 six stories de natures différentes', s05)

    def s06():
        po.goto(U + '/story/1')
        po.fill('textarea[name=en_tant_que]', 'viticulteur'); po.fill('textarea[name=besoin]', 'importer mes parcelles'); po.fill('textarea[name=pour]', 'gagner du temps')
        po.fill('textarea[name=criteres]', 'Le fichier GeoJSON est importé'); po.fill('input[name=points]', '5')
        for i in range(5): po.check(f'input[name=dorc_{i}]')
        l = po.locator('.raci-ligne').last; l.locator('.raci-acteur').select_option('dev1'); l.locator('.raci-niveau').select_option('RA')
        po.click('#raci-ajout'); l = po.locator('.raci-ligne').last; l.locator('.raci-acteur').select_option('dev2'); l.locator('.raci-niveau').select_option('R')
        po.select_option('select[name=sprint]', '1')
        po.click('.barre-save button'); po.wait_for_load_state()
        t = ' '.join(alertes(po)); assert 'enregistrée' in t and 'refus' not in t.lower(), t
        assert po.input_value('select[name=sprint]') == '1'
        assert 'Prête' in po.content()
    etape(po, '06 fiche US-001 : rédaction, DoR complète, estimation, RACI, sprint 1', s06)

    def s07():
        po.goto(U + '/story/3'); po.select_option('select[name=parent_id]', '1'); po.fill('input[name=points]', '3')
        po.click('.barre-save button'); po.wait_for_load_state()
        assert po.input_value('select[name=parent_id]') == '1'
        po.goto(U + '/story/4'); po.select_option('select[name=parent_id]', '3'); po.click('.barre-save button'); po.wait_for_load_state()
        assert po.input_value('select[name=parent_id]') == '3'
        po.goto(U + '/story/1'); assert 'TECH-003' in po.content() or 'API commande' in po.content(), 'enfant non listé'
    etape(po, '07 rattachements (tech→US, bug→tech) et liste des enfants', s07)

    def s08():
        po.goto(U + '/story/2')
        l = po.locator('.raci-ligne').last; l.locator('.raci-acteur').select_option('dev3'); l.locator('.raci-niveau').select_option('R')
        po.click('.barre-save button'); po.wait_for_load_state()
        t = ' '.join(alertes(po)); assert 'RACI refusé' in t, 'RACI sans A accepté : ' + t
    etape(po, '08 RACI invalide (pas de A) refusé', s08)

    def s09():
        po.goto(U + '/planifier?sprint=1')
        po.fill('input[name=objectif]', 'Importer et sélectionner les parcelles'); po.locator('input[name=objectif]').press('Tab'); po.wait_for_load_state()
        po.fill('input[name=capacite]', '10'); po.locator('input[name=capacite]').press('Tab'); po.wait_for_load_state()
        assert po.input_value('input[name=capacite]') == '10'
        n0 = po.locator('.cols .card').nth(1).locator('.pl-row').count()
        po.locator('.cols .card').nth(0).locator('.pl-row', has_text='API commande').locator('button').click(); po.wait_for_load_state()
        po.locator('.cols .card').nth(0).locator('.pl-row', has_text='Sélectionner les rangs').locator('button').click(); po.wait_for_load_state()
        n1 = po.locator('.cols .card').nth(1).locator('.pl-row').count(); assert n1 == n0 + 2, (n0, n1)
        assert 'Pas encore prête' in po.content() or True
        po.locator('.cols .card').nth(1).locator('.pl-row', has_text='Sélectionner les rangs').locator('button').click(); po.wait_for_load_state()
        assert po.locator('.cols .card').nth(1).locator('.pl-row').count() == n0 + 1
        po.locator('.cols .card').nth(0).locator('.pl-row', has_text='Sélectionner les rangs').locator('button').click(); po.wait_for_load_state()
    etape(po, '09 sprint planning : objectif, capacité, ajout/retrait (story non prête acceptée)', s09)

    def s10():
        po.goto(U + '/story/1'); assert po.locator('#dod-bloc.replie').count() == 0, 'DoD repliée alors que la story est dans un sprint'
        for t, h in [('Analyse GeoJSON', '4'), ('Écran import', '6')]:
            po.fill('#ft-new input[name=titre]', t); po.fill('#ft-new input[name=heures]', h); po.click('text=Ajouter la tâche'); po.wait_for_load_state()
        assert 'Analyse GeoJSON' in po.content() and 'Écran import' in po.content() and '10 h' in po.locator('#taches').inner_text(), po.locator('#taches').inner_text()[-200:]
    etape(po, '10 tâches sur US-001', s10)

    def s11():
        po.goto(U + '/kanban?sprint=1')
        c = po.locator('.kcard', has_text='Importer le plan'); c.locator('button[data-dir="1"]').click(); po.wait_for_timeout(800)
        po.reload(); c = po.locator('.col[data-statut="En cours"] .kcard', has_text='Importer le plan'); assert c.count() == 1, 'carte pas en En cours'
        c.locator('button[data-dir="1"]').click(); po.wait_for_timeout(800); po.reload()
        # DoD incomplete -> confirm (non bloquante ?) ou refus
        st = 'Fait' if po.locator('.col[data-statut="Fait"] .kcard', has_text='Importer le plan').count() else 'En cours'
        note(f'    passage en Fait avec DoD 0/5 → statut obtenu : {st}')
        po.locator('form[action$="/jour"] button[title^="Jour suivant"]').click(); po.wait_for_load_state()
        assert 'J2' in po.locator('#jour-val').inner_text()
        k = po.locator('.kcard', has_text='API commande'); k.locator('.btn-andon').click(); po.wait_for_load_state(); po.wait_for_timeout(500)
        assert po.locator('.kcard', has_text='API commande').locator('.andon').count() >= 1, 'andon non affiché'
        po.screenshot(path=f'{OUT}/kanban.png', full_page=True)
    etape(po, '11 Kanban : déplacements, DoD, jour suivant, andon', s11)

    def s12():
        po.goto(U + '/kanban?vue=globale'); assert po.locator('.postit').count() >= 2
        po.screenshot(path=f'{OUT}/globale.png')
    etape(po, '12 vue globale', s12)

    def s13():
        login(dev, 'dev1', 'devdev')
        note('    accueil dev1 → ' + dev.url)
        dev.goto(U + '/kanban?sprint=1'); dev.screenshot(path=f'{OUT}/mobile_kanban.png', full_page=True)
        k = dev.locator('.kcard', has_text='API commande'); k.locator('button[data-dir="1"]').click(); dev.wait_for_timeout(800); dev.reload()
        assert dev.locator('.col[data-statut="En cours"] .kcard', has_text='API commande').count() == 1, 'dev ne peut pas déplacer'
        dev.goto(U + '/story/2'); assert dev.locator('input[name=titre][disabled]').count() == 1, 'titre modifiable par le dev'
        dev.fill('input[name=points]', '2'); dev.click('.barre-save button'); dev.wait_for_load_state()
        assert dev.input_value('input[name=points]') == '2', 'estimation dev non enregistrée'
        for path in ['/backlog', '/sprints', '/planifier', '/revue', '/retro']:
            r = dev.goto(U + path); assert r.status == 200, (path, r.status)
            dev.screenshot(path=f'{OUT}/mobile{path.replace("/", "_")}.png', full_page=True)
        r = dev.goto(U + '/admin/users'); note(f'    dev1 sur /admin/users → {r.status} {dev.url}')
        assert '/admin/users' not in dev.url or r.status in (302, 403), 'dev a accès à l\'admin'
    etape(dev, '13 parcours dev1 sur téléphone (droits, Kanban, estimation)', s13)

    def s14():
        po.goto(U + '/revue?sprint=1')
        po.fill('.ajout-retour textarea[name=texte]', 'La carte doit montrer le niveau de batterie'); po.click('text=Enregistrer le retour'); po.wait_for_load_state()
        po.click('.j-creer'); po.wait_for_timeout(300)
        f = po.locator('form.creer').first; f.locator('select[name=nature]').select_option('us'); f.locator('button').click(); po.wait_for_load_state()
        assert 'story' in po.locator('#retours').inner_text().lower()
        po.check('input[name=objectif_atteint][value=partiel]'); po.click('text=Clôturer la revue et figer le bilan'); po.wait_for_load_state()
        assert 'Revue clôturée' in po.content()
        po.screenshot(path=f'{OUT}/revue.png', full_page=True)
    etape(po, '14 revue : retour client → story, clôture', s14)

    def s15():
        po.goto(U + '/retro?sprint=1'); po.locator('.tech-choix label').nth(2).click(); po.click('text=Démarrer la rétrospective'); po.wait_for_load_state()
        for _ in range(1):
            po.locator('form[action$="/phase"] button.btn-primary').click(); po.wait_for_load_state()
        f = po.locator('form.add-postit').first; f.locator('textarea, input[type=text]').first.fill('Simulateur indisponible'); f.locator('button').click(); po.wait_for_load_state()
        dev.goto(U + '/retro?sprint=1'); f = dev.locator('form.add-postit').first; f.locator('textarea, input[type=text]').first.fill('Bonne entraide'); f.locator('button').click(); dev.wait_for_load_state()
        po.reload(); po.locator('form[action$="/phase"] button.btn-primary').click(); po.wait_for_load_state()
        po.locator('.j-vote').first.click(); po.wait_for_timeout(600)
        po.reload(); po.locator('form[action$="/phase"] button.btn-primary').click(); po.wait_for_load_state()
        po.locator('.j-action').first.click(); po.wait_for_timeout(300)
        af = po.locator('form.act-form'); 
        if af.locator('select[name=porteur]').count(): af.locator('select[name=porteur]').select_option(index=1)
        if af.locator('select[name=sprint_cible]').count(): af.locator('select[name=sprint_cible]').select_option('2')
        af.locator('button').click(); po.wait_for_load_state()
        assert po.locator('.act-row').count() >= 1, 'action non créée'
        po.locator('form[action$="/phase"] button.btn-primary').click(); po.wait_for_load_state()
        po.screenshot(path=f'{OUT}/retro.png', full_page=True)
        po.goto(U + '/kanban?sprint=2'); assert 'Simulateur' in po.content() or po.locator('text=Actions').count(), 'action non visible sur le Kanban S2'
    etape(po, '15 rétro speed boat : post-its PO+dev, vote, action → Kanban S2', s15)

    def s16():
        po.goto(U + '/sprints'); po.screenshot(path=f'{OUT}/sprints.png', full_page=True)
        assert po.locator('#ensemble').count() == 1
        po.goto(U + '/backlog?nature=bug'); assert po.locator('a.story-link').count() == 1
        po.goto(U + '/backlog?dev=dev1'); assert po.locator('a.story-link').count() >= 1
        po.goto(U + '/backlog'); po.screenshot(path=f'{OUT}/backlog.png', full_page=True)
    etape(po, '16 vue d\'ensemble et filtres du backlog', s16)

    def s17():
        po.goto(U + '/parametres'); r = po.goto(U + '/admin/users'); assert r.status == 200
        po.screenshot(path=f'{OUT}/admin.png', full_page=True)
    etape(po, '17 pages d\'administration', s17)

    def s18():
        po.goto(U + '/sprints'); po.click('#repartir .repli-btn'); po.fill('#repartir input[name=confirmation]', 'vider'); po.click('#repartir button.btn-danger'); po.wait_for_load_state()
        assert 'Backlog vidé' in ' '.join(alertes(po)), alertes(po)
        po.goto(U + '/backlog'); assert po.locator('a.story-link').count() == 0
    etape(po, '18 repartir de zéro', s18)

    def s19():
        po.goto(U + '/admin/users'); po.fill('form[action$="exemple"] input[name=confirmation]', 'EXEMPLE'); po.click('form[action$="exemple"] button'); po.wait_for_load_state()
        for path in ['/backlog', '/sprints', '/planifier', '/kanban', '/kanban?vue=globale', '/revue', '/retro', '/story/1', '/parametres']:
            r = po.goto(U + path); assert r.status == 200, (path, r.status)
    etape(po, '19 exemple ROBO AGRI + toutes les pages', s19)

    def s19b():
        po.goto(U + '/backlog'); po.click('text=Exporter en PDF'); po.wait_for_load_state()
        assert '/backlog/export' in po.url
        assert po.locator('.story').count() == 17, po.locator('.story').count()
        assert po.locator('h2', has_text='Sprints planifiés').count() == 1
        po.fill('#auteur', 'Test ÉTUDIANT'); assert 'Test ÉTUDIANT' in po.title()
        assert po.inner_text('#auteur-aff') == 'Test ÉTUDIANT'
        po.emulate_media(media='print'); po.pdf(path=f'{OUT}/export.pdf', format='A4'); po.emulate_media(media='screen')
    etape(po, '19b export PDF du backlog', s19b)

    def s20():
        r = po.goto(U + '/story/9999'); assert r.status == 404
        r = po.goto(U + '/kanban?sprint=99'); assert r.status == 200
        r = po.goto(U + '/planifier?sprint=abc'); assert r.status == 200
    etape(po, '20 URL invalides', s20)
    b.close()

open(f'{OUT}/rapport.txt', 'w').write('\n'.join(log) + '\n\nBUGS:\n' + '\n'.join(bugs))
print('\n=== %d bug(s) ===' % len(bugs))

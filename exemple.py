"""Jeu de donnees d'exemple : ROBO AGRI, robot vendangeur autonome.

Structure pensee pour l'exercice :
- Sprint 1 planifie, estime et decoupe en taches (pret pour le Kanban et le burndown)
- Sprint 2 partiellement planifie
- le reste du backlog est a estimer et a planifier par les participants
"""

PRODUIT = {
    'nom': 'ROBO AGRI – robot vendangeur autonome',
    'vision': ("Pour les exploitations viticoles confrontées à la pénurie de saisonniers, "
               "ROBO AGRI est un robot vendangeur autonome qui récolte rang par rang, de jour comme de nuit, "
               "et que l'exploitant pilote depuis une tablette. Contrairement aux machines à vendanger tractées, "
               "il ne demande pas de chauffeur et préserve les grappes."),
    'nb_sprints': 6,
    'duree_semaines': 2,
}

DOD_COMMUNE = [
    'Code relu par un pair',
    'Tests unitaires écrits et passants',
    "Critères d'acceptation validés par le PO",
    'Testé sur le simulateur de parcelle',
    'Documentation utilisateur mise à jour',
]

DOR_COMMUNE = [
    'Rédigée au format « En tant que… j\'ai besoin de… pour… »',
    "Critères d'acceptation définis",
    "Estimée par l'équipe",
    'Assez petite pour tenir dans un sprint',
    'Dépendances identifiées',
]

def dor_cochee(criteres, points, sprint):
    """Etat de depart de la DoR : les stories deja planifiees sont pretes,
    les autres ne cochent que ce qui est vrai (redigee, criteres ecrits, estimee)."""
    if sprint:
        return list(DOR_COMMUNE)
    ok = [DOR_COMMUNE[0]]
    if criteres: ok.append(DOR_COMMUNE[1])
    if points: ok.append(DOR_COMMUNE[2])
    return ok

RELEASES = [
    {'nom': 'R1 – Premier robot au rang', 'nb_sprints': 3,
     'objectif': 'Un robot récolte seul une parcelle cartographiée, en sécurité, sous la supervision d’un opérateur.'},
    {'nom': 'R2 – Flotte et supervision', 'nb_sprints': 3,
     'objectif': 'Piloter plusieurs robots en même temps et anticiper les pannes.'},
]

SPRINTS = {
    1: {'objectif': 'Lancer et arrêter en sécurité une récolte sur une parcelle cartographiée', 'capacite': 21},
    2: {'objectif': 'Récolter sans dégâts et suivre le volume récolté', 'capacite': 20},
}

# (titre, en_tant_que, besoin, pour, criteres, priorite, points, sprint, dod_specifique, taches[(titre, heures)])
FEATURES = [
    {'nom': 'Cartographie des parcelles', 'release': 0, 'stories': [
        ('Importer le plan des parcelles', 'viticulteur exploitant',
         'importer le plan GPS de mes parcelles depuis mon logiciel de gestion viticole',
         'que le robot connaisse les zones à vendanger sans que je les redessine',
         "Étant donné un fichier GeoJSON valide, quand je l'importe, alors chaque parcelle apparaît sur la carte avec son nom et sa surface.\n"
         "Un fichier invalide affiche un message d'erreur compréhensible.",
         'P1', 8, 1, ['Testé avec 3 formats de fichiers exportés par des logiciels du marché'],
         [('Analyse des formats GeoJSON / KML', 4), ("Écran d'import et contrôle du fichier", 6),
          ('Affichage des parcelles sur la carte', 8), ('Tests avec fichiers réels', 4)]),
        ('Sélectionner les rangs à récolter', 'chef de culture',
         'sélectionner sur la carte les rangs dont le raisin est mûr',
         'ne récolter que les raisins à maturité',
         'Je peux sélectionner un ou plusieurs rangs ; la sélection est enregistrée et visible par l’opérateur.',
         'P1', 5, 1, [],
         [('Sélection multiple des rangs sur la carte', 6), ('Enregistrement de la sélection', 3), ('Tests', 3)]),
        ('Délimiter les zones interdites', 'chef de culture',
         'tracer sur la carte des zones que le robot ne doit jamais traverser (fossés, poteaux, bâtiments)',
         'éviter les accidents et les dégâts matériels',
         '', 'P2', 3, 2, ['Vérifié en conditions réelles sur une parcelle en pente'], []),
    ]},
    {'nom': 'Récolte autonome', 'release': 0, 'stories': [
        ('Lancer une récolte à distance', 'opérateur de supervision',
         'démarrer la récolte des rangs sélectionnés depuis ma tablette',
         'ne pas avoir à me déplacer dans la parcelle',
         'Le robot démarre en moins de 30 s après la commande ; la tablette affiche « Récolte en cours ».',
         'P1', 5, 1, [],
         [('Commande de démarrage (API robot)', 5), ('Bouton et retour d’état sur la tablette', 4), ('Tests sur simulateur', 3)]),
        ("Arrêt d'urgence à distance", 'opérateur de supervision',
         "arrêter immédiatement le robot d'un seul geste",
         'protéger les personnes présentes dans le rang',
         "Le robot s'immobilise en moins d'1 seconde, quel que soit l'écran affiché sur la tablette.",
         'P1', 3, 1, ['Validé par le référent sécurité'],
         [("Bouton d'arrêt toujours visible", 2), ('Temps de réponse < 1 s', 4), ('Test de sécurité filmé', 2)]),
        ('Suivre le volume récolté', 'responsable de chai',
         'connaître en temps réel les kilos récoltés par parcelle',
         'organiser la réception de la vendange au chai',
         '', 'P2', 5, 2, [], []),
        ('Adapter la cadence à la météo', 'chef de culture',
         'que le robot ralentisse ou se mette à l’abri en cas de pluie forte',
         'préserver la qualité des grappes et le matériel',
         '', 'P3', 0, 0, [], []),
        ("Connaître l'autonomie de la batterie", 'opérateur de supervision',
         "voir le niveau de batterie et l'autonomie restante en rangs",
         'renvoyer le robot à la recharge avant la panne',
         '', 'P2', 0, 0, [], []),
    ]},
    {'nom': 'Supervision de la flotte', 'release': 1, 'stories': [
        ('Voir la position des robots en temps réel', 'opérateur de supervision',
         'voir sur la carte la position de chaque robot, mise à jour toutes les 10 secondes',
         'savoir où intervenir en cas de blocage', '', 'P1', 0, 0, [], []),
        ('Réaffecter un robot à une autre parcelle', 'chef de culture',
         'envoyer un robot inoccupé vers une parcelle en retard',
         'terminer les vendanges à temps', '', 'P2', 0, 0, [], []),
        ('Bilan de fin de journée', 'viticulteur exploitant',
         'recevoir chaque soir un bilan des rangs récoltés, des kilos et des incidents',
         'préparer la journée du lendemain', '', 'P3', 0, 0, [], []),
    ]},
    {'nom': 'Maintenance et alertes', 'release': 1, 'stories': [
        ('Être alerté en cas de panne ou de blocage', 'opérateur de supervision',
         'recevoir une notification dès qu’un robot est bloqué ou en panne',
         'intervenir avant de perdre une demi-journée de récolte', '', 'P1', 0, 0, [], []),
        ('Planifier la maintenance préventive', 'technicien de maintenance',
         'connaître les heures de fonctionnement de chaque pièce d’usure',
         'remplacer les pièces avant la casse en pleine saison', '', 'P3', 0, 0, [], []),
    ]},
]

#!/usr/bin/env python3
"""Script temporaire pour ajouter les chapitres manquants en Maths 5ème."""

import json
from pathlib import Path

new_docs = [
    {
        "title": "Échelles - Lecture et utilisation",
        "domaine": "Grandeurs et Mesures",
        "sousdomaine": "Échelles",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "Une échelle est un rapport entre les dimensions d'une représentation (plan, carte, maquette) et les dimensions réelles. Elle s'écrit sous forme de fraction : échelle = dimension sur le plan / dimension réelle. Exemple : une échelle de 1/100 signifie que 1 cm sur le plan représente 100 cm (= 1 m) en réalité. Lecture d'une échelle : 1/50 signifie que 1 unité sur le plan = 50 unités en réalité. Sur une carte au 1/25000, 1 cm représente 25000 cm = 250 m. Calcul de la dimension réelle : dimension réelle = dimension sur le plan × dénominateur de l'échelle. Exemple : sur un plan au 1/200, un mur mesure 3 cm. Dimension réelle = 3 × 200 = 600 cm = 6 m. Calcul de la dimension sur le plan : dimension plan = dimension réelle / dénominateur. Exemple : représenter 15 m à l'échelle 1/500. Dimension plan = 1500 cm / 500 = 3 cm. Plus le dénominateur est grand, plus l'échelle est petite (moins de détails). Échelle 1/25000 < 1/100.",
        "keywords": ["échelle", "plan", "carte", "rapport", "dimension", "réduction", "agrandissement", "proportionnalité"],
        "typical_questions": ["Comment lire une échelle ?", "Comment calculer une dimension réelle ?", "Que signifie 1/100 ?", "Comment calculer la dimension sur le plan ?"],
        "common_errors": ["Confondre numérateur et dénominateur", "Oublier de convertir les unités", "Multiplier au lieu de diviser"],
        "prerequis": ["proportionnalité", "conversions unités longueur", "fractions"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["échelles", "proportionnalité", "programme_5eme"],
        "learning_objectives": ["Maîtriser la méthode: Échelles - Lecture et utilisation", "Savoir calculer dimensions réelles et sur plan", "Comprendre la signification des échelles"]
    },
    {
        "title": "Vitesse moyenne - Calcul et formules",
        "domaine": "Grandeurs et Mesures",
        "sousdomaine": "Vitesse",
        "content_type": "formule",
        "difficulty": "standard",
        "content": "La vitesse moyenne est le rapport entre la distance parcourue et la durée du trajet : v = d / t où v est la vitesse, d la distance, t le temps. Formules dérivées : d = v × t (distance = vitesse × temps) et t = d / v (temps = distance / vitesse). Unités courantes : km/h (kilomètres par heure), m/s (mètres par seconde). Conversion : 1 m/s = 3,6 km/h. Pour convertir km/h en m/s, diviser par 3,6 ; pour convertir m/s en km/h, multiplier par 3,6. Exemple : une voiture roule à 90 km/h pendant 2h. Distance = 90 × 2 = 180 km. Autre exemple : un cycliste parcourt 45 km en 3h. Vitesse = 45 / 3 = 15 km/h. Attention aux unités : si la distance est en km et le temps en heures, la vitesse est en km/h. Si la distance est en m et le temps en s, la vitesse est en m/s. Pour les durées en minutes, convertir en heures (diviser par 60) ou en secondes (multiplier par 60).",
        "keywords": ["vitesse", "distance", "temps", "durée", "km/h", "m/s", "conversion", "moyenne"],
        "typical_questions": ["Comment calculer une vitesse ?", "Comment convertir km/h en m/s ?", "Comment calculer une distance parcourue ?", "Comment calculer un temps de trajet ?"],
        "common_errors": ["Mélanger les unités (km et m, h et min)", "Oublier de convertir les minutes en heures", "Confondre multiplication et division"],
        "prerequis": ["proportionnalité", "conversions unités temps", "division"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["vitesse", "grandeurs", "programme_5eme"],
        "learning_objectives": ["Mémoriser les formules vitesse-distance-temps", "Savoir convertir les unités de vitesse", "Appliquer les formules dans des problèmes"]
    },
    {
        "title": "Statistiques - Médiane et étendue",
        "domaine": "Organisation et Gestion de Données",
        "sousdomaine": "Statistiques",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "La médiane est la valeur qui partage une série statistique ordonnée en deux parties de même effectif : 50% des valeurs sont inférieures ou égales à la médiane, 50% sont supérieures ou égales. Méthode de calcul : 1) Ranger les valeurs dans l'ordre croissant ; 2) Si n (effectif) est impair, la médiane est la valeur centrale (rang (n+1)/2) ; 3) Si n est pair, la médiane est la moyenne des deux valeurs centrales (rangs n/2 et n/2+1). Exemple avec n=5 : valeurs 3, 7, 9, 12, 15 → médiane = 9 (3ème valeur). Exemple avec n=6 : valeurs 4, 6, 8, 11, 13, 17 → médiane = (8+11)/2 = 9,5. L'étendue mesure la dispersion : étendue = valeur maximale - valeur minimale. Exemple : pour 3, 7, 9, 12, 15, l'étendue = 15 - 3 = 12. Avantage de la médiane sur la moyenne : elle est insensible aux valeurs extrêmes. Série 1, 2, 3, 4, 100 → moyenne = 22 mais médiane = 3.",
        "keywords": ["médiane", "étendue", "statistiques", "série ordonnée", "valeur centrale", "dispersion", "effectif"],
        "typical_questions": ["Comment calculer la médiane ?", "Quelle différence entre moyenne et médiane ?", "Comment calculer l'étendue ?", "Que faire si l'effectif est pair ?"],
        "common_errors": ["Oublier de ranger les valeurs dans l'ordre", "Confondre moyenne et médiane", "Se tromper de position pour la valeur centrale"],
        "prerequis": ["moyenne", "rangement ordre croissant", "effectif"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["statistiques", "médiane", "étendue", "programme_5eme"],
        "learning_objectives": ["Comprendre la définition de la médiane", "Savoir calculer médiane et étendue", "Comparer moyenne et médiane"]
    },
    {
        "title": "Aire du disque",
        "domaine": "Grandeurs et Mesures",
        "sousdomaine": "Périmètres et aires",
        "content_type": "formule",
        "difficulty": "standard",
        "content": "L'aire d'un disque de rayon r se calcule avec la formule : A = π × r² (pi fois rayon au carré). Le disque est la surface intérieure d'un cercle. Attention à bien distinguer rayon et diamètre : le diamètre d = 2r, donc si on connaît le diamètre, r = d/2. Exemple : disque de rayon 5 cm. Aire = π × 5² = π × 25 = 25π ≈ 78,5 cm². Exemple avec diamètre : disque de diamètre 8 cm. Rayon = 8/2 = 4 cm. Aire = π × 4² = 16π ≈ 50,3 cm². Rappel : le périmètre du cercle (circonférence) est P = 2πr = πd. Valeur de π : π ≈ 3,14159... On utilise souvent π ≈ 3,14 pour les calculs, mais il est préférable de garder le résultat sous forme exacte (25π) quand c'est possible. Unités : l'aire s'exprime en unités de surface (cm², m², etc.). Attention : si le rayon est en cm, l'aire est en cm².",
        "keywords": ["aire", "disque", "cercle", "rayon", "diamètre", "pi", "formule", "surface"],
        "typical_questions": ["Comment calculer l'aire d'un disque ?", "Quelle différence entre cercle et disque ?", "Comment utiliser le diamètre dans la formule ?", "Pourquoi utilise-t-on π ?"],
        "common_errors": ["Confondre rayon et diamètre", "Oublier de mettre le rayon au carré", "Confondre périmètre et aire"],
        "prerequis": ["périmètre du cercle", "nombre π", "carré d'un nombre"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["aires", "cercle", "disque", "programme_5eme"],
        "learning_objectives": ["Mémoriser la formule de l'aire du disque", "Distinguer rayon et diamètre", "Calculer des aires de disques"]
    },
    {
        "title": "Cercle circonscrit d'un triangle",
        "domaine": "Géométrie",
        "sousdomaine": "Triangles",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Le cercle circonscrit à un triangle est l'unique cercle qui passe par les trois sommets du triangle. Son centre est équidistant des trois sommets. Construction : le centre du cercle circonscrit est le point d'intersection des médiatrices des côtés du triangle. En pratique, il suffit de tracer deux médiatrices : leur intersection donne le centre. Le rayon est la distance du centre à n'importe quel sommet. Position du centre selon le type de triangle : dans un triangle acutangle (3 angles aigus), le centre est à l'intérieur ; dans un triangle rectangle, le centre est sur l'hypoténuse, exactement en son milieu (propriété fondamentale) ; dans un triangle obtusangle (1 angle obtus), le centre est à l'extérieur. Propriété du triangle rectangle : l'hypoténuse est un diamètre du cercle circonscrit. Donc si ABC est rectangle en A, alors le milieu de [BC] est le centre du cercle circonscrit. Cette propriété a une réciproque : si un triangle est inscrit dans un cercle avec un côté qui est un diamètre, alors c'est un triangle rectangle.",
        "keywords": ["cercle circonscrit", "triangle", "médiatrice", "centre", "rayon", "hypoténuse", "inscrit"],
        "typical_questions": ["Comment construire le cercle circonscrit ?", "Où se trouve le centre du cercle circonscrit ?", "Quel lien entre triangle rectangle et cercle circonscrit ?", "Pourquoi utiliser les médiatrices ?"],
        "common_errors": ["Confondre cercle inscrit et cercle circonscrit", "Oublier que le centre peut être à l'extérieur", "Se tromper sur la position du centre selon le type de triangle"],
        "prerequis": ["médiatrice", "triangle", "triangle rectangle"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["cercle", "triangle", "construction", "programme_5eme"],
        "learning_objectives": ["Savoir construire le cercle circonscrit", "Connaître la propriété du triangle rectangle", "Localiser le centre selon le type de triangle"]
    },
    {
        "title": "Quadrilatères particuliers - Classification",
        "domaine": "Géométrie",
        "sousdomaine": "Quadrilatères",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Les quadrilatères particuliers sont classés selon leurs propriétés de côtés, d'angles et de diagonales. Le parallélogramme : côtés opposés parallèles et de même longueur, diagonales qui se coupent en leur milieu. Le rectangle : parallélogramme avec 4 angles droits, diagonales de même longueur. Le losange : parallélogramme avec 4 côtés de même longueur, diagonales perpendiculaires. Le carré : à la fois rectangle ET losange, donc 4 angles droits ET 4 côtés égaux, diagonales perpendiculaires et de même longueur. Relations d'inclusion : carré ⊂ rectangle ⊂ parallélogramme et carré ⊂ losange ⊂ parallélogramme. Tout carré est un rectangle, mais tout rectangle n'est pas un carré. Le trapèze : quadrilatère avec deux côtés parallèles (les bases). Le trapèze isocèle a ses côtés non parallèles de même longueur. Le cerf-volant : quadrilatère avec deux paires de côtés consécutifs de même longueur, ses diagonales sont perpendiculaires.",
        "keywords": ["quadrilatère", "parallélogramme", "rectangle", "losange", "carré", "trapèze", "diagonales", "classification"],
        "typical_questions": ["Quelle différence entre rectangle et carré ?", "Comment prouver qu'un quadrilatère est un losange ?", "Quelles sont les propriétés des diagonales ?", "Un carré est-il un rectangle ?"],
        "common_errors": ["Penser que losange = carré", "Oublier qu'un carré EST un rectangle", "Confondre propriétés et caractérisations"],
        "prerequis": ["parallélogramme", "angle droit", "perpendiculaire"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["quadrilatères", "classification", "programme_5eme"],
        "learning_objectives": ["Connaître la classification des quadrilatères", "Identifier les propriétés de chaque type", "Comprendre les relations d'inclusion"]
    },
    {
        "title": "Durées - Calculs et conversions",
        "domaine": "Grandeurs et Mesures",
        "sousdomaine": "Durées",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "Les durées utilisent un système non décimal : 1 jour = 24 heures, 1 heure = 60 minutes, 1 minute = 60 secondes. Conversions : pour convertir en unité plus petite, on multiplie (2h = 2 × 60 = 120 min) ; pour convertir en unité plus grande, on divise avec quotient et reste (150 min = 150 ÷ 60 = 2h30 car 150 = 2×60 + 30). Addition de durées : on additionne séparément heures, minutes, secondes, puis on convertit si nécessaire. Exemple : 2h45min + 1h30min = 3h75min = 4h15min (car 75min = 1h15min). Soustraction de durées : méthode par complément ou par conversion. Exemple : 14h20 − 11h45. Méthode : de 11h45 à 12h00 = 15min, de 12h00 à 14h20 = 2h20. Total = 2h35min. Ou : 14h20min = 13h80min, puis 13h80min − 11h45min = 2h35min. Calcul d'heure d'arrivée : heure départ + durée = heure arrivée. Exemple : départ 9h40, trajet 2h35 → arrivée = 9h40 + 2h35 = 11h75 = 12h15.",
        "keywords": ["durée", "heure", "minute", "seconde", "conversion", "addition", "soustraction", "temps"],
        "typical_questions": ["Comment additionner des durées ?", "Comment convertir des minutes en heures ?", "Comment calculer une heure d'arrivée ?", "Comment soustraire des durées ?"],
        "common_errors": ["Traiter les durées comme des décimaux (1h50 ≠ 1,50h)", "Oublier que 60 min = 1h", "Se tromper lors des retenues"],
        "prerequis": ["division euclidienne", "addition soustraction", "conversions"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["durées", "conversions", "programme_5eme"],
        "learning_objectives": ["Maîtriser les conversions de durées", "Savoir additionner et soustraire des durées", "Calculer heures de départ et d'arrivée"]
    }
]

if __name__ == "__main__":
    filepath = Path(__file__).parent.parent / "data" / "processed" / "college" / "cinquieme" / "mathematiques.jsonl"

    with open(filepath, "a", encoding="utf-8") as f:
        for doc in new_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"[OK] Added {len(new_docs)} documents to mathematiques.jsonl")
    print("  - Echelles")
    print("  - Vitesse moyenne")
    print("  - Mediane et etendue")
    print("  - Aire du disque")
    print("  - Cercle circonscrit")
    print("  - Quadrilateres particuliers")
    print("  - Durees")

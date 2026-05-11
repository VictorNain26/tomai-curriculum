"""
Exemples de documents pour la documentation OpenAPI / JSON Schema.

Externalisés depuis `document.py` pour garder le module schema lisible :
les contenus pédagogiques sont longs par nature (programme officiel) et
polluent la lecture du modèle Pydantic. Importés dans `model_config`.
"""

DOCUMENT_EXAMPLES: list[dict] = [
    {
        "id": "math_5eme_pythagore_001",
        "title": "Théorème de Pythagore - Énoncé, conditions et applications",
        "domaine": "Géométrie",
        "sousdomaine": "Triangles rectangles",
        "content_type": "theoreme",
        "difficulty": "standard",
        "content": (
            "Dans un triangle rectangle, le carré de l'hypoténuse est égal à la somme des "
            "carrés des deux autres côtés. Si ABC est un triangle rectangle en A, alors "
            "BC² = AB² + AC². Ce théorème ne s'applique QUE dans un triangle rectangle. "
            "L'hypoténuse est toujours le côté opposé à l'angle droit, c'est le plus grand "
            "côté du triangle. Exemple d'application : Dans un triangle rectangle dont les "
            "côtés de l'angle droit mesurent 3 cm et 4 cm, l'hypoténuse mesure "
            "√(3² + 4²) = √(9 + 16) = √25 = 5 cm. Cette relation permet de vérifier qu'un "
            "triangle est rectangle : si BC² = AB² + AC², alors le triangle ABC est "
            "rectangle en A. Attention aux erreurs courantes : ne pas confondre "
            "l'hypoténuse avec un des côtés de l'angle droit, et bien identifier l'angle "
            "droit avant d'appliquer le théorème."
        ),
        "keywords": [
            "pythagore",
            "triangle rectangle",
            "hypoténuse",
            "carré",
            "théorème",
            "géométrie",
            "côtés",
            "angle droit",
        ],
        "prerequis": ["math_5eme_triangle_rectangle_001", "math_5eme_carre_nombre_001"],
        "typical_questions": [
            "Comment calculer l'hypoténuse d'un triangle rectangle ?",
            "Qu'est-ce que le théorème de Pythagore ?",
            "Comment vérifier qu'un triangle est rectangle ?",
        ],
        "learning_objectives": [
            "Connaître et appliquer le théorème de Pythagore",
            "Calculer la longueur d'un côté d'un triangle rectangle",
        ],
        "common_errors": [
            "Confondre l'hypoténuse avec un côté de l'angle droit",
            "Appliquer le théorème à un triangle non rectangle",
        ],
        "enriched": {
            "latex_formulas": ["BC^2 = AB^2 + AC^2", "c^2 = a^2 + b^2"],
        },
        "version": "1.0.0",
        "author": "Éduscol - Programme officiel",
        "source_revision": "BO 30/07/2020",
        "review_status": "validated",
        "confidence_level": 1.0,
        "tags": ["essentiel", "programme_5eme", "géométrie_plane"],
    },
]

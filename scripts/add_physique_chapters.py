#!/usr/bin/env python3
"""Add missing Physics chapters for 5eme - Energy section."""

import json
from pathlib import Path

new_docs = [
    {
        "title": "Sources d'energie - Classification",
        "domaine": "L'energie et ses conversions",
        "sousdomaine": "Sources d'energie",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Une source d'energie est un systeme capable de fournir de l'energie. On classe les sources d'energie en deux grandes categories. Les sources d'energie renouvelables sont inepuisables a l'echelle humaine car elles se regenerent naturellement : le Soleil (energie solaire), le vent (energie eolienne), l'eau des rivieres et marees (energie hydraulique et maremotrice), la chaleur de la Terre (energie geothermique), la biomasse (bois, dechets organiques). Les sources d'energie non renouvelables existent en quantite limitee et s'epuisent : les combustibles fossiles (petrole, charbon, gaz naturel) formes en millions d'annees a partir de matieres organiques, et l'uranium utilise dans les centrales nucleaires. Le Soleil est la source primaire de presque toutes les energies sur Terre : il est a l'origine du vent (differences de temperature), du cycle de l'eau, de la photosynthese (biomasse) et meme des combustibles fossiles (anciens organismes vivants). Les enjeux actuels sont la transition vers les energies renouvelables pour limiter le rechauffement climatique (lie aux emissions de CO2 des combustibles fossiles) et l'epuisement des ressources. Chaque source a ses avantages et inconvenients : impact environnemental, disponibilite, cout, intermittence (le soleil et le vent ne sont pas constants).",
        "keywords": ["source d'energie", "renouvelable", "non renouvelable", "fossile", "solaire", "eolien", "transition energetique"],
        "prerequis": ["energie"],
        "typical_questions": ["Quelles sont les sources d'energie renouvelables ?", "Pourquoi dit-on que le petrole n'est pas renouvelable ?", "Quel est le lien entre le Soleil et les autres sources d'energie ?"],
        "common_errors": ["Croire que l'electricite est une source d'energie (c'est un vecteur)", "Confondre renouvelable et propre"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["physique-chimie", "energie", "environnement", "programme_5eme"],
        "learning_objectives": ["Distinguer sources renouvelables et non renouvelables", "Comprendre les enjeux de la transition energetique", "Identifier le role du Soleil comme source primaire"]
    },
    {
        "title": "Formes d'energie",
        "domaine": "L'energie et ses conversions",
        "sousdomaine": "Formes d'energie",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "L'energie existe sous differentes formes qui peuvent se transformer les unes en les autres. L'energie cinetique est l'energie que possede un objet en mouvement : plus un objet est rapide et massif, plus son energie cinetique est grande. Exemples : voiture en mouvement, balle lancee, vent, eau qui coule. L'energie potentielle est l'energie stockee due a la position ou l'etat d'un objet. L'energie potentielle de pesanteur depend de l'altitude : un objet en hauteur possede de l'energie qu'il liberera en tombant. L'energie potentielle elastique est stockee dans un ressort comprime ou etire. L'energie thermique (ou chaleur) est liee a l'agitation des particules de la matiere : plus les particules bougent, plus la temperature est elevee. L'energie lumineuse est transportee par la lumiere. L'energie electrique est liee au deplacement des charges electriques dans un circuit. L'energie chimique est stockee dans les liaisons entre atomes des molecules : elle est liberee lors de reactions chimiques (combustion, digestion, piles). L'energie nucleaire est stockee dans le noyau des atomes et liberee lors de reactions nucleaires (fission dans les centrales, fusion dans le Soleil). L'unite d'energie dans le systeme international est le joule (J). On utilise aussi le kilowattheure (kWh) pour l'electricite : 1 kWh = 3 600 000 J.",
        "keywords": ["forme d'energie", "cinetique", "potentielle", "thermique", "chimique", "electrique", "nucleaire", "joule"],
        "prerequis": ["energie", "mouvement"],
        "typical_questions": ["Quelles sont les differentes formes d'energie ?", "Quelle est l'energie d'un objet qui tombe ?", "Quelle unite utilise-t-on pour mesurer l'energie ?"],
        "common_errors": ["Confondre energie et puissance", "Oublier l'energie potentielle d'un objet en hauteur", "Croire que l'energie disparait"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["physique-chimie", "energie", "formes", "programme_5eme"],
        "learning_objectives": ["Identifier les differentes formes d'energie", "Comprendre les notions d'energie cinetique et potentielle", "Connaitre l'unite d'energie (joule)"]
    },
    {
        "title": "Conversions d'energie - Chaine energetique",
        "domaine": "L'energie et ses conversions",
        "sousdomaine": "Conversions",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "L'energie peut passer d'une forme a une autre : c'est une conversion d'energie (ou transformation). Principe fondamental : l'energie totale se conserve, elle ne peut etre ni creee ni detruite, seulement transformee d'une forme en une autre. Exemples de conversions : dans une lampe, l'energie electrique est convertie en energie lumineuse (et thermique) ; dans un moteur, l'energie chimique du carburant devient energie cinetique (et thermique) ; dans un panneau solaire, l'energie lumineuse devient energie electrique ; dans une pile, l'energie chimique devient energie electrique ; dans une eolienne, l'energie cinetique du vent devient energie electrique. Pour representer les conversions, on utilise une chaine energetique : un schema avec des rectangles (convertisseurs) et des fleches (energie). Le convertisseur est l'appareil qui transforme l'energie (lampe, moteur, pile). Les fleches entrantes montrent l'energie recue, les fleches sortantes l'energie produite. Lors de toute conversion, une partie de l'energie est toujours transformee en energie thermique (chaleur) qui se dissipe dans l'environnement : ce sont les pertes. Le rendement mesure l'efficacite d'une conversion : c'est le rapport entre l'energie utile produite et l'energie totale consommee. Un rendement de 100% (conversion parfaite) est impossible en pratique.",
        "keywords": ["conversion", "transformation", "chaine energetique", "conservation", "rendement", "pertes", "convertisseur"],
        "prerequis": ["formes d'energie", "sources d'energie"],
        "typical_questions": ["Comment representer une chaine energetique ?", "Pourquoi y a-t-il toujours des pertes ?", "Qu'est-ce que le rendement ?"],
        "common_errors": ["Croire que l'energie disparait lors des pertes", "Oublier l'energie thermique dans les conversions", "Confondre source et convertisseur"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["physique-chimie", "energie", "conversion", "programme_5eme"],
        "learning_objectives": ["Comprendre le principe de conservation de l'energie", "Savoir representer une chaine energetique", "Identifier les pertes et le rendement"]
    }
]

if __name__ == "__main__":
    filepath = Path(__file__).parent.parent / "data" / "processed" / "college" / "cinquieme" / "physique_chimie.jsonl"

    with open(filepath, "a", encoding="utf-8") as f:
        for doc in new_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"[OK] Added {len(new_docs)} documents to physique_chimie.jsonl")
    print("  - Sources d'energie")
    print("  - Formes d'energie")
    print("  - Conversions d'energie")

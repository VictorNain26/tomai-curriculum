#!/usr/bin/env python3
"""Add missing Histoire-Geo chapters for 5eme."""

import json
from pathlib import Path

new_docs = [
    {
        "title": "Francois Ier et la Renaissance francaise",
        "domaine": "Histoire",
        "sousdomaine": "Les transformations de l'Europe XVIe-XVIIe",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Francois Ier (1515-1547) est le roi emblematique de la Renaissance francaise. Il incarne le prince de la Renaissance : cultive, amateur d'arts et protecteur des artistes. Il invite Leonard de Vinci en France (qui meurt a Amboise en 1519). Il fait construire ou renover de somptueux chateaux : Chambord, Fontainebleau, le chateau de Madrid. Il fonde le College de France (1530) pour enseigner les langues anciennes et les sciences, en dehors de la Sorbonne traditionnelle. Il impose le francais comme langue officielle (ordonnance de Villers-Cotterets, 1539). Sur le plan politique, il renforce le pouvoir royal : il controle l'Eglise de France (Concordat de Bologne, 1516), il developpe l'administration et les impots. Il mene des guerres en Italie pour etendre son royaume, rivalisant avec Charles Quint. Francois Ier represente la transition vers l'absolutisme : le roi concentre les pouvoirs, s'entoure d'une cour brillante, affirme sa puissance par les arts et l'architecture. Il reste associe a la bataille de Marignan (1515) et a la rivalite avec Charles Quint.",
        "keywords": ["Francois Ier", "Renaissance", "Chambord", "Villers-Cotterets", "College de France", "Marignan"],
        "prerequis": ["Renaissance", "Moyen Age"],
        "typical_questions": ["Qui etait Francois Ier ?", "Qu'est-ce que l'ordonnance de Villers-Cotterets ?", "Pourquoi Francois Ier est-il un prince de la Renaissance ?"],
        "common_errors": ["Confondre Francois Ier avec d'autres rois Francois", "Croire que la Renaissance commence avec Francois Ier"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["histoire", "renaissance", "francois ier", "programme_5eme"],
        "learning_objectives": ["Connaitre le regne de Francois Ier", "Comprendre le modele du prince de la Renaissance", "Identifier les apports culturels de cette periode"]
    },
    {
        "title": "Henri IV et l'Edit de Nantes",
        "domaine": "Histoire",
        "sousdomaine": "Les transformations de l'Europe XVIe-XVIIe",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Henri IV (1589-1610) met fin aux guerres de Religion qui ont dechire la France pendant 36 ans (1562-1598). Protestant devenu roi, il se convertit au catholicisme (Paris vaut bien une messe, 1593) pour etre accepte par la majorite catholique. En 1598, il signe l'Edit de Nantes qui etablit la tolerance religieuse : les protestants obtiennent la liberte de culte (sauf a Paris), des places de surete, l'acces a tous les emplois. C'est une premiere en Europe. Henri IV reconstruit le royaume apres les guerres : il developpe l'agriculture (Sully : Labourage et paturage sont les deux mamelles de la France), fait construire des routes et des ponts, embellit Paris (Place des Vosges, Pont Neuf). Il affirme l'autorite royale, preparant l'absolutisme. Henri IV reste populaire comme le bon roi Henri ou le Vert Galant. Son regne est interrompu par son assassinat en 1610 par Ravaillac, un catholique fanatique. L'Edit de Nantes sera revoque par Louis XIV en 1685, mettant fin a la tolerance religieuse.",
        "keywords": ["Henri IV", "Edit de Nantes", "guerres de Religion", "tolerance", "Sully", "absolutisme"],
        "prerequis": ["Reforme protestante", "guerres de Religion"],
        "typical_questions": ["Qu'est-ce que l'Edit de Nantes ?", "Pourquoi Henri IV s'est-il converti ?", "Comment Henri IV a-t-il pacifie le royaume ?"],
        "common_errors": ["Croire que l'Edit de Nantes etablit la laicite", "Confondre Edit de Nantes et sa revocation"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["histoire", "henri iv", "edit de nantes", "tolerance", "programme_5eme"],
        "learning_objectives": ["Comprendre les guerres de Religion", "Connaitre l'Edit de Nantes et ses consequences", "Situer Henri IV dans l'evolution vers l'absolutisme"]
    },
    {
        "title": "Louis XIV et l'absolutisme",
        "domaine": "Histoire",
        "sousdomaine": "Les transformations de l'Europe XVIe-XVIIe",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Louis XIV (1643-1715), le Roi-Soleil, incarne l'absolutisme : tous les pouvoirs sont concentres entre les mains du roi qui gouverne seul (L'Etat, c'est moi). Il regne 72 ans, le plus long regne de l'histoire de France. L'absolutisme repose sur plusieurs piliers. Le droit divin : le roi tient son pouvoir de Dieu, il n'a de comptes a rendre qu'a Dieu. Versailles : le chateau construit a partir de 1661 devient le siege du pouvoir. La noblesse y est enfermee dans des rituels (lever du roi, coucher) qui la tiennent eloignee du pouvoir reel. La centralisation : des intendants representent le roi dans les provinces, Colbert reorganise les finances et developpe l'industrie (manufactures). La grandeur : arts, architecture, fetes, guerres montrent la puissance royale. Louis XIV revoque l'Edit de Nantes (1685), forcant les protestants a se convertir ou a s'exiler. Il mene de nombreuses guerres couteuses qui affaiblissent le royaume a la fin de son regne. Le modele absolutiste francais influence toute l'Europe.",
        "keywords": ["Louis XIV", "absolutisme", "Versailles", "Roi-Soleil", "droit divin", "Colbert", "centralisation"],
        "prerequis": ["Francois Ier", "Henri IV", "monarchie"],
        "typical_questions": ["Qu'est-ce que l'absolutisme ?", "Pourquoi Louis XIV a-t-il fait construire Versailles ?", "Comment Louis XIV controlait-il la noblesse ?"],
        "common_errors": ["Croire que Louis XIV a invente l'absolutisme", "Oublier les aspects negatifs du regne"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["histoire", "louis xiv", "absolutisme", "versailles", "programme_5eme"],
        "learning_objectives": ["Definir l'absolutisme", "Connaitre les moyens du pouvoir de Louis XIV", "Comprendre le role de Versailles"]
    },
    {
        "title": "La societe feodale - Organisation",
        "domaine": "Histoire",
        "sousdomaine": "Societe, Eglise et pouvoir (XIe-XVe)",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "La societe feodale (Xe-XVe siecle) est organisee en trois ordres. Ceux qui prient (oratores) : le clerge (eveques, pretres, moines) prie pour le salut de tous, enseigne, soigne les malades. L'Eglise est tres puissante, possede des terres, preleve la dime (1/10 des recoltes). Ceux qui combattent (bellatores) : la noblesse (seigneurs, chevaliers) protege le royaume et les paysans. Les nobles vivent de leurs terres et des droits seigneuriaux. Ils sont lies par des liens de vassalite (hommage, fidelite). Ceux qui travaillent (laboratores) : les paysans (90% de la population) cultivent la terre. Ils peuvent etre serfs (attaches a la terre) ou vilains (libres mais soumis aux corvees et redevances). Cette societe est presentee comme voulue par Dieu : chacun a sa place et son role. La mobilite sociale est tres limitee : on nait dans un ordre et on y reste. Les trois ordres correspondent aux trois fonctions : spirituelle, militaire, productive. Ce schema trifonctionnel se retrouve dans d'autres civilisations indo-europeennes.",
        "keywords": ["societe feodale", "trois ordres", "clerge", "noblesse", "paysans", "serfs", "vassalite"],
        "prerequis": ["Moyen Age", "seigneurie"],
        "typical_questions": ["Quels sont les trois ordres ?", "Quelle est la place des paysans ?", "Peut-on changer d'ordre ?"],
        "common_errors": ["Croire que tous les paysans sont des serfs", "Penser que les ordres sont egaux en nombre"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["histoire", "moyen age", "feodalite", "trois ordres", "programme_5eme"],
        "learning_objectives": ["Connaitre les trois ordres", "Comprendre l'organisation feodale", "Situer chaque ordre dans la societe"]
    },
    {
        "title": "La prevention des risques",
        "domaine": "Geographie",
        "sousdomaine": "Prevenir les risques",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "La prevention des risques vise a reduire les consequences des catastrophes naturelles et technologiques. Rappel : Risque = Alea (phenomene dangereux) x Vulnerabilite (population exposee). La prevention agit sur les deux facteurs. Agir sur l'alea : surveillance des volcans, systemes d'alerte tsunami, previsions meteorologiques, entretien des forets contre les incendies. On ne peut pas empecher le phenomene mais on peut le detecter. Agir sur la vulnerabilite : constructions adaptees (normes parasismiques, digues, batiments sur pilotis), amenagement du territoire (interdiction de construire en zone inondable : PPR - Plan de Prevention des Risques), education des populations (exercices d'evacuation, consignes de securite). Gestion de crise : plans ORSEC, services de secours, evacuation. Les inegalites face aux risques : les pays riches ont plus de moyens de prevention, les pays pauvres subissent plus de victimes. Exemple : un seisme de meme magnitude fait moins de morts au Japon qu'en Haiti. En France : Vigipirate (terrorisme), Vigilance meteo (couleurs), PPR, information des populations. Le changement climatique intensifie certains risques (canicules, inondations, feux de foret).",
        "keywords": ["prevention", "risque", "alea", "vulnerabilite", "PPR", "alerte", "evacuation", "securite"],
        "prerequis": ["risques naturels", "changement climatique"],
        "typical_questions": ["Comment prevenir les risques ?", "Qu'est-ce qu'un PPR ?", "Pourquoi les pays pauvres sont-ils plus vulnerables ?"],
        "common_errors": ["Croire qu'on peut empecher tous les risques", "Confondre prevention et gestion de crise"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["geographie", "risques", "prevention", "securite", "programme_5eme"],
        "learning_objectives": ["Distinguer prevention et gestion de crise", "Connaitre les moyens de prevention", "Comprendre les inegalites face aux risques"]
    }
]

if __name__ == "__main__":
    filepath = Path(__file__).parent.parent / "data" / "processed" / "college" / "cinquieme" / "histoire_geo.jsonl"

    with open(filepath, "a", encoding="utf-8") as f:
        for doc in new_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"[OK] Added {len(new_docs)} documents to histoire_geo.jsonl")
    print("  - Francois Ier")
    print("  - Henri IV et l'Edit de Nantes")
    print("  - Louis XIV et l'absolutisme")
    print("  - La societe feodale")
    print("  - La prevention des risques")

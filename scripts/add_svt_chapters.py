#!/usr/bin/env python3
"""Add missing SVT chapters for 5eme - Geology and Reproduction."""

import json
from pathlib import Path

new_docs = [
    {
        "title": "Les volcans - Types et eruptions",
        "domaine": "La planete Terre",
        "sousdomaine": "Risques geologiques",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Un volcan est une ouverture dans la croute terrestre par laquelle remontent des materiaux en fusion provenant de l'interieur de la Terre. La structure d'un volcan comprend : un reservoir magmatique en profondeur (chambre magmatique), une cheminee (conduit reliant le reservoir a la surface), un cratere (ouverture au sommet), et parfois un cone volcanique forme par l'accumulation des materiaux rejetes. On distingue deux grands types d'eruptions. Les eruptions effusives (volcans rouges) produisent des coulees de lave fluide qui s'ecoulent le long des pentes. La lave sort a 1000-1200 degres, le magma est pauvre en gaz, l'eruption est relativement calme et previsible. Exemples : volcans d'Hawai, Piton de la Fournaise (Reunion). Les eruptions explosives (volcans gris) sont violentes et dangereuses. Le magma est visqueux et riche en gaz : la pression s'accumule jusqu'a provoquer une explosion. Elles produisent des nuees ardentes (nuages brulants de gaz et cendres devalant a grande vitesse), des projections (bombes, lapilli, cendres), parfois des lahars (coulees de boue). Exemples : Mont Saint Helens, Montagne Pelee (Martinique 1902). Les volcans sont localises principalement aux frontieres des plaques tectoniques (dorsales oceaniques, zones de subduction) et aux points chauds.",
        "keywords": ["volcan", "eruption", "lave", "magma", "effusif", "explosif", "cratere", "nuee ardente"],
        "prerequis": ["Terre", "roches"],
        "typical_questions": ["Quelle difference entre volcan rouge et volcan gris ?", "Pourquoi certaines eruptions sont explosives ?", "Ou se trouvent les volcans ?"],
        "common_errors": ["Confondre lave et magma", "Croire que tous les volcans sont explosifs"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["svt", "volcans", "geologie", "programme_5eme"],
        "learning_objectives": ["Connaitre les deux types d'eruptions volcaniques", "Comprendre la structure d'un volcan", "Localiser les volcans sur Terre"]
    },
    {
        "title": "Les seismes - Origine et mesure",
        "domaine": "La planete Terre",
        "sousdomaine": "Risques geologiques",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Un seisme (ou tremblement de terre) est une vibration brutale du sol causee par une rupture des roches en profondeur. Les roches de la croute terrestre sont soumises a des contraintes (forces de compression ou d'etirement) dues aux mouvements des plaques tectoniques. Quand la contrainte depasse la resistance des roches, celles-ci se brisent le long d'une faille : c'est la rupture sismique. L'energie accumulee est liberee sous forme d'ondes sismiques qui se propagent dans toutes les directions. Le foyer (ou hypocentre) est le point en profondeur ou se produit la rupture. L'epicentre est le point a la surface situe exactement a la verticale du foyer : c'est la que les degats sont generalement les plus importants. Les ondes sismiques sont detectees par des sismographes qui enregistrent les mouvements du sol (sismogrammes). On mesure deux caracteristiques d'un seisme. La magnitude (echelle de Richter) mesure l'energie liberee au foyer : elle est unique pour un seisme donne. L'intensite mesure les effets en surface (degats, ressenti) : elle varie selon la distance a l'epicentre et la nature du sol. Les seismes se produisent principalement aux frontieres des plaques tectoniques. Ils peuvent declencher des tsunamis s'ils ont lieu sous l'ocean.",
        "keywords": ["seisme", "tremblement de terre", "foyer", "epicentre", "faille", "ondes sismiques", "magnitude", "intensite"],
        "prerequis": ["Terre", "roches"],
        "typical_questions": ["Qu'est-ce qui provoque un seisme ?", "Quelle difference entre magnitude et intensite ?", "Ou se produisent les seismes ?"],
        "common_errors": ["Confondre foyer et epicentre", "Croire que la magnitude varie selon l'endroit"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["svt", "seismes", "geologie", "programme_5eme"],
        "learning_objectives": ["Comprendre l'origine des seismes", "Distinguer foyer et epicentre", "Connaitre les moyens de mesure des seismes"]
    },
    {
        "title": "La tectonique des plaques",
        "domaine": "La planete Terre",
        "sousdomaine": "Structure de la Terre",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "La lithosphere (couche externe rigide de la Terre comprenant la croute et le haut du manteau) est fragmentee en une quinzaine de grandes plaques tectoniques (ou lithospheriques) qui flottent sur l'asthenosphere, couche plus profonde, chaude et ductile (deformable). Ces plaques sont en mouvement permanent, de quelques centimetres par an, grace aux courants de convection du manteau. Trois types de mouvements existent aux frontieres des plaques. La divergence : les plaques s'ecartent l'une de l'autre au niveau des dorsales oceaniques (chaines de montagnes sous-marines). Du magma remonte et cree de nouvelle croute oceanique. Exemple : dorsale medio-atlantique. La convergence : les plaques se rapprochent. Si une plaque oceanique rencontre une plaque continentale, la plaque oceanique (plus dense) plonge sous l'autre dans une zone de subduction, creant des fosses oceaniques, des volcans explosifs et des seismes. Exemple : cote ouest de l'Amerique du Sud. Si deux plaques continentales se rencontrent, il y a collision et formation de chaines de montagnes. Exemple : Himalaya (Inde + Eurasie). Le coulissement : les plaques glissent l'une contre l'autre le long d'une faille transformante. Exemple : faille de San Andreas en Californie. La tectonique des plaques explique la repartition des volcans et des seismes, principalement situes aux frontieres des plaques.",
        "keywords": ["plaques tectoniques", "lithosphere", "dorsale", "subduction", "collision", "divergence", "convection"],
        "prerequis": ["structure de la Terre", "volcans", "seismes"],
        "typical_questions": ["Comment bougent les plaques tectoniques ?", "Pourquoi les volcans sont-ils situes a certains endroits ?", "Comment se forment les montagnes ?"],
        "common_errors": ["Croire que les plaques bougent vite", "Confondre lithosphere et croute"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["svt", "tectonique", "plaques", "programme_5eme"],
        "learning_objectives": ["Comprendre le modele de la tectonique des plaques", "Identifier les trois types de frontieres de plaques", "Expliquer l'origine des volcans et seismes"]
    },
    {
        "title": "Risques geologiques et prevention",
        "domaine": "La planete Terre",
        "sousdomaine": "Risques geologiques",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Les risques geologiques majeurs comprennent les seismes, les eruptions volcaniques, les tsunamis et les glissements de terrain. Un risque resulte de la combinaison d'un alea (phenomene naturel potentiellement dangereux) et d'une vulnerabilite (presence de populations et d'enjeux exposes). Risque = Alea x Vulnerabilite. Un seisme en zone desertique n'est pas un risque majeur ; le meme seisme dans une ville densement peuplee peut etre catastrophique. La prevention consiste a reduire le risque. Pour les seismes : constructions parasismiques (batiments souples et resistants), plans d'urbanisme evitant les zones a risque, education de la population (reflexes de securite), systemes d'alerte rapide. On ne peut pas predire precisement un seisme, mais on peut identifier les zones a risque (cartes de sismicite). Pour les volcans : surveillance permanente (deformations du sol, emissions de gaz, sismicite locale), plans d'evacuation, zonage (interdiction de construire pres du cratere). Les volcans sont plus previsibles que les seismes. Pour les tsunamis : systemes d'alerte base sur les sismographes et bouees oceaniques, education des populations cotieres (fuir vers les hauteurs apres un seisme ressenti). La France est concernee par ces risques : seismes (Pyrenees, Alpes, Antilles), volcans (Martinique, Guadeloupe, Reunion), tsunamis (Mediterranee, Antilles).",
        "keywords": ["risque", "alea", "vulnerabilite", "prevention", "parasismique", "surveillance", "alerte"],
        "prerequis": ["seismes", "volcans"],
        "typical_questions": ["Qu'est-ce qu'un risque geologique ?", "Comment se proteger des seismes ?", "Peut-on predire les eruptions volcaniques ?"],
        "common_errors": ["Croire qu'on peut predire les seismes", "Confondre alea et risque"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["svt", "risques", "prevention", "programme_5eme"],
        "learning_objectives": ["Distinguer alea, vulnerabilite et risque", "Connaitre les moyens de prevention", "Identifier les zones a risque en France"]
    },
    {
        "title": "Reproduction sexuee et asexuee",
        "domaine": "Le vivant et son evolution",
        "sousdomaine": "Reproduction",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Les etres vivants se reproduisent selon deux modes differents. La reproduction sexuee necessite la rencontre de deux cellules reproductrices (gametes) provenant de deux parents differents (male et femelle). Le gamete male (spermatozoide chez les animaux, pollen chez les plantes) et le gamete femelle (ovule) fusionnent lors de la fecondation pour former une cellule-oeuf qui se developpera en un nouvel individu. Ce nouvel individu possede un patrimoine genetique unique, combinant des caracteristiques des deux parents. La reproduction sexuee cree donc de la diversite genetique au sein de l'espece. La fecondation peut etre interne (dans le corps de la femelle : mammiferes, oiseaux, reptiles) ou externe (dans le milieu aquatique : la plupart des poissons, amphibiens). La reproduction asexuee ne fait intervenir qu'un seul individu parent, sans fecondation. Le nouvel individu est genetiquement identique au parent : c'est un clone. Exemples : bourgeonnement (hydre, levure), bouturage (plantes), fragmentation (etoile de mer), division cellulaire (bacteries, amibes). La reproduction asexuee est plus rapide et ne necessite pas de partenaire, mais elle ne cree pas de diversite genetique. Beaucoup d'organismes peuvent utiliser les deux modes selon les conditions (fraisier : stolons + graines).",
        "keywords": ["reproduction", "sexuee", "asexuee", "gametes", "fecondation", "diversite genetique", "clone"],
        "prerequis": ["cellule", "heredite"],
        "typical_questions": ["Quelle difference entre reproduction sexuee et asexuee ?", "Qu'est-ce qu'un gamete ?", "Pourquoi la reproduction sexuee cree-t-elle de la diversite ?"],
        "common_errors": ["Croire que la reproduction asexuee n'existe que chez les plantes", "Confondre clone et jumeau"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["svt", "reproduction", "genetique", "programme_5eme"],
        "learning_objectives": ["Distinguer reproduction sexuee et asexuee", "Comprendre le role de la fecondation", "Expliquer l'origine de la diversite genetique"]
    },
    {
        "title": "Puberte et reproduction humaine",
        "domaine": "Corps humain et sante",
        "sousdomaine": "Reproduction",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "La puberte est la periode de transition entre l'enfance et l'age adulte durant laquelle le corps se transforme et devient capable de se reproduire. Elle debute generalement entre 10 et 14 ans et dure plusieurs annees. Ces transformations sont declenchees par des hormones sexuelles (testosterone chez les garcons, oestrogenes et progesterone chez les filles) produites par les gonades (testicules et ovaires) sous le controle du cerveau (hypothalamus et hypophyse). Chez les garcons : developpement des organes genitaux, apparition des poils (pubis, aisselles, visage), mue de la voix, developpement musculaire, debut de la production de spermatozoides. Chez les filles : developpement des seins, apparition des poils (pubis, aisselles), elargissement des hanches, debut des regles (menstruations). Les regles marquent le debut du cycle menstruel (environ 28 jours) : chaque mois, un ovule est libere par un ovaire (ovulation) ; s'il n'est pas feconde, la muqueuse uterine est eliminee (regles). La puberte s'accompagne aussi de changements psychologiques : emotions nouvelles, questionnements sur l'identite, attirance pour les autres. Ces transformations sont normales et progressives. La reproduction humaine est possible apres la puberte mais engage des responsabilites : contraception, protection contre les IST, respect de soi et des autres.",
        "keywords": ["puberte", "hormones", "regles", "cycle menstruel", "ovulation", "testosterone", "reproduction"],
        "prerequis": ["hormones", "reproduction sexuee"],
        "typical_questions": ["Qu'est-ce que la puberte ?", "Quels changements se produisent a la puberte ?", "Comment fonctionne le cycle menstruel ?"],
        "common_errors": ["Croire que la puberte commence au meme age pour tous", "Confondre ovulation et regles"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["svt", "puberte", "reproduction", "programme_5eme"],
        "learning_objectives": ["Comprendre les transformations de la puberte", "Connaitre le role des hormones", "Expliquer le cycle menstruel"]
    }
]

if __name__ == "__main__":
    filepath = Path(__file__).parent.parent / "data" / "processed" / "college" / "cinquieme" / "svt.jsonl"

    with open(filepath, "a", encoding="utf-8") as f:
        for doc in new_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"[OK] Added {len(new_docs)} documents to svt.jsonl")
    print("  - Volcans")
    print("  - Seismes")
    print("  - Tectonique des plaques")
    print("  - Risques geologiques")
    print("  - Reproduction sexuee/asexuee")
    print("  - Puberte et reproduction")

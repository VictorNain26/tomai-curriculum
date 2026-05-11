#!/usr/bin/env python3
"""Add missing Francais chapters for 5eme."""

import json
from pathlib import Path

new_docs = [
    {
        "title": "Phrase simple et phrase complexe",
        "domaine": "Etude de la langue",
        "sousdomaine": "Grammaire",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Une phrase simple contient un seul verbe conjugue, donc une seule proposition. Exemple : Le chat dort sur le canape. Une phrase complexe contient plusieurs verbes conjugues, donc plusieurs propositions. Exemple : Le chat dort pendant que le chien aboie (deux verbes = deux propositions). Les propositions peuvent etre reliees de trois manieres. Par juxtaposition : les propositions sont separees par une ponctuation (virgule, point-virgule). Exemple : Il pleut, je reste chez moi. Par coordination : les propositions sont reliees par une conjonction de coordination (mais, ou, et, donc, or, ni, car). Exemple : Il pleut donc je prends mon parapluie. Par subordination : une proposition depend d'une autre (proposition principale et proposition subordonnee). Exemple : Je sais que tu viendras. Identifier le nombre de propositions : compter les verbes conjugues. Attention aux verbes a l'infinitif ou au participe qui ne comptent pas comme propositions independantes.",
        "keywords": ["phrase simple", "phrase complexe", "proposition", "juxtaposition", "coordination", "subordination", "verbe conjugue"],
        "prerequis": ["phrase", "verbe", "ponctuation"],
        "typical_questions": ["Comment distinguer phrase simple et phrase complexe ?", "Combien de propositions dans cette phrase ?", "Comment sont reliees les propositions ?"],
        "common_errors": ["Compter les verbes a l'infinitif comme propositions", "Confondre coordination et subordination"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "grammaire", "phrase", "programme_5eme"],
        "learning_objectives": ["Distinguer phrase simple et phrase complexe", "Identifier les propositions", "Reconnaitre les types de liens entre propositions"]
    },
    {
        "title": "Les mots invariables",
        "domaine": "Etude de la langue",
        "sousdomaine": "Grammaire",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Les mots invariables sont des mots qui ne changent jamais de forme : ils n'ont ni genre, ni nombre, ni conjugaison. On distingue quatre categories. Les adverbes modifient le sens d'un verbe, d'un adjectif ou d'un autre adverbe : rapidement, tres, souvent, hier, ici, ne...pas. Ils repondent aux questions comment ? quand ? ou ? combien ? Les prepositions introduisent un complement et etablissent un lien : a, de, pour, par, avec, sans, dans, sur, sous, chez, vers, en. Elles sont suivies d'un nom, pronom ou verbe a l'infinitif. Les conjonctions de coordination relient des elements de meme nature : mais, ou, et, donc, or, ni, car (moyen mnemotechnique : MAIS OU EST DONC ORNICAR). Les conjonctions de subordination introduisent une proposition subordonnee : que, quand, comme, si, lorsque, puisque, parce que, bien que, pour que. Les interjections expriment une emotion : oh ! ah ! helas ! bravo ! Astuce : un mot invariable s'ecrit toujours de la meme facon, il faut les memoriser.",
        "keywords": ["invariable", "adverbe", "preposition", "conjonction", "coordination", "subordination", "interjection"],
        "prerequis": ["classes de mots", "verbe", "nom"],
        "typical_questions": ["Quels sont les mots invariables ?", "Quelle est la difference entre preposition et conjonction ?", "Comment retenir les conjonctions de coordination ?"],
        "common_errors": ["Accorder un adverbe comme un adjectif", "Confondre preposition et adverbe (devant/avant)"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "grammaire", "mots invariables", "programme_5eme"],
        "learning_objectives": ["Connaitre les quatre categories de mots invariables", "Distinguer prepositions et conjonctions", "Utiliser correctement les mots invariables"]
    },
    {
        "title": "La proposition subordonnee - Introduction",
        "domaine": "Etude de la langue",
        "sousdomaine": "Grammaire",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Une proposition subordonnee est une proposition qui depend d'une autre proposition, appelee proposition principale. Elle ne peut pas exister seule et est introduite par un mot subordonnant. Exemple : Je pense [que tu as raison]. Principale : Je pense / Subordonnee : que tu as raison. Les principaux types de subordonnees en 5eme sont : la subordonnee conjonctive introduite par que, completant souvent un verbe (Je sais que tu viendras) ; la subordonnee relative introduite par un pronom relatif (qui, que, dont, ou) et completant un nom (Le livre que je lis est passionnant) ; la subordonnee circonstancielle introduite par quand, lorsque, si, parce que, pour que, etc., exprimant une circonstance. Pour identifier une subordonnee : 1) Reperer les verbes conjugues (plusieurs = phrase complexe), 2) Trouver le mot subordonnant, 3) Delimiter la subordonnee (du mot subordonnant jusqu'a la fin de la proposition). La subordonnee a toujours une fonction dans la phrase : COD, complement du nom, complement circonstanciel.",
        "keywords": ["subordonnee", "principale", "relative", "conjonctive", "circonstancielle", "mot subordonnant", "proposition"],
        "prerequis": ["phrase complexe", "verbe conjugue", "fonctions grammaticales"],
        "typical_questions": ["Qu'est-ce qu'une proposition subordonnee ?", "Comment identifier une subordonnee ?", "Quelle est la difference entre relative et conjonctive ?"],
        "common_errors": ["Confondre que conjonction et que pronom relatif", "Mal delimiter la subordonnee"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "grammaire", "subordonnee", "programme_5eme"],
        "learning_objectives": ["Comprendre la notion de subordination", "Identifier une subordonnee", "Distinguer les types de subordonnees"]
    },
    {
        "title": "L'accord du participe passe",
        "domaine": "Etude de la langue",
        "sousdomaine": "Orthographe",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "Le participe passe peut s'employer seul ou avec un auxiliaire. Les regles d'accord sont differentes. Employe seul ou avec etre : le participe passe s'accorde en genre et en nombre avec le sujet ou le nom auquel il se rapporte. Exemples : Les portes sont fermees. Fatiguee, Marie s'est assise. Une lettre ecrite a la main. Employe avec avoir : le participe passe ne s'accorde jamais avec le sujet. Il s'accorde avec le COD seulement si celui-ci est place AVANT le verbe. Exemples : Elle a mange une pomme (COD apres = pas d'accord). La pomme qu'elle a mangee (COD que = la pomme, place avant = accord). Je les ai vus (les = COD place avant = accord). Methode pour accorder avec avoir : 1) Chercher le COD (il repond a la question qui ? ou quoi ? apres le verbe), 2) Verifier s'il est place avant le verbe, 3) Si oui, accorder avec ce COD. Si pas de COD ou COD apres : pas d'accord. Attention aux pronoms COD (le, la, les, l', que) qui sont toujours places avant.",
        "keywords": ["participe passe", "accord", "auxiliaire etre", "auxiliaire avoir", "COD", "genre", "nombre"],
        "prerequis": ["temps composes", "COD", "auxiliaires"],
        "typical_questions": ["Quand accorde-t-on le participe passe ?", "Comment savoir si on accorde avec avoir ?", "Quelle est la regle avec etre ?"],
        "common_errors": ["Accorder avec le sujet quand l'auxiliaire est avoir", "Oublier d'accorder quand le COD est avant", "Confondre l'auxiliaire etre et avoir"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "orthographe", "participe passe", "accord", "programme_5eme"],
        "learning_objectives": ["Maitriser l'accord du participe passe avec etre", "Appliquer la regle d'accord avec avoir", "Identifier la position du COD"]
    },
    {
        "title": "Synonymes et antonymes",
        "domaine": "Etude de la langue",
        "sousdomaine": "Lexique",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Les synonymes sont des mots de meme nature grammaticale qui ont un sens proche ou identique. Ils permettent d'eviter les repetitions et d'enrichir son vocabulaire. Exemples : maison/demeure/habitation, beau/joli/magnifique, manger/se nourrir/devorer. Attention : les synonymes n'ont pas toujours exactement le meme sens. Ils peuvent differer par leur intensite (colere/fureur), leur registre de langue (voiture/bagnole/vehicule), ou leur precision (regarder/observer/contempler). Les antonymes sont des mots de sens contraire. Ils appartiennent a la meme classe grammaticale. Exemples : grand/petit, chaud/froid, entrer/sortir, possible/impossible. Les antonymes peuvent se former par prefixation : possible/impossible, heureux/malheureux, faire/defaire, adroit/maladroit (prefixes in-, im-, mal-, de-). Utilite : les synonymes enrichissent le style, evitent les repetitions, permettent de nuancer ; les antonymes structurent un texte par opposition, creent des effets de contraste (antithese). Pour trouver un synonyme ou antonyme, utiliser un dictionnaire des synonymes.",
        "keywords": ["synonyme", "antonyme", "contraire", "sens proche", "prefixe", "registre de langue", "nuance"],
        "prerequis": ["nature des mots", "vocabulaire de base"],
        "typical_questions": ["Qu'est-ce qu'un synonyme ?", "Comment trouver l'antonyme d'un mot ?", "Pourquoi utiliser des synonymes ?"],
        "common_errors": ["Donner un synonyme d'une autre classe grammaticale", "Utiliser un synonyme dans un mauvais registre", "Confondre synonyme et mot de la meme famille"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "lexique", "synonyme", "antonyme", "programme_5eme"],
        "learning_objectives": ["Definir synonyme et antonyme", "Enrichir son vocabulaire par les synonymes", "Former des antonymes par prefixation"]
    },
    {
        "title": "Sens propre et sens figure",
        "domaine": "Etude de la langue",
        "sousdomaine": "Lexique",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Le sens propre d'un mot est son sens premier, concret, litteral. C'est le sens de base, souvent physique ou materiel. Exemples : La lumiere du soleil eclaire la piece (lumiere = rayons lumineux). Il monte l'escalier (monter = aller vers le haut physiquement). Le sens figure est un sens image, abstrait, derive du sens propre par analogie ou metaphore. Exemples : Cette explication a eclaire ma comprehension (eclaire = fait comprendre). Les prix montent (monter = augmenter). Un mot peut avoir plusieurs sens figures selon les contextes. Le mot coeur : sens propre = organe qui pompe le sang ; sens figures = centre (le coeur de la ville), courage (avoir du coeur), sentiments amoureux (affaire de coeur). Pour identifier le sens : se demander si le mot peut etre pris au pied de la lettre (sens propre) ou s'il evoque autre chose (sens figure). Le contexte aide a determiner le sens. Les expressions figees utilisent souvent le sens figure : avoir le cafard (etre triste), donner sa langue au chat (renoncer a deviner), tomber dans les pommes (s'evanouir).",
        "keywords": ["sens propre", "sens figure", "litteral", "image", "abstrait", "concret", "expression figee", "contexte"],
        "prerequis": ["vocabulaire", "comprehension de texte"],
        "typical_questions": ["Quelle est la difference entre sens propre et sens figure ?", "Dans quel sens est utilise ce mot ?", "Qu'est-ce qu'une expression figee ?"],
        "common_errors": ["Confondre sens propre et sens figure", "Interpreter litteralement une expression figuree"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "lexique", "sens propre", "sens figure", "programme_5eme"],
        "learning_objectives": ["Distinguer sens propre et sens figure", "Identifier le sens d'un mot en contexte", "Comprendre les expressions figurees"]
    },
    {
        "title": "Les niveaux de langue",
        "domaine": "Etude de la langue",
        "sousdomaine": "Lexique",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Les niveaux de langue (ou registres de langue) correspondent a differentes facons de s'exprimer selon la situation de communication. On distingue trois niveaux. Le niveau familier est utilise a l'oral, entre proches, dans des contextes detendus. Il emploie un vocabulaire simple ou argotique, des phrases courtes, parfois incorrectes grammaticalement, des contractions. Exemples : T'as vu ? Y'a un mec qui arrive. C'est super cool ! Le niveau courant (ou standard) est le plus utilise, a l'oral et a l'ecrit, dans les situations quotidiennes. Il respecte les regles de grammaire, utilise un vocabulaire usuel. Exemples : Tu as vu ? Il y a quelqu'un qui arrive. C'est tres bien ! Le niveau soutenu (ou soigne) est utilise a l'ecrit litteraire ou administratif, dans des situations formelles. Il emploie un vocabulaire riche et precis, des phrases complexes, des tournures recherchees. Exemples : Avez-vous apercu cet individu qui s'avance ? C'est remarquable ! Choisir son niveau selon : l'interlocuteur (ami, professeur, inconnu), le contexte (conversation, examen, lettre officielle), le support (SMS, dissertation, discours). A l'ecole, on utilise le niveau courant ou soutenu.",
        "keywords": ["niveau de langue", "registre", "familier", "courant", "soutenu", "situation de communication", "oral", "ecrit"],
        "prerequis": ["vocabulaire", "communication"],
        "typical_questions": ["Quels sont les trois niveaux de langue ?", "Quand utiliser le niveau soutenu ?", "Comment reconnaitre le niveau familier ?"],
        "common_errors": ["Utiliser le niveau familier dans une redaction", "Confondre niveau soutenu et niveau correct"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "lexique", "niveaux de langue", "registre", "programme_5eme"],
        "learning_objectives": ["Identifier les trois niveaux de langue", "Adapter son niveau au contexte", "Reformuler dans un autre niveau"]
    },
    {
        "title": "L'utopie - Genre litteraire",
        "domaine": "Litterature",
        "sousdomaine": "Regarder le monde, inventer des mondes",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "L'utopie est un genre litteraire qui decrit une societe ideale, parfaite, imaginaire. Le mot vient du grec ou-topos signifiant lieu qui n'existe pas (invente par Thomas More en 1516). Caracteristiques de l'utopie : elle presente un monde ideal ou tout est organise pour le bonheur collectif ; elle critique indirectement la societe reelle en montrant ce qu'elle devrait etre ; elle se situe souvent dans un lieu isole (ile, vallee cachee) ou un temps lointain ; elle decrit des lois, une organisation sociale, une education ideales. Exemples celebres : L'Utopia de Thomas More (1516), L'Abbaye de Theleme dans Gargantua de Rabelais, L'Eldorado dans Candide de Voltaire, les iles utopiques dans les recits de voyage. La contre-utopie (ou dystopie) est le genre inverse : elle presente une societe cauchemardesque, totalitaire, pour alerter sur les dangers de certaines evolutions (1984 d'Orwell, Le Meilleur des mondes d'Huxley). L'utopie fait reflechir : en imaginant l'ideal, elle nous invite a questionner notre propre societe et a rever d'ameliorations possibles.",
        "keywords": ["utopie", "dystopie", "societe ideale", "Thomas More", "critique sociale", "imaginaire", "ile"],
        "prerequis": ["genres litteraires", "recit"],
        "typical_questions": ["Qu'est-ce qu'une utopie ?", "Pourquoi les auteurs inventent-ils des utopies ?", "Quelle difference entre utopie et dystopie ?"],
        "common_errors": ["Confondre utopie et reve irrealiste", "Oublier la dimension critique de l'utopie"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "litterature", "utopie", "programme_5eme"],
        "learning_objectives": ["Definir le genre utopique", "Comprendre la fonction critique de l'utopie", "Distinguer utopie et dystopie"]
    },
    {
        "title": "L'homme et la nature - Theme litteraire",
        "domaine": "Litterature",
        "sousdomaine": "Questionnement complementaire",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Le theme de l'homme et la nature traverse toute la litterature. Il interroge les rapports entre l'etre humain et son environnement naturel. Plusieurs visions se degagent. La nature comme source d'emerveillement : les ecrivains celebrent sa beaute, sa puissance, sa diversite (poesie romantique, recits de voyage, descriptions de paysages). La nature comme refuge : face a la societe corrompue, la nature offre un espace de liberte, de ressourcement, de sagesse (Rousseau, le bon sauvage, la vie simple). La nature comme menace : tempetes, catastrophes, betes sauvages montrent une nature hostile que l'homme doit apprivoiser ou combattre (recits d'aventures, naufrages). La nature exploitee ou detruite : la litterature contemporaine denonce les atteintes a l'environnement, la disparition des especes, le rechauffement climatique. Genres concernes : poesie descriptive, recits de voyage (Marco Polo, Bougainville), romans d'aventures (Robinson Crusoe, L'Ile mysterieuse), fables (La Fontaine), ecriture engagee contemporaine. Ce theme invite a reflechir sur notre place dans l'ecosysteme et notre responsabilite envers la planete.",
        "keywords": ["nature", "homme", "environnement", "romantisme", "ecologie", "voyage", "refuge", "menace"],
        "prerequis": ["genres litteraires", "recit", "description"],
        "typical_questions": ["Comment la litterature represente-t-elle la nature ?", "Pourquoi la nature est-elle un theme majeur ?", "Quelles visions de la nature trouve-t-on en litterature ?"],
        "common_errors": ["Reduire ce theme a la simple description de paysages", "Oublier la dimension critique et reflexive"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["francais", "litterature", "nature", "theme", "programme_5eme"],
        "learning_objectives": ["Identifier les differentes visions de la nature", "Analyser le rapport homme-nature dans un texte", "Relier ce theme aux enjeux contemporains"]
    }
]

if __name__ == "__main__":
    filepath = Path(__file__).parent.parent / "data" / "processed" / "college" / "cinquieme" / "francais.jsonl"

    with open(filepath, "a", encoding="utf-8") as f:
        for doc in new_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"[OK] Added {len(new_docs)} documents to francais.jsonl")
    print("  - Phrase simple et phrase complexe")
    print("  - Les mots invariables")
    print("  - Proposition subordonnee (intro)")
    print("  - Accord du participe passe")
    print("  - Synonymes et antonymes")
    print("  - Sens propre et sens figure")
    print("  - Niveaux de langue")
    print("  - L'utopie")
    print("  - L'homme et la nature")

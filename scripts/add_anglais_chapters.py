#!/usr/bin/env python3
"""Add missing English chapters for 5eme."""

import json
from pathlib import Path

new_docs = [
    {
        "title": "Comparatives - Comparatifs",
        "domaine": "Grammar",
        "sousdomaine": "Comparatives and Superlatives",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "Comparatives are used to compare two things or people. Short adjectives (1-2 syllables): add -er + than. Examples: tall -> taller than (My brother is taller than me), fast -> faster than, big -> bigger than (double final consonant), easy -> easier than (y becomes i). Long adjectives (3+ syllables): use more + adjective + than. Examples: beautiful -> more beautiful than (Paris is more beautiful than expected), expensive -> more expensive than, interesting -> more interesting than. Irregular comparatives: good -> better than, bad -> worse than, far -> farther/further than. For equality: as + adjective + as (She is as tall as her sister). For inferiority: not as + adjective + as OR less + adjective + than. Common mistakes: Never say more taller or more better. Pronunciation: than is often pronounced with a weak vowel sound.",
        "keywords": ["comparative", "adjectives", "than", "more", "-er", "comparison", "grammar"],
        "prerequis": ["adjectives", "basic sentence structure"],
        "typical_questions": ["How do we form comparatives?", "When do we use more?", "What are the irregular comparatives?"],
        "common_errors": ["Using more with short adjectives (more big)", "Forgetting to double consonants (biger instead of bigger)", "Mixing up than and then"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "grammar", "comparatives", "programme_5eme"],
        "learning_objectives": ["Form comparatives with short adjectives", "Form comparatives with long adjectives", "Use irregular comparatives correctly"]
    },
    {
        "title": "Superlatives - Superlatifs",
        "domaine": "Grammar",
        "sousdomaine": "Comparatives and Superlatives",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "Superlatives compare one thing to all others in a group (3+). They express the highest degree. Short adjectives: the + adjective + -est. Examples: tall -> the tallest (He is the tallest in the class), fast -> the fastest, big -> the biggest (double consonant), easy -> the easiest (y becomes i). Long adjectives: the most + adjective. Examples: beautiful -> the most beautiful (It's the most beautiful city), expensive -> the most expensive, interesting -> the most interesting. Irregular superlatives: good -> the best, bad -> the worst, far -> the farthest/furthest. The article THE is always used before superlatives. We often add in/of after superlatives: the best in the world, the tallest of all. For inferiority: the least + adjective (the least expensive option). Note: Superlatives compare 3+ items; comparatives compare only 2. Common pattern: This is the -est / most + adjective + noun + I have ever + past participle. Example: This is the best movie I have ever seen.",
        "keywords": ["superlative", "the most", "the -est", "comparison", "adjectives", "grammar"],
        "prerequis": ["comparatives", "adjectives", "articles"],
        "typical_questions": ["How do we form superlatives?", "When do we use the most?", "What's the difference between comparative and superlative?"],
        "common_errors": ["Forgetting THE before superlatives", "Using most with short adjectives", "Confusing comparative and superlative forms"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "grammar", "superlatives", "programme_5eme"],
        "learning_objectives": ["Form superlatives correctly", "Use THE with superlatives", "Distinguish superlatives from comparatives"]
    },
    {
        "title": "Relative pronouns - Pronoms relatifs",
        "domaine": "Grammar",
        "sousdomaine": "Clauses",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Relative pronouns introduce relative clauses that give more information about a noun. WHO is used for people: The man who lives next door is a teacher. That's the girl who won the competition. WHICH is used for things and animals: The book which I'm reading is interesting. The cat which is sleeping is mine. THAT can replace who or which in defining clauses: The man that lives next door (= who). The book that I'm reading (= which). THAT is more common in spoken English. WHERE is used for places: The house where I was born. This is the school where I study. WHEN is used for time: I remember the day when we met. Defining vs non-defining clauses: Defining clauses are essential to identify the noun (no commas): The girl who is wearing red is my sister. Non-defining clauses add extra information (with commas): My sister, who lives in Paris, is a doctor. You cannot use THAT in non-defining clauses.",
        "keywords": ["relative pronoun", "who", "which", "that", "where", "when", "relative clause"],
        "prerequis": ["sentence structure", "nouns", "pronouns"],
        "typical_questions": ["When do we use who vs which?", "Can we use that instead of who?", "What's a relative clause?"],
        "common_errors": ["Using which for people", "Using who for things", "Forgetting commas in non-defining clauses"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "grammar", "relative pronouns", "programme_5eme"],
        "learning_objectives": ["Choose the correct relative pronoun", "Form relative clauses", "Distinguish defining and non-defining clauses"]
    },
    {
        "title": "Vocabulary - Food and meals",
        "domaine": "Vocabulary",
        "sousdomaine": "Daily life",
        "content_type": "definition",
        "difficulty": "decouverte",
        "content": "Essential food and meal vocabulary. Meals: breakfast (petit dejeuner), lunch (dejeuner), dinner (diner), snack (gouter). Cooking verbs: to cook, to bake, to fry, to boil, to grill, to roast. Common foods - Fruits: apple, banana, orange, strawberry, grape, pear, cherry. Vegetables: carrot, potato, tomato, lettuce, onion, peas, beans. Meat and fish: chicken, beef, pork, lamb, fish, salmon, tuna. Dairy: milk, cheese, butter, yogurt, cream, eggs. Drinks: water, juice, tea, coffee, soda. At the table: plate, glass, knife, fork, spoon, napkin. Useful expressions: I'm hungry (j'ai faim), I'm thirsty (j'ai soif), Would you like some...?, Can I have...?, It's delicious!, I don't like... Countable vs uncountable: bread, rice, sugar, water are uncountable (some water, NOT a water). Use some in affirmative, any in negative/questions: I have some milk. Do you have any eggs?",
        "keywords": ["food", "meals", "vocabulary", "eating", "cooking", "countable", "uncountable"],
        "prerequis": ["basic vocabulary", "some/any"],
        "typical_questions": ["How do you say dejeuner in English?", "What's the difference between some and any?", "Name 5 vegetables in English"],
        "common_errors": ["Saying a water instead of some water", "Confusing breakfast and lunch times", "Mispronouncing vegetables"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "vocabulary", "food", "programme_5eme"],
        "learning_objectives": ["Know meal vocabulary", "Name common foods", "Use countable/uncountable correctly"]
    },
    {
        "title": "Vocabulary - Travel and transport",
        "domaine": "Vocabulary",
        "sousdomaine": "Travel",
        "content_type": "definition",
        "difficulty": "decouverte",
        "content": "Travel and transport vocabulary. Means of transport: car, bus, train, plane (airplane/aeroplane), boat, ship, bicycle (bike), motorcycle, taxi, underground/metro/subway, tram. Prepositions: by car/bus/train/plane/bike (without article), on foot, in a car (inside), on a bus/train/plane (public transport). Places: airport, train station, bus stop, harbour/port, petrol station (UK)/gas station (US). Travel vocabulary: ticket, passport, luggage/baggage, suitcase, boarding pass, delay, to book, to check in. Actions: to take the bus, to catch a train, to miss a flight, to travel, to arrive, to depart. Directions: turn left/right, go straight on, it's on the left/right, next to, opposite, between, behind, in front of. Questions: How do you get to school? I go by bus. How long does it take? It takes 20 minutes. What time does the train leave/arrive? British vs American: underground (UK) = subway (US), petrol (UK) = gas (US), railway (UK) = railroad (US).",
        "keywords": ["travel", "transport", "directions", "airport", "train", "vocabulary"],
        "prerequis": ["basic vocabulary", "prepositions"],
        "typical_questions": ["How do you travel to school?", "What preposition do we use with transport?", "How do you give directions in English?"],
        "common_errors": ["Saying by the bus instead of by bus", "Confusing on foot and by foot", "Using wrong prepositions with transport"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "vocabulary", "travel", "transport", "programme_5eme"],
        "learning_objectives": ["Name means of transport", "Use correct prepositions", "Ask and give directions"]
    },
    {
        "title": "Vocabulary - Environment",
        "domaine": "Vocabulary",
        "sousdomaine": "Environment",
        "content_type": "definition",
        "difficulty": "standard",
        "content": "Environment vocabulary. Nature: forest, tree, river, lake, sea, ocean, mountain, beach, desert, field, flower, grass. Animals: wild animals (lion, elephant, tiger, bear, wolf), farm animals (cow, pig, sheep, horse, chicken), pets (dog, cat, rabbit, hamster). Environmental issues: pollution, climate change, global warming, deforestation, endangered species, recycling, waste, rubbish/garbage. Actions: to recycle, to save energy, to protect, to pollute, to waste, to reduce, to reuse. Weather and climate: sunny, rainy, cloudy, windy, stormy, hot, cold, warm, cool. Useful expressions: We should protect the environment. We must save water. Plastic is bad for the planet. Turn off the lights to save energy. Endangered animals might become extinct. The 3 Rs: Reduce (use less), Reuse (use again), Recycle (make new products from waste). This topic connects to geography and science lessons.",
        "keywords": ["environment", "nature", "pollution", "recycling", "animals", "climate", "vocabulary"],
        "prerequis": ["basic vocabulary", "modal verbs"],
        "typical_questions": ["How can we protect the environment?", "What does endangered mean?", "What are the 3 Rs?"],
        "common_errors": ["Confusing weather and climate", "Using wrong vocabulary (pollution/pullution)", "Forgetting article with environment (THE environment)"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "vocabulary", "environment", "programme_5eme"],
        "learning_objectives": ["Use environmental vocabulary", "Express opinions about ecology", "Discuss environmental actions"]
    },
    {
        "title": "Communication - Expressing opinions",
        "domaine": "Communication",
        "sousdomaine": "Opinions",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "Expressing opinions in English. Giving your opinion: I think (that)..., I believe (that)..., In my opinion..., I feel that..., Personally, I..., From my point of view..., As far as I'm concerned... Agreeing: I agree (with you), You're right, That's true, Exactly, Absolutely, I think so too. Disagreeing (politely): I disagree, I don't think so, I'm not sure about that, I see your point but..., I'm afraid I don't agree, That's not how I see it. Asking for opinions: What do you think?, What's your opinion?, Do you agree?, How do you feel about...?, What do you think about...? Giving reasons: Because..., That's why..., The reason is..., For example... Hedging (being less direct): I think..., Maybe..., Perhaps..., It seems to me that..., I suppose... Example dialogue: What do you think about school uniforms? - Personally, I think they're a good idea because everyone looks the same. - I see your point, but I disagree. I believe students should express their personality through their clothes.",
        "keywords": ["opinion", "agree", "disagree", "communication", "expressing views", "dialogue"],
        "prerequis": ["basic sentence structure", "present simple"],
        "typical_questions": ["How do you say your opinion politely?", "How do you agree or disagree?", "What expressions introduce an opinion?"],
        "common_errors": ["Being too direct when disagreeing", "Forgetting that after I think", "Using I am agree instead of I agree"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "communication", "opinions", "programme_5eme"],
        "learning_objectives": ["Express opinions in English", "Agree and disagree politely", "Support opinions with reasons"]
    },
    {
        "title": "Communication - Describing past events",
        "domaine": "Communication",
        "sousdomaine": "Narration",
        "content_type": "methode",
        "difficulty": "standard",
        "content": "Describing past events and experiences. Time markers for the past: yesterday, last week/month/year, ago (two days ago, a week ago), in 2020, when I was young, once, at that time. Sequencing words: first, then, after that, next, later, finally, in the end. Useful structures: I went to... and saw..., It was (amazing/boring/fun), We had a great time, The best part was when..., I remember when..., I'll never forget... Describing experiences: What happened? - First, we went to the beach. Then we had a picnic. After that, we played volleyball. Finally, we watched the sunset. Using past simple and past continuous together: I was walking home when it started to rain (interrupted action). While I was studying, my phone rang. Giving details: Where did it happen?, When was it?, Who were you with?, What did you do?, How did you feel? Example: Last summer, I went to Spain with my family. We stayed in Barcelona for a week. The weather was beautiful. We visited the Sagrada Familia - it was amazing! I had a wonderful time.",
        "keywords": ["past events", "narration", "past simple", "past continuous", "time markers", "sequencing"],
        "prerequis": ["past simple", "past continuous", "time expressions"],
        "typical_questions": ["How do you describe what happened?", "What words do we use to sequence events?", "How do you talk about your holidays?"],
        "common_errors": ["Mixing up tenses", "Forgetting irregular past forms", "Not using sequencing words"],
        "version": "2.0.0",
        "confidence_level": 1.0,
        "review_status": "validated",
        "tags": ["anglais", "communication", "past", "narration", "programme_5eme"],
        "learning_objectives": ["Narrate past events clearly", "Use sequencing words", "Combine past simple and continuous"]
    }
]

if __name__ == "__main__":
    filepath = Path(__file__).parent.parent / "data" / "processed" / "college" / "cinquieme" / "anglais.jsonl"

    with open(filepath, "a", encoding="utf-8") as f:
        for doc in new_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"[OK] Added {len(new_docs)} documents to anglais.jsonl")
    print("  - Comparatives")
    print("  - Superlatives")
    print("  - Relative pronouns")
    print("  - Vocabulary: Food and meals")
    print("  - Vocabulary: Travel and transport")
    print("  - Vocabulary: Environment")
    print("  - Communication: Expressing opinions")
    print("  - Communication: Describing past events")

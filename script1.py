import json
import random
import yaml
from multiprocessing import Pool, cpu_count, Manager
from tqdm import tqdm

# CONFIG
DIFFICULTIES = ["easy", "medium", "hard"]
SETS_PER_DIFFICULTY = 5
QUESTIONS_PER_SET = 20
POS_CATEGORIES = ["adjective", "verb", "noun"]
NOUN_SAMPLE_SIZE = 10000  # Limit noun processing to 10,000 words

# Load dataset
with open("synonyms.json", "r") as f:
    raw_data = json.load(f)

# Parse synonyms (noun + noun:satellite etc.)
def parse_data(data):
    parsed = {pos: {} for pos in POS_CATEGORIES}
    for key, value in data.items():
        if ":" not in key:
            continue
        word, tag = key.rsplit(":", 1)
        tag = tag.strip().lower()
        synonyms = [s.strip() for s in value.replace("|", ";").replace(",", ";").split(";") if s.strip()]
        if not synonyms:
            continue
        if "noun" in tag:
            parsed["noun"][word] = synonyms
        elif "adjective" in tag:
            parsed["adjective"][word] = synonyms
        elif "verb" in tag:
            parsed["verb"][word] = synonyms
    return parsed

# Worker function with shared counter
def question_worker(args):
    word, synonyms, pool_words, counter = args
    correct = synonyms[0]
    synonym_set = set(synonyms)
    distractor_pool = [w for w in pool_words if w != word and w not in synonym_set]
    counter.value += 1
    if len(distractor_pool) < 3:
        return None
    distractors = random.sample(distractor_pool, 3)
    options = [{"correct": True, "value": correct, "detail": f"'{correct}' is a synonym for '{word}'."}]
    for d in distractors:
        options.append({
            "correct": False,
            "value": d,
            "detail": f"'{d}' is not a synonym for '{word}'."
        })
    random.shuffle(options)
    return {"text": f"What is a synonym for '{word}'?", "options": options}

# Generate quizzes and save
def generate_quizzes(pos, entries):
    all_words = list(entries.keys())
    
    # Limit noun processing to 10,000 words if the category is "noun"
    if pos == "noun" and len(all_words) > NOUN_SAMPLE_SIZE:
        all_words = random.sample(all_words, NOUN_SAMPLE_SIZE)

    pool_words = all_words.copy()

    print(f"[{pos}] Starting multiprocessing with {cpu_count()} workers...")

    with Manager() as manager:
        counter = manager.Value('i', 0)
        args = [(word, entries[word], pool_words, counter) for word in all_words]

        with Pool(processes=cpu_count()) as pool:
            results = []
            with tqdm(total=len(all_words), desc=f"[{pos}] Generating", unit="words") as pbar:
                for res in pool.imap_unordered(question_worker, args):
                    results.append(res)
                    pbar.update(1)

    all_questions = list(filter(None, results))
    random.shuffle(all_questions)
    print(f"\n{pos.upper()}: Total valid questions = {len(all_questions)}")

    filenames = []
    idx = 0
    for difficulty in DIFFICULTIES:
        for i in range(1, SETS_PER_DIFFICULTY + 1):
            questions = all_questions[idx:idx + QUESTIONS_PER_SET]
            if len(questions) < QUESTIONS_PER_SET:
                print(f"[!] Skipping {pos}-{difficulty}{i} — only {len(questions)} questions left.")
                break
            idx += QUESTIONS_PER_SET
            quiz_id = f"{pos}-{difficulty}{i}"
            filename = f"{quiz_id}.yaml"
            quiz = {
                "description": f"Synonym questions - {difficulty.title()} Set {i}",
                "topic": pos,
                "id": quiz_id,
                "title": f"{pos.title()} Synonyms - {difficulty.title()} {i}",
                "questions": questions
            }
            with open(filename, "w") as f:
                yaml.dump(quiz, f, sort_keys=False)
            print(f"[✓] Saved: {filename}")
            filenames.append({
                "title": f"{difficulty.title()} {i}",
                "description": f"Synonym questions - {difficulty.title()} Set {i}",
                "id": quiz_id,
                "file": filename
            })
    return filenames

# MAIN
parsed = parse_data(raw_data)

for pos in POS_CATEGORIES:
    print(f"{pos.upper()}: {len(parsed[pos])} words")

index = {}
for pos in POS_CATEGORIES:
    quiz_list = generate_quizzes(pos, parsed[pos])
    index[pos] = quiz_list

with open("quiz_index.yaml", "w") as f:
    yaml.dump(index, f, sort_keys=False)

print("\n[✓] All quizzes saved. Index file: quiz_index.yaml")

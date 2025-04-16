import json
import os
import random
import yaml
import difflib
import re
import concurrent.futures
from tqdm import tqdm
import multiprocessing
from functools import lru_cache
import time
import sys

# CONFIGURATION
DIFFICULTIES = ["easy", "medium", "hard"]
SETS_PER_DIFFICULTY = 5
QUESTIONS_PER_SET = 20
POS_CATEGORIES = ["verb", "noun"]
MAX_WORKERS = min(16, multiprocessing.cpu_count())
TEST_LIMIT = 500  # Set to None to process all words

tqdm_kwargs = dict(file=sys.stdout, dynamic_ncols=True)

# --- Utility Functions ---

def clean_word(word):
    word = word.strip().lower()
    if not word:
        return None
    if re.search(r"[^\w\s\-]", word):
        return None
    if len(word.split()) > 2:
        return None
    return word

@lru_cache(maxsize=100_000)
def is_similar(word1, word2, threshold=0.7):
    return difflib.SequenceMatcher(None, word1.lower(), word2.lower()).ratio() >= threshold

# --- Load and Parse Data ---

with open("synonyms.json", "r") as f:
    raw_data = json.load(f)

def parse_data(data):
    parsed = {pos: {} for pos in POS_CATEGORIES}
    print("📦 Parsing data...")

    for key, value in data.items():
        if ":" not in key:
            continue
        word, pos = key.rsplit(":", 1)
        word = clean_word(word)
        if not word or pos not in POS_CATEGORIES:
            continue
        raw_syns = value.replace("|", ";").replace(",", ";").split(";")
        synonyms = [clean_word(s) for s in raw_syns]
        synonyms = [s for s in synonyms if s and not is_similar(word, s)]
        if synonyms:
            parsed[pos][word] = synonyms

    print("✅ Data parsing complete.")
    return parsed

# --- Preprocess Distractors ---

def build_distractor_pool(entries):
    all_words = list(entries.keys())
    distractor_map = {}
    print(f"🔄 Building distractor pool ({len(all_words)} words)...")
    for word in tqdm(all_words, desc="Building Distractors", **tqdm_kwargs):
        synonyms = entries[word]
        if not synonyms:
            continue
        correct = synonyms[0]
        distractors = [
            w for w in all_words
            if w != word and w not in synonyms and not is_similar(w, correct)
        ]
        distractor_map[word] = distractors
    print(f"✅ Distractor pool built with {len(distractor_map)} entries.")
    return distractor_map

# --- Question Generator ---

QUESTION_TEMPLATES = [
    "What word means the same as '{word}'?",
    "Choose the word that is most similar in meaning to '{word}'.",
    "Which of the following is a synonym of '{word}'?",
    "Select the best synonym for the word '{word}'.",
    "Pick the correct synonym for '{word}'."
]

def make_question(word, synonyms, distractor_pool):
    if not synonyms or not distractor_pool.get(word):
        return None
    correct = synonyms[0]
    distractors = distractor_pool[word]
    if len(distractors) < 3:
        return None

    options = [{
        "correct": True,
        "value": correct,
        "detail": f"'{correct}' is a synonym for '{word}'."
    }]

    for d in random.sample(distractors, 3):
        options.append({
            "correct": False,
            "value": d,
            "detail": f"'{d}' is not a synonym for '{word}'."
        })

    random.shuffle(options)
    question_text = random.choice(QUESTION_TEMPLATES).format(word=word)
    return {"text": question_text, "options": options}

# --- Quiz Generator per POS ---

def generate_quizzes_for_category(pos, entries):
    print(f"\n📚 Generating quizzes for {pos}... Total words: {len(entries)}")
    
    # Build distractor pool
    distractor_pool = build_distractor_pool(entries)

    # Limit for debug/testing
    all_words = list(entries.keys())
    if TEST_LIMIT:
        all_words = all_words[:TEST_LIMIT]
    print(f"🧠 Preparing to generate questions for {len(all_words)} words.")

    all_questions = []
    start_time = time.perf_counter()

    # Threaded question generation
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(make_question, word, entries[word], distractor_pool): word
            for word in all_words if entries[word]
        }

        print(f"🚦 Submitted {len(futures)} tasks for question generation.")

        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures),
                           desc=f"Processing {pos}", **tqdm_kwargs):
            try:
                q = future.result()
                if q:
                    all_questions.append(q)
            except Exception as e:
                print(f"⚠️ Error processing '{futures[future]}': {e}")

    end_time = time.perf_counter()
    print(f"✅ Finished question generation for {pos} in {end_time - start_time:.2f}s.")
    print(f"📝 Generated {len(all_questions)} questions for {pos}.")

    # Shuffle and group into quizzes
    random.shuffle(all_questions)
    filenames = []
    idx = 0
    total_sets = SETS_PER_DIFFICULTY * len(DIFFICULTIES)
    pbar = tqdm(total=total_sets, desc=f"Creating quizzes [{pos}]", position=POS_CATEGORIES.index(pos), **tqdm_kwargs)

    for difficulty in DIFFICULTIES:
        for i in range(1, SETS_PER_DIFFICULTY + 1):
            questions = all_questions[idx:idx + QUESTIONS_PER_SET]
            if len(questions) < QUESTIONS_PER_SET:
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
            filenames.append({
                "title": f"{difficulty.title()} {i}",
                "description": f"Synonym questions - {difficulty.title()} Set {i}",
                "id": quiz_id,
                "file": filename
            })
            pbar.update(1)

    pbar.close()
    print(f"✅ Quiz sets created for {pos}.")
    return pos, filenames

# --- Full Quiz Generation ---

def generate_all_quizzes(parsed_data):
    index = {}
    print("\n🚀 Starting full quiz generation process...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(POS_CATEGORIES)) as executor:
        results = list(executor.map(
            lambda pos: generate_quizzes_for_category(pos, parsed_data[pos]),
            POS_CATEGORIES
        ))

    for pos, quiz_list in results:
        index[pos] = quiz_list

    print("✅ All quizzes generated successfully.")
    return index

# --- Run the Script ---

if __name__ == "__main__":
    parsed = parse_data(raw_data)
    index = generate_all_quizzes(parsed)

    # Save index file
    with open("quiz_index.yaml", "w") as f:
        yaml.dump(index, f, sort_keys=False)

    print("\n📁 Quiz index saved to 'quiz_index.yaml'. All done!")

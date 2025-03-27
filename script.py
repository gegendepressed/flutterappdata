import json
import random
import yaml
import os
import sys
import multiprocessing
from tqdm import tqdm  # Progress bar

yaml_dir = "quizzes"
os.makedirs(yaml_dir, exist_ok=True)

# Load synonyms JSON
def load_synonyms():
    print("📂 Loading synonyms.json...\n")
    try:
        with open('synonyms.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"❌ Error loading synonyms.json: {e}")
        sys.exit(1)

synonyms_data = load_synonyms()
all_words = list(synonyms_data.keys())
random.shuffle(all_words)

# Split data into chunks for multiprocessing
def chunk_data(data, num_chunks):
    chunk_size = len(data) // num_chunks
    return [data[i * chunk_size: (i + 1) * chunk_size] for i in range(num_chunks)]

# Function to process a chunk
def process_chunk(chunk_id, words_subset):
    categories = {}
    skipped_words = []
    
    print(f"🚀 Processing chunk {chunk_id + 1}... ({len(words_subset)} words)")

    for key in tqdm(words_subset, desc=f"🔄 Chunk {chunk_id+1} Progress", leave=False):
        word, category = key.split(':') if ':' in key else (key, "unknown")
        
        if category not in categories:
            categories[category] = {"easy": [], "medium": [], "hard": []}

        synonyms = list(set(synonyms_data[key].split(';')))
        
        if len(synonyms) < 1:
            skipped_words.append(word)
            continue

        word_length = len(word)
        synonym_count = len(synonyms)
        difficulty = "hard" if word_length > 8 or synonym_count < 3 else "medium" if word_length <= 8 else "easy"
        
        distractors = [w for w in all_words if w != word]
        distractors = random.sample(distractors, min(3, len(distractors)))

        if len(distractors) < 1:
            skipped_words.append(word)
            continue
        
        question = {
            "text": f"What is a synonym for \"{word}\"?",
            "difficulty": difficulty,
            "options": [
                {"correct": True, "value": random.choice(synonyms), "detail": f'Correct! "{synonyms[0]}" is a synonym for "{word}".'},
                *[{"correct": False, "value": wrong, "detail": f'Incorrect, "{wrong}" is not a synonym for "{word}".'} for wrong in distractors]
            ]
        }
        categories[category][difficulty].append(question)

    print(f"✅ Finished processing chunk {chunk_id + 1}!")
    
    return categories, skipped_words

# Function to save YAML
def save_yaml(file_name, data):
    with open(file_name, 'w', encoding='utf-8') as yaml_file:
        yaml.dump(data, yaml_file, allow_unicode=True, default_flow_style=False)

# Main processing function
def main():
    
    print(f"🔢 Splitting {len(all_words)} words into {num_processes} parallel chunks...\n")
    
    with multiprocessing.Pool(num_processes) as pool:
        results = pool.starmap(process_chunk, [(i, chunk) for i, chunk in enumerate(chunks)])
    
    combined_categories = {}
    skipped_words = []
    
    for categories, skipped in results:
        skipped_words.extend(skipped)
        for category, difficulties in categories.items():
            if category not in combined_categories:
                combined_categories[category] = {"easy": [], "medium": [], "hard": []}
            for difficulty in ["easy", "medium", "hard"]:
                combined_categories[category][difficulty].extend(difficulties[difficulty])
    
    # Save skipped words
    with open("skipped_words.txt", "w") as log_file:
        log_file.write("\n".join(skipped_words))
    
    num_files = 10
    questions_per_file = 20
    
    print("\n📁 Saving quizzes into YAML files...\n")
    
    for category, difficulties in combined_categories.items():
        category_path = os.path.join(yaml_dir, category)
        os.makedirs(category_path, exist_ok=True)
        quiz_entries = []
        
        for difficulty in ["easy", "medium", "hard"]:
            filtered_questions = difficulties[difficulty]
            random.shuffle(filtered_questions)
            
            for i in range(num_files):
                start_idx = i * questions_per_file
                end_idx = start_idx + questions_per_file
                file_questions = filtered_questions[start_idx:end_idx]
                
                if not file_questions:
                    break
                
                file_name = f"{category_path}/{difficulty}_{i+1}.yaml"
                save_yaml(file_name, {"questions": file_questions})
            
            quiz_entries.append({
                "description": f"Synonyms for {category.capitalize()} ({difficulty.capitalize()})",
                "id": f"{category}-{difficulty}",
                "title": f"{category.capitalize()} - {difficulty.capitalize()}"
            })
        
        save_yaml(f"{category_path}/{category}.yaml", {
            "quizzes": quiz_entries,
            "id": category,
            "img": f"{category}.png",
            "title": f"{category.capitalize()} Synonyms"
        })
    
    print("\n✅ All YAML files generated successfully!")
    print(f"⚠️ Skipped {len(skipped_words)} words. See 'skipped_words.txt' for details.\n")

if __name__ == "__main__":
    main()

from datasets import load_dataset
import json
import random
from collections import defaultdict


SEED = 42
NUM_TESTS = 60


# Load English and Indonesian devtest sets
english = load_dataset(
    "openlanguagedata/flores_plus",
    "eng_Latn",
    split="devtest",
)

indonesian = load_dataset(
    "openlanguagedata/flores_plus",
    "ind_Latn",
    split="devtest",
)


# Build Indonesian lookup by ID
indonesian_by_id = {
    row["id"]: row
    for row in indonesian
}


# Build aligned English-Indonesian pairs
pairs = []

for row in english:
    ind_row = indonesian_by_id.get(row["id"])

    if ind_row is None:
        continue

    pairs.append({
        "id": row["id"],
        "english": row["text"],
        "indonesian": ind_row["text"],
        "topic": row["topic"],
        "domain": row["domain"],
        "url": row["url"],
    })


# ---------------------------------------------------------
# Remove duplicate / near-duplicate English sentences
# ---------------------------------------------------------

seen_sentences = set()
unique_pairs = []

for pair in pairs:
    normalized = " ".join(pair["english"].lower().split())

    if normalized in seen_sentences:
        continue

    seen_sentences.add(normalized)
    unique_pairs.append(pair)


# ---------------------------------------------------------
# Bucket sentences by topic
# ---------------------------------------------------------

topic_buckets = defaultdict(list)

for pair in unique_pairs:
    topic_buckets[pair["topic"]].append(pair)


# ---------------------------------------------------------
# Deterministic sampling
#
# First distribute samples across topics so that the
# benchmark is not dominated by a few consecutive articles.
# ---------------------------------------------------------

rng = random.Random(SEED)

for bucket in topic_buckets.values():
    rng.shuffle(bucket)


selected = []

topics = list(topic_buckets.keys())
rng.shuffle(topics)

# Round-robin across topics
while len(selected) < NUM_TESTS:
    added_this_round = False

    for topic in topics:
        bucket = topic_buckets[topic]

        if bucket:
            selected.append(bucket.pop())

            added_this_round = True

            if len(selected) >= NUM_TESTS:
                break

    if not added_this_round:
        break


# ---------------------------------------------------------
# Sort by ID for deterministic output
# ---------------------------------------------------------

selected.sort(key=lambda x: int(x["id"]))


# ---------------------------------------------------------
# Create testset
# ---------------------------------------------------------

with open("tests.jsonl", "w", encoding="utf-8") as f:

    for pair in selected:
        item = {
            "question": (
                "Translate this to Bahasa Indonesia: "
                f"{pair['english']}"
            ),
            "reference_answer": pair["indonesian"],
            "keywords": [],
            "category": "flores_devtest",
        }

        f.write(
            json.dumps(
                item,
                ensure_ascii=False
            ) + "\n"
        )


print(
    f"Created tests.jsonl with "
    f"{len(selected)} FLORES+ devtest tests."
)
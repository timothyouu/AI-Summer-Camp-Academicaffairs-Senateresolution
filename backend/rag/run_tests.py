import json
from models.claude_model import ask_claude


# Load test questions
with open("tests/test_questions.json", "r") as file:
    questions = json.load(file)


results = []

# Test each question
for item in questions:
    print(f"Testing question {item['id']}...")

    answer = ask_claude(item["question"])

    results.append(
        {
            "id": item["id"],
            "question": item["question"],
            "answer": answer
        }
    )


# Save results
with open("results/responses.json", "w") as file:
    json.dump(results, file, indent=4)


print("Testing complete! Results saved.")
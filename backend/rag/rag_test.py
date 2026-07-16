from retrieval.search import search_policy
from models.claude_model import ask_claude

question = input("Ask a policy question: ")

context = search_policy(question)

answer = ask_claude(question, context)

print("\n===== Claude's Answer =====\n")
print(answer)
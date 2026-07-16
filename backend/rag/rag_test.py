from config import ACADEMIC_KB_ID
from retrieval.search import search_policy
from models.claude_model import ask_claude

question = input("Ask a policy question: ")

context = search_policy(question, ACADEMIC_KB_ID)

answer = ask_claude(question, context)

print("\n===== Claude's Answer =====\n")
print(answer)

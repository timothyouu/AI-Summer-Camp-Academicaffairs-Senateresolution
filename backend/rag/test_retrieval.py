from retrieval.search import search_policy
from config import ACADEMIC_KB_ID


question = "What is the academic probation policy?"

results = search_policy(
    question,
    ACADEMIC_KB_ID
)

print(results)
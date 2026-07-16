from agent import ask_policy_assistant


test_questions = [
    "How are alternates selected for the Grievance Review Board?",
    
    "What happens if a faculty member has a conflict of interest during evaluation?",
    
    "How are faculty members selected for an Academic Integrity Review Committee?",
    
    "What happens if a board member is no longer eligible to serve?",
    
    "What is the process for creating a new probationary faculty position?"
]


for question in test_questions:
    print("\n" + "="*80)
    print("QUESTION:")
    print(question)

    answer = ask_policy_assistant(question)

    print("\nANSWER:")
    print(answer)
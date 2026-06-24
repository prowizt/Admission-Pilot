import os
import google.generativeai as genai

api_key = ""
with open("backend/.env", "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("STUDENT_API_KEY="):
            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

genai.configure(api_key=api_key)

print("Models:")
for m in genai.list_models():
    print(m.name)

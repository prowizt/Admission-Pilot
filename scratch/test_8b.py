import os
import google.generativeai as genai

api_key = ""
with open("backend/.env", "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("STUDENT_API_KEY="):
            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

if not api_key:
    print("API Key not found.")
    exit(1)

genai.configure(api_key=api_key)

try:
    models = genai.list_models()
    for m in models:
        if "8b" in m.name.lower():
            print(m.name)
except Exception as e:
    print("Error listing models:", e)

try:
    model = genai.GenerativeModel("gemini-1.5-flash-8b")
    res = model.generate_content("hello")
    print("Test gemini-1.5-flash-8b:", res.text)
except Exception as e:
    print("Test gemini-1.5-flash-8b failed:", e)

try:
    model = genai.GenerativeModel("gemini-1.5-flash-8b-latest")
    res = model.generate_content("hello")
    print("Test gemini-1.5-flash-8b-latest:", res.text)
except Exception as e:
    print("Test gemini-1.5-flash-8b-latest failed:", e)

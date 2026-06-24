import os
import google.generativeai as genai

api_key = ""
with open("backend/.env", "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("GEMINI_API_KEY="):
            api_key = line.split("=", 1)[1].strip()

genai.configure(api_key=api_key)

print("Models:")
try:
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods and "8b" in m.name:
            print(m.name)
except Exception as e:
    print("Error:", e)

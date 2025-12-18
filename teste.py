from pydantic import BaseModel
from google.genai import types
from google import genai
from config import api_key
client = genai.Client(api_key=api_key   
                      )


class CountryInfo(BaseModel):
    name: str
    population: int
    capital: str
    continent: str
    gdp: int
    official_language: str
    total_area_sq_mi: int
    woman_percent: float

generation_config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_budget=5000,
        include_thoughts=True,
        
    ),
    response_mime_type='application/json',
    response_schema=CountryInfo,
)

for chunk in client.models.generate_content_stream(
    model='gemini-2.5-flash',
    contents='Give me information for the CEARÁ state in Brazil/',
    config=generation_config,
):
    candidate = chunk.candidates[0]
    candidate_part = candidate.content.parts[0]
    print(candidate_part.text, end="")
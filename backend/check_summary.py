import asyncio
from pathlib import Path
from dotenv import load_dotenv
from app.summarizer import summarize_transcript, SummaryError

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

transcript = (
    "Today we discussed the audio notes project. "
    "Database integration is complete. "
    "Sankalp will add summarization tomorrow and deploy by Saturday."
)

try:
    print(asyncio.run(summarize_transcript(transcript)))
except SummaryError as exc:
    print("Summary failed:", exc)
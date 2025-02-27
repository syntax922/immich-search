##############################
# main.py
##############################

import os
from typing import Any, Dict
import geonamescache
import calendar
import json
import urllib.parse
from datetime import datetime
import re

import spacy
import dateparser
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse


immich_host = os.getenv("IMMICH_HOST", "127.0.0.1")
immich_port = os.getenv("IMMICH_PORT", "2283")

app = FastAPI()

# Load the spaCy transformer model
# Make sure en_core_web_trf is installed in your container environment!
try:
    nlp = spacy.load("en_core_web_trf")
except Exception as e:
    raise RuntimeError(
        "Could not load spaCy model 'en_core_web_trf'. "
        "Ensure it's installed in the container via requirements.txt or manually."
    ) from e

@app.get("/health")
def health_check() -> Dict[str, str]:
    """
    Quick health check endpoint.
    """
    return {"status": "ok"}

@app.post("/parse")
async def parse_query(request: Request) -> Dict[str, Any]:
    data = await request.json()
    user_text = data.get("query", "")
    lowered_text = user_text.lower()

    # Initialize structured result
    structured = {
        "city": None,
        "state": None,
        "country": None,
        "createdAfter": None,
        "createdBefore": None,
        "takenAfter": None,
        "takenBefore": None,
        "isArchived": False,
        "isFavorite": False,
        "isMotion": False,
        "make": None,
        "model": None,
        "remainingQuery": user_text,
    }

    
    # -------------------------------------------------
    # Helper function to parse a date with custom preference
    # For partial dates ("Jan", "Jan 14", "Jan 2024"), append the current year if missing
    # and use "first" for starting dates and "last" for ending dates.
    # -------------------------------------------------
    def parse_date_str(date_str: str, prefer_day: str = "first") -> str:
        # If no year is provided, append the current year.
        if not any(token.isdigit() for token in date_str.split()):
            date_str = f"{date_str} {datetime.now().year}"
        settings = {"PREFER_DAY_OF_MONTH": prefer_day}
        dt = dateparser.parse(date_str, settings=settings)
        if dt:
            if prefer_day == "first":
                dt = dt.replace(hour=0, minute=0, second=0)
            else:  # "last"
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt.isoformat()
        return None


    # -------------------------------------------------
    # Helper function to filter out extraneous tokens for the second date
    # -------------------------------------------------
    def filter_date_tokens(date_str: str) -> str:
        # remove words that are unlikely to belong to a date
        extraneous = {"taken", "with", "iphone", "pixel", "nikon", "canon", "sony", "by", "on", ","}
        tokens = date_str.split()
        filtered = [token for token in tokens if token not in extraneous]
        return " ".join(filtered)

    # -------------------------------------------------
    # Step 1) Check simple booleans by keyword
    # -------------------------------------------------
    if "archived" in lowered_text:
        structured["isArchived"] = True
    if "favorite" in lowered_text or "favourite" in lowered_text:
        structured["isFavorite"] = True
    if "motion" in lowered_text:
        structured["isMotion"] = True

    # -------------------------------------------------
    # Step 2) Basic date parsing improvements
    # -------------------------------------------------

    # Attempt to detect "from <date> to <date>" or "between <date> and <date>"
    if (" from " in lowered_text and (" to " in lowered_text or " through " in lowered_text)) or \
       (" between " in lowered_text and " and " in lowered_text):
        # Normalize "through" to "to" and "between" to "from" for consistent splitting.
        normalized_text = lowered_text.replace(" through ", " to ").replace(" between ", " from ").replace(" and ", " to ")
        after_part = normalized_text.split(" from ", 1)[1]
        parts = after_part.split(" to ", 1)
        if len(parts) == 2:
            # Get the raw date strings.
            date1_str, date2_str = parts[0].strip(), parts[1].strip()
            # Filter extra tokens from the second date string.
            date2_str = filter_date_tokens(date2_str)
            # For the end date, use only the first two tokens (so that "july 2024 an 14" becomes "july 2024").
            tokens_date2 = date2_str.split()
            candidate = date2_str if len(tokens_date2) < 2 else " ".join(tokens_date2[:2])
            # Parse the candidate using the "first" day setting.
            dt_temp = dateparser.parse(candidate, settings={"PREFER_DAY_OF_MONTH": "first"})
            # If the start date string doesn't include a year, append the year from dt_temp or current year.
            if not any(token.isdigit() for token in date1_str):
                year = dt_temp.year if dt_temp else datetime.now().year
                date1_str = f"{date1_str} {year}"
            # Now parse the start date.
            dt1 = parse_date_str(date1_str, prefer_day="first").split("T")[0]
            # Parse the end date: if dt_temp exists, use the last day of that month; otherwise, attempt to parse date2_str directly.
            if dt_temp:
                last_day = calendar.monthrange(dt_temp.year, dt_temp.month)[1]
                dt2_obj = dt_temp.replace(day=last_day)
                dt2 = dt2_obj.isoformat().split("T")[0]
            else:
                dt2 = parse_date_str(date2_str, prefer_day="last").split("T")[0]
            # Assign both taken and created dates
            structured["takenAfter"] = dt1
            structured["takenBefore"] = dt2

    # Handle cases like "taken in 2022", "dogs taken in 2022", or "dogs in 2023"
    elif re.search(r'(?:(?:\b(?:taken|created)\b.*?\bin\s+)|(?:\bin\s+))(?P<year>\d{4})\b', lowered_text, flags=re.IGNORECASE):
        m = re.search(r'(?:(?:\b(?:taken|created)\b.*?\bin\s+)|(?:\bin\s+))(?P<year>\d{4})\b', lowered_text, flags=re.IGNORECASE)
        if m:
            year = int(m.group("year"))
            dt1 = datetime(year, 1, 1).strftime("%Y-%m-%d")
            dt2 = datetime(year, 12, 31).strftime("%Y-%m-%d")
            structured["takenAfter"] = dt1
            structured["takenBefore"] = dt2

    # -------------------------------------------------
    # Step 3) Use spaCy NER for location with refined splitting using geonamescache
    # -------------------------------------------------
    gc = geonamescache.GeonamesCache()
    known_states = {state["name"].lower() for state in gc.get_us_states().values()}
    known_countries = {country["name"].lower() for country in gc.get_countries().values()}

    doc = nlp(user_text)
    for ent in doc.ents:
        if ent.label_ in ("GPE", "LOC"):
            loc_text = ent.text
            # If there is a comma, split parts and check each against our dictionaries
            if "," in loc_text:
                parts = [p.strip() for p in loc_text.split(",")]
                city_part = None
                state_part = None
                country_part = None
                for part in parts:
                    lower_part = part.lower()
                    if lower_part in known_states:
                        state_part = part
                    elif lower_part in known_countries:
                        country_part = part
                    else:
                        if city_part is None:
                            city_part = part
                if city_part and structured["city"] is None:
                    structured["city"] = city_part
                if state_part and structured["state"] is None:
                    structured["state"] = state_part
                if country_part and structured["country"] is None:
                    structured["country"] = country_part
            else:
                # refined splitting: break the location into tokens using whitespace
                parts = loc_text.split()
                city_parts = []
                state_candidate = None
                for part in parts:
                    lower_part = part.lower()
                    if lower_part in known_states:
                        state_candidate = part
                    elif lower_part in known_countries:
                        if structured["country"] is None:
                            structured["country"] = part
                    else:
                        city_parts.append(part)
                if city_parts and structured["city"] is None:
                    structured["city"] = " ".join(city_parts)
                if state_candidate and structured["state"] is None:
                    structured["state"] = state_candidate
                # If a US state was detected but no country exists, default to "United States"
                if state_candidate and structured["country"] is None:
                    structured["country"] = "United States"

    # -------------------------------------------------
    # Step 4) Check for camera "make" / "model"
    # -------------------------------------------------
    if "iphone" in lowered_text:
        structured["make"] = "Apple"
        idx = lowered_text.find("iphone")
        if idx != -1:
            tail = lowered_text[idx:].split()
            if len(tail) > 1 and tail[1].isdigit():
                structured["model"] = f"iPhone {tail[1]}"
            else:
                structured["model"] = "iPhone"

    if "pixel" in lowered_text:
        structured["make"] = "Google"
        idx = lowered_text.find("pixel")
        tail = lowered_text[idx:].split()
        if len(tail) > 1 and tail[1].isdigit():
            structured["model"] = f"Pixel {tail[1]}"
        else:
            structured["model"] = "Pixel"

    if "galaxy" in lowered_text:
        structured["make"] = "Samsung"
        idx = lowered_text.find("galaxy")
        tail = lowered_text[idx:].split()
        if len(tail) > 1 and tail[1].isdigit():
            structured["model"] = f"Galaxy {tail[1]}"
        else:
            structured["model"] = "Galaxy"

    if "nikon" in lowered_text:
        structured["make"] = "Nikon"
    if "canon" in lowered_text:
        structured["make"] = "Canon"
    if "sony" in lowered_text:
        structured["make"] = "Sony"

    # Return the recognized structure
        # Build Immich Search Payload
    immich_body = {
        "city": structured["city"],
        "country": structured["country"],
        "createdAfter": structured["createdAfter"],
        "createdBefore": structured["createdBefore"],
        "takenAfter": structured["takenAfter"],
        "takenBefore": structured["takenBefore"],
        "isArchived": structured["isArchived"],
        "isFavorite": structured["isFavorite"],
        "isMotion": structured["isMotion"],
        "make": structured["make"],
        "model": structured["model"],
        "query": structured["remainingQuery"],  # For CLIP-based text search
        # other fields if relevant
    }

    # Filter out keys that are None, empty strings, or empty lists
    immich_body = {k: v for k, v in immich_body.items() if v not in (None, "", False, [])}

    # Serialize as JSON
    payload_str = json.dumps(immich_body)

    # URL-encode the JSON payload for embedding in the query parameter
    encoded_payload = urllib.parse.quote(payload_str)

    # Build the final URL
    final_url = f"http://{immich_host}:{immich_port}/search?query={encoded_payload}"

    # For example: print or return final_url
    print(final_url)
    return {"query":encoded_payload}


# --- Front-End HTML Search Form ---
@app.get("/", response_class=HTMLResponse)
def search_form():
    html_content = """
    <html>
      <head>
        <title>Immich Smart Search</title>
      </head>
      <body>
        <h1>Immich Smart Search</h1>
        <form id="searchForm" onsubmit="event.preventDefault(); submitQuery(); return false;">
        <input type="text" id="query" name="query" placeholder="Enter your search query" size="80"/>
        <button type="button" onclick="submitQuery()">Search</button>
        </form>
        <p id="resultLink"></p>
        <script>
          async function submitQuery() {
            const query = document.getElementById('query').value;
            const response = await fetch('/parse', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ query: query })
            });
            const data = await response.json();
            // Build the final URL by serializing the structured object
            const url = new URL(window.location.origin + '/searchRedirect');
            url.searchParams.append('query', data.query);
            document.getElementById('resultLink').innerHTML = '<a href="' + url.toString() + '">Click here to view results</a>';
          }
        </script>
      </body>
    </html>
    """
    return html_content

# Endpoint to redirect to Immich's search URL with our query JSON embedded.
@app.get("/searchRedirect")
def search_redirect(query: str):
    # Construct Immich search URL using the provided query JSON.
    immich_search_url = f"https://{immich_host}:{immich_port}/search?query={query}"
    html_content = f"""
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url={immich_search_url}" />
      </head>
      <body>
        <p>Redirecting to <a href="{immich_search_url}">{immich_search_url}</a></p>
      </body>
    </html>
    """
    return HTMLResponse(content=html_content)
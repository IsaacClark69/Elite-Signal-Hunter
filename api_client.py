import json
import requests
from usd import USD_SCHEMA, generate_sighting_id

# In a real application, this would be in a configuration file.
API_ENDPOINT = "https://example.com/api/submit_signal" 

def submit_signal(cmdr_context, signal_characteristics, raw_data_hash, notes=""):
    """
    Constructs and 'sends' a signal report to the central database.
    
    For now, it just prints the JSON that would be sent.
    """
    
    # 1. Generate a unique ID for this sighting
    sighting_id = generate_sighting_id(cmdr_context.get("timestamp", ""), cmdr_context.get("Commander", "UnknownCMDR"))

    # 2. Build the submission dictionary using the USD schema
    submission = {
        "sighting_id": sighting_id,
        "timestamp_utc": cmdr_context.get("timestamp", ""),
        "cmdr_name": cmdr_context.get("Commander", "UnknownCMDR"),
        "cmdr_context": {
            "ship": cmdr_context.get("Ship", "Unknown"),
            "system": cmdr_context.get("StarSystem", "Unknown"),
            "body": cmdr_context.get("BodyName", "Unknown"),
        },
        "signal_characteristics": signal_characteristics,
        "raw_data_hash": raw_data_hash,
        "notes": notes
    }

    # 3. Convert to JSON
    submission_json = json.dumps(submission, indent=4)

    # 4. "Submit" the data (for now, just print it)
    print("--- BEGIN SIGNAL SUBMISSION ---")
    print(submission_json)
    print("--- END SIGNAL SUBMISSION ---")
    
    # In the future, this would be an actual API call:
    # try:
    #     response = requests.post(API_ENDPOINT, json=submission)
    #     response.raise_for_status() # Raise an exception for bad status codes
    #     print(f"Successfully submitted signal {sighting_id}. Server response: {response.json()}")
    #     return True, sighting_id
    # except requests.exceptions.RequestException as e:
    #     print(f"Error submitting signal: {e}")
    #     return False, None
        
    return True, sighting_id # Simulate success for now

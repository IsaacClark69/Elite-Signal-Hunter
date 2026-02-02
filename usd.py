"""
Defines the Universal Signal Descriptor (USD) schema for submitting signal
findings to the central database.
"""

# This dictionary represents the structure of a signal submission.
# It will be converted to JSON before sending to the API.
USD_SCHEMA = {
    "sighting_id": "unique_sighting_id_generated_by_client",
    "timestamp_utc": "ISO_8601_timestamp",
    "cmdr_name": "CommanderName",
    "cmdr_context": {
        "ship": "ShipType",
        "system": "StarSystem",
        "body": "BodyName",
        # And other relevant data from the journal...
    },
    "signal_characteristics": {
        "peak_frequency": 1234.5, # Hz
        "snr": 25.5, # dB
        "bandwidth": 50.0, # Hz
        "spectral_centroid": 1250.0, # Hz
        # Doppler shift would be calculated server-side or in a later client version
    },
    "raw_data_hash": "sha256_hash_of_capture.wav",
    # The raw .wav and full metadata.json will be uploaded separately,
    # and the server will associate them with the sighting_id.
    "community_vetting": {
        "confirmations": 0,
        "rejections": 0,
        "status": "unverified" # e.g., unverified, verified, rejected
    },
    "notes": "Optional user-submitted notes about the signal."
}

def generate_sighting_id(timestamp_utc, cmdr_name):
    """Generates a unique sighting ID based on timestamp and commander name."""
    import hashlib
    id_string = f"{timestamp_utc}-{cmdr_name}"
    return hashlib.sha1(id_string.encode('utf-8')).hexdigest()

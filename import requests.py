import requests

def hms_code(attr, code):
    if attr > 0 and code > 0:
        return f'{int(attr / 0x10000):0>4X}_{attr & 0xFFFF:0>4X}_{int(code / 0x10000):0>4X}_{code & 0xFFFF:0>4X}' # 0300_0100_0001_0007
    return ""

def check_errors(attr, code):
    url = "https://e.bambulab.com/query.php?lang=en"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        # Extracting English error codes and descriptions
        english_errors = data["data"]["device_hms"]["en"]
        
        # Create a temporary JSON structure for hms data if it's not present in the response
        hms_json = data["data"]["device_hms"].get("hms", [])
        
        # Function to search for a specific error code
        def search_error(error_code, error_list):
            for error in error_list:
                if error["ecode"] == error_code:
                    return error
            return None
        
        # Example: Searching for device_hms error code
        device_error_code_to_search = hms_code(attr, code)
        error_code_to_hms_cleaned = device_error_code_to_search.replace("hms_", "")
        error_code_to_search_cleaned = error_code_to_hms_cleaned.replace("_", "")
        found_device_error = search_error(error_code_to_search_cleaned, english_errors)

        # Example: Searching for reporting error code
        found_reporting_error = search_error(code, hms_json)

        if found_device_error:
            print("Device Error Code:", device_error_code_to_search)
            print("Description:", found_device_error["intro"])
            print("URL:", f"https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/{error_code_to_hms_cleaned}")
        else:
            print("Device error code", device_error_code_to_search, "not found.")
    else:
        print("Failed to fetch data:", response.status_code)

# Example usage
attr_value = 50336000
code_value = 131074


def parse_json(url):
    # Send a GET request to the URL
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON content
        data = response.json()

        # Print the parsed JSON data
        print(json.dumps(data, indent=4))

        # Or you can access specific data fields like this:
        # print(data['field_name'])

    else:
        print("Failed to retrieve JSON data")

# URL of the JSON file
url = "https://e.bambulab.com/query.php?lang=en"

# Call the function to parse the JSON data
parse_json(url)
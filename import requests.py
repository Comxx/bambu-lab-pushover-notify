import requests

url = "https://e.bambulab.com/query.php?lang=en"

response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    english_errors = data["data"]["device_hms"]["en"]
    
for error in english_errors:
    ecode = error["ecode"]
    intro = error["intro"]
    print("Error Code:", ecode)
    print("Description:", intro)
    print()
else:
    print("Failed to fetch data:", response.status_code)
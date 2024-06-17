import logging
from bambu_cloud import BambuCloud

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    # Configuration
    region = 'US'  # e.g., 'China' or 'US'
    email = ''    
    password = ''
    
    # Initialize BambuCloud instance
    bambu_cloud = BambuCloud(region=region, email=email, username='', auth_token='')

    # Login to get auth token and username
    print("Attempting to log in to Bambu Cloud.")
    try:
        bambu_cloud.login(region=region, email=email, password=password)
        print(f"Access Token: {bambu_cloud.auth_token}")
        print(f"Username: {bambu_cloud.username}")
    except ValueError as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    main()

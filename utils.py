from constants import BAMBU_URL

def get_Url(url: str, region: str):
    urlstr = BAMBU_URL[url]
    if region == "China":
        urlstr = urlstr.replace('.com', '.cn')
    return urlstr
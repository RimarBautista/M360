from datetime import datetime

import requests
import json
import pytest

payload = {
        "app_key": "aNCnlGizAhrSV3QP",
        "app_secret": "iCi7H6rmceVUjZPnjrZHA6L91n7cKcaY",
        # telco ID: 1=Globe/TM, 2=Smart/TNT, 3=SUN, 4=DITO
        "to": [
        # Globe valid
         "639197764436"
        # Smart valid
        # "639609325315"
        # Dito
        # "639945938603"
        # UK
        # "447949338056"
        # India
        # "917428730894"
        # SPAIN
        # "34628152325"
        ],
        "from": "qamoo2",
        "is_template": False,
        "is_intl": True,
        "dcs": 0,
         # 0,1: 1 message part = 160, if >160 counter should be 153 per message part
         # 3,8: 1 message part = 70, if >70 counter should be 67 per message part
        "content": {
            "text": "1 message part 1 message part 1 message part 1 "
                    "message part 1 message part 1 message part 1 message part 1 "
                    "message part 1 message part 1 message part 1 messag1601 message part 1"
        },
        "request_id": "ABC123",
        "template": {
            "code": "M360-TEMPLATE-44CA93AEF22B7EC941715058357",
            "variables": {
                "client_name": "Client 1",
                "client_email": "jgulinao@m360.com.ph"
            }
        }
    }
       # "text": "  ¡ ¢ £ ¤ ¥ ¦ § ¨ © ª « ¬ ­ ® ¯ ° ± ² ³ ´ µ ¶ · ¸ ¹ º » ¼ ½ ¾ ¿ À Á Â Ã Ä Å Æ Ç È É Ê Ë Ì Í Î Ï Ð Ñ Ò Ó Ô Õ Ö × Ø Ù Ú Û Ü Ý Þ ß à á â ã ä å æ ç è é ê ë ì í î ï ð ñ ò ó ô õ ö ÷ ø ù ú û ü ý þ ÿ \r 😀 😃 😄 😁 😆 😅 🤣 😂 🙂 🙃 🫠 😉 😊 😇 \r \ud83d\ude28\ud83d\ude27\ud83d\ude26\ud83d\ude31\ud83d\ude2b\ud83d\ude29"

def test_get_api(endpoint):
    response = requests.get(endpoint)
    assert response.status_code == 200
    print(response.text)

def test_post_api(endpoint):
    response = requests.post(endpoint, json=payload)
    assert response.status_code == 200
    json_response = json.loads(response.text)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    print(json_response)
    with open(f"m360reports/{timestamp}data.json", "w") as file:
        json.dump(json_response, file, indent=4)


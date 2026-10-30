import os


CURRENT_ENV = os.getenv("ENV", "prod")


ENVIRONMENTS = {

    "stg": {
        "url": "https://stg-portal.m360.com.ph/login",
        "username": "test0001",
        "password": "LQQ1RQw1",
    },

    "prod": {
        "url": "https://dashboard.m360.com.ph/login",
        "username": "jgmy360plan50k",
        "password": "Em360@123!!",
    }
}


def get_environment():
    return ENVIRONMENTS[CURRENT_ENV]
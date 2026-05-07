
import pytest
from openpyxl.packaging import workbook
from selenium import webdriver

BaseUrl = 'https://stg-portal.m360.com.ph/login'
login_page_title = 'm360 - Login'
email = '3806230'
password = 'Em360@123!'


@pytest.fixture(scope='class', autouse=True)
def browser_setup(request):
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-notifications')
    request.cls.driver = webdriver.Chrome(options=options)


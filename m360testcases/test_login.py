import pytest

from conftest import BaseUrl,email,password,login_page_title
from m360pages.LoginPage import LoginPage

@pytest.mark.usefixtures("browser_setup")
class Test_login:

    def setup_class(self):
        self.driver.get(BaseUrl)
        self.loginPage = LoginPage(self.driver)

    def test_login(self):
        assert self.loginPage.get_title_page().__eq__(login_page_title)
        self.loginPage.login(email,password)
        assert self.loginPage.check_page_element()

    def teardown_class(self):
        self.driver.quit()
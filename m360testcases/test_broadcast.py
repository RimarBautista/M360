import time

import pytest

from conftest import BaseUrl,email,password,login_page_title
from m360helper import selenium_helper
from m360pages.LoginPage import LoginPage
from m360pages.BroadcastPage import BroadcastPage
from API_requests import test_API
from m360helper.selenium_helper import SeleniumHelper

@pytest.mark.usefixtures("browser_setup")
class Test_Click_Tracking_Case:

    def setup_class(self):
        self.testApi = test_API
        # API calling
        # self.testApi.test_post_api("https://stg-api.m360.com.ph/v4/sms/send")
        # time.sleep(5)
        # -------------------------------

        self.driver.get(BaseUrl)
        self.driver.maximize_window()
        self.loginPage = LoginPage(self.driver)
        self.broadcastPage = BroadcastPage(self.driver)

    def test_click_tracking(self):
        # login journey
        # SeleniumHelper.start_video_recording()
        assert self.loginPage.get_title_page().__eq__(login_page_title)
        self.loginPage.login(email,password)
        assert self.loginPage.check_page_element()

        # broadcast journey
        self.broadcastPage.goto_broadcast()
        assert self.broadcastPage.check_page_element()
        # SeleniumHelper.stop_video_recording()

    def teardown_class(self):
        self.driver.quit()
import string
import time

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from m360helper.selenium_helper import SeleniumHelper
from conftest import email


class BroadcastPage(SeleniumHelper):
    def __init__(self, driver):
        super().__init__(driver)
        self.alphabet_list = None

    broadcast_tab_element = (By.XPATH, "//span[text()='Broadcasts']")
    broadcast_list_tab_element = (By.XPATH, "//span[text()='Broadcast List']")
    broadcast_list_item = (By.XPATH, "//table//tr[3]")
    duplicate_button = (By.XPATH, "//span[text()=' Duplicate Broadcast ']")
    confirm_duplicate_button = (By.XPATH, "//span[text()=' Yes, duplicate ']")
    start_broadcast_button = (By.XPATH, "//span[text()=' Start broadcast ']")
    broadcast_list = (By.XPATH, "//h1[text()='Broadcast List']")
    confirm_button = (By.XPATH, "//span[text()=' Confirm and start broadcast ']")



    def goto_broadcast(self):
        time.sleep(1)
        self.click_element(self.broadcast_tab_element)
        self.click_element(self.broadcast_list_tab_element)
        self.click_element(self.broadcast_list_item)
        self.click_element(self.duplicate_button)
        self.click_element(self.confirm_duplicate_button)
        time.sleep(5)
        self.click_element(self.start_broadcast_button)
        self.click_element(self.confirm_button)

    def check_page_element(self):
        return self.web_element_display(self.broadcast_list)
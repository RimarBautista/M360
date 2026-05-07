from selenium.webdriver.common.by import By

from m360helper.selenium_helper import SeleniumHelper


class LoginPage(SeleniumHelper):
    def __init__(self, driver):
        super().__init__(driver)

    input_email_element = (By.XPATH, '//input[@data-cy="username"]')
    input_password_element = (By.XPATH, '//input[@data-cy="password"]')
    login_button_element = (By.XPATH, '//button[@data-cy="login-button"]')
    dashboard_element = (By.XPATH, '//h3[contains(text(),"Dashboard")]')

    def login(self, email, password):
        self.get_title_page()
        self.enter_text(self.input_email_element, email)
        self.enter_text(self.input_password_element, password)
        self.click_element(self.login_button_element)
        self.capture_screenshot("Screenshots/Login.png")

    def check_page_element(self):
        return self.web_element_display(self.dashboard_element)